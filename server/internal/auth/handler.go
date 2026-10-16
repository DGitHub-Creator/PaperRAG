package auth

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/httpapi"
)

// detail 文案一律**照抄** backend/api/auth.py 与 core/auth.py，含"中英文混用"这个现状：
// register/login 的 400/401/409 是英文，令牌失效与两条 403 是中文。
// 统一成一种语言看着更整洁，但那会让跨语言契约测试各验一套，而前端可能已经按现有字符串分支。
// 要改文案就两侧一起改，并同步 contracts/error-codes.md。
const (
	detailCredentialsRequired = "Username and password are required"
	detailPasswordTooSimple   = "Password must include at least two of lowercase, uppercase, and digits"
	detailUsernameTaken       = "Username already exists"
	detailInvalidLogin        = "Invalid username or password"
	detailAdminChannelClosed  = "系统未配置管理员邀请码，管理员注册已关闭"
	detailAdminCodeMismatch   = "管理员邀请码错误"
	detailInvalidToken        = "无效或过期的认证令牌"
	detailNotAuthenticated    = httpapi.DetailNotAuthenticated
	detailInternalError       = httpapi.DetailInternalError
	// detailWrongPassword 没有 Python 对照（改密码是新开的 Go 面），文案与其余 400 一路用英文。
	detailWrongPassword = "Current password is incorrect"
	// 偏好的两条 400 同样没有 Python 对照；取值域在契约的 enum 里（openapi.yaml）。
	detailInvalidTheme     = "theme must be one of: light, dark, system"
	detailInvalidStartView = "start_view must be a lowercase slug"
)

// 请求体校验的文案。这几条不是猜的：2026-10-12 用**生产侧的** handler
// （backend/core/exceptions.py:request_validation_error_handler，决策 K4 把 422 降级成
// 400+字符串）配 RegisterRequest 现跑取数，六种输入的实际响应如下，Go 逐条对齐：
//
//	{"username":"alice"}            → 400 "password: Field required"
//	{}                              → 400 "username: Field required; password: Field required"
//	{"username":123,"password":"…"} → 400 "username: Input should be a valid string"
//	{"username":"a","password":null} → 400 "password: Input should be a valid string"
//	多余字段                         → 200（pydantic 默认忽略未知键，Go 也不能拒）
//	非法 JSON                        → 400 "1: JSON decode error"
//	空 body                          → 400 "请求体: Field required"
//	非 JSON 的 Content-Type           → 400 "请求体: Input should be a valid dictionary or object to extract fields from"
const (
	msgFieldRequired   = "Field required"
	msgInvalidString   = "Input should be a valid string"
	msgJSONDecode      = "1: JSON decode error"
	msgBodyRequired    = "请求体: Field required"
	msgBodyNotAnObject = "请求体: Input should be a valid dictionary or object to extract fields from"
)

// AuthResponse 对应契约的 AuthResponse（openapi.yaml）。
// 字段顺序与 pydantic 的声明顺序一致：token_type 有默认值 "bearer"，但它**确实出现在响应体里**，
// 少一项前端就拿不到（api/types.ts 按契约声明了它）。
type AuthResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
	Username     string `json:"username"`
	Role         string `json:"role"`
}

// CurrentUserResponse 对应契约的 CurrentUserResponse，只有两项。
type CurrentUserResponse struct {
	Username string `json:"username"`
	Role     string `json:"role"`
}

// RegisterHandler 处理 POST /api/v1/auth/register。As-Is：注册即登录，直接返回两个 token。
func RegisterHandler(s *Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		fields, problem := decodeJSONObject(r)
		if problem != "" {
			httpapi.WriteError(w, http.StatusBadRequest, problem)
			return
		}

		// 按 pydantic 的声明顺序收集问题，多条用 "; " 连接（K4 的 handler 就是这么拼的）。
		var problems []string
		username, _, p := stringField(fields, "username", true)
		problems = appendIf(problems, p)
		password, _, p := stringField(fields, "password", true)
		problems = appendIf(problems, p)
		role, roleGiven, p := stringField(fields, "role", false)
		problems = appendIf(problems, p)
		adminCode, adminCodeGiven, p := stringField(fields, "admin_code", false)
		problems = appendIf(problems, p)
		if len(problems) > 0 {
			httpapi.WriteError(w, http.StatusBadRequest, strings.Join(problems, "; "))
			return
		}

		in := RegisterInput{Username: username, Password: password}
		if roleGiven {
			in.Role = &role
		}
		if adminCodeGiven {
			in.AdminCode = &adminCode
		}

		result, err := s.Register(r.Context(), in)
		if err != nil {
			writeServiceError(w, err, s.MinPasswordLength)
			return
		}
		httpapi.WriteJSON(w, http.StatusOK, toAuthResponse(result))
	}
}

// LoginHandler 处理 POST /api/v1/auth/login。
func LoginHandler(s *Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		fields, problem := decodeJSONObject(r)
		if problem != "" {
			httpapi.WriteError(w, http.StatusBadRequest, problem)
			return
		}
		var problems []string
		username, _, p := stringField(fields, "username", true)
		problems = appendIf(problems, p)
		password, _, p := stringField(fields, "password", true)
		problems = appendIf(problems, p)
		if len(problems) > 0 {
			httpapi.WriteError(w, http.StatusBadRequest, strings.Join(problems, "; "))
			return
		}

		result, err := s.Login(r.Context(), username, password)
		if err != nil {
			writeServiceError(w, err, s.MinPasswordLength)
			return
		}
		httpapi.WriteJSON(w, http.StatusOK, toAuthResponse(result))
	}
}

// MeHandler 处理 GET /api/v1/auth/me：校验 token 并回显身份（前端启动时探测登录态）。
func MeHandler(s *Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		token, ok := bearerToken(r.Header.Get("Authorization"))
		if !ok {
			// 缺 Authorization 头与"方案不是 bearer"在生产侧是**同一句** "Not authenticated"
			// （2026-10-12 实测 OAuth2PasswordBearer：Basic 方案也回这句，不是
			// "Invalid authentication credentials"——那句在 HTTPBearer 里，本项目没用它）。
			writeUnauthorized(w, detailNotAuthenticated)
			return
		}
		identity, err := s.CurrentUser(r.Context(), token)
		if err != nil {
			if errors.Is(err, ErrUnauthenticated) {
				writeUnauthorized(w, detailInvalidToken)
				return
			}
			httpapi.WriteError(w, http.StatusInternalServerError, detailInternalError)
			return
		}
		httpapi.WriteJSON(w, http.StatusOK, CurrentUserResponse{Username: identity.Username, Role: identity.Role})
	}
}

// ChangePasswordHandler 处理 POST /api/v1/auth/password（设置页的「改密码」）。
// 先验令牌再读请求体：令牌缺失时不该因为"body 也没带"而先报 400，
// 那会让"到底该重新登录还是该改请求"分不清。
func ChangePasswordHandler(s *Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		token, ok := bearerToken(r.Header.Get("Authorization"))
		if !ok {
			writeUnauthorized(w, detailNotAuthenticated)
			return
		}
		fields, problem := decodeJSONObject(r)
		if problem != "" {
			httpapi.WriteError(w, http.StatusBadRequest, problem)
			return
		}
		var problems []string
		oldPassword, _, p := stringField(fields, "old_password", true)
		problems = appendIf(problems, p)
		newPassword, _, p := stringField(fields, "new_password", true)
		problems = appendIf(problems, p)
		if len(problems) > 0 {
			httpapi.WriteError(w, http.StatusBadRequest, strings.Join(problems, "; "))
			return
		}

		if err := s.ChangePassword(r.Context(), token, oldPassword, newPassword); err != nil {
			writeChangePasswordError(w, err)
			return
		}
		httpapi.WriteJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	}
}

// bearerToken 从 Authorization 头取出令牌。语义对齐 Starlette 的
// get_authorization_scheme_param：按**第一个**空格切分，方案名大小写不敏感，
// 且 "Bearer"（后面什么都没有）算方案匹配、令牌为空串——空串随后会在
// 令牌校验那一步被拒，而不是在这里变成 "Not authenticated"（实测生产侧就是这个顺序）。
func bearerToken(header string) (string, bool) {
	if header == "" {
		return "", false
	}
	scheme, param, _ := strings.Cut(header, " ")
	if strings.ToLower(scheme) != "bearer" {
		return "", false
	}
	return param, true
}

func writeUnauthorized(w http.ResponseWriter, detail string) {
	// WWW-Authenticate 必须带：生产侧三处 401 都带 Bearer，浏览器的某些客户端与
	// curl --fail 会看这个头，契约里 Unauthorized 的语义也依赖它。
	w.Header().Set("WWW-Authenticate", "Bearer")
	httpapi.WriteError(w, http.StatusUnauthorized, detail)
}

func writeServiceError(w http.ResponseWriter, err error, minPasswordLength int) {
	var tooShort PasswordTooShortError
	switch {
	case errors.Is(err, ErrMissingCredentials):
		httpapi.WriteError(w, http.StatusBadRequest, detailCredentialsRequired)
	case errors.As(err, &tooShort):
		httpapi.WriteError(w, http.StatusBadRequest,
			fmt.Sprintf("Password must be at least %d characters", tooShort.Min))
	case errors.Is(err, ErrPasswordTooSimple):
		httpapi.WriteError(w, http.StatusBadRequest, detailPasswordTooSimple)
	case errors.Is(err, ErrUsernameTaken):
		httpapi.WriteError(w, http.StatusConflict, detailUsernameTaken)
	case errors.Is(err, ErrInvalidCredentials):
		httpapi.WriteError(w, http.StatusUnauthorized, detailInvalidLogin)
	case errors.Is(err, ErrAdminChannelClosed):
		httpapi.WriteError(w, http.StatusForbidden, detailAdminChannelClosed)
	case errors.Is(err, ErrAdminCodeMismatch):
		httpapi.WriteError(w, http.StatusForbidden, detailAdminCodeMismatch)
	case errors.Is(err, ErrUnauthenticated):
		writeUnauthorized(w, detailInvalidToken)
	default:
		// 库连接失败之类：对外一句话，细节只进日志（生产侧 unhandled_error_handler 同款文案）。
		httpapi.WriteError(w, http.StatusInternalServerError, detailInternalError)
	}
}

// writeChangePasswordError 把改密码的失败映射成 HTTP。与 writeServiceError 分开是刻意的：
// 那张表里的 409/403 属于注册语义，改密码路径永远不会遇到，混在一起会让后来的人
// 以为改密码可能回 403。
func writeChangePasswordError(w http.ResponseWriter, err error) {
	var tooShort PasswordTooShortError
	switch {
	case errors.Is(err, ErrWrongPassword):
		httpapi.WriteError(w, http.StatusBadRequest, detailWrongPassword)
	case errors.As(err, &tooShort):
		httpapi.WriteError(w, http.StatusBadRequest,
			fmt.Sprintf("Password must be at least %d characters", tooShort.Min))
	case errors.Is(err, ErrPasswordTooSimple):
		httpapi.WriteError(w, http.StatusBadRequest, detailPasswordTooSimple)
	case errors.Is(err, ErrUnauthenticated):
		writeUnauthorized(w, detailInvalidToken)
	default:
		httpapi.WriteError(w, http.StatusInternalServerError, detailInternalError)
	}
}

func toAuthResponse(r *AuthResult) AuthResponse {
	return AuthResponse{
		AccessToken:  r.AccessToken,
		RefreshToken: r.RefreshToken,
		TokenType:    r.TokenType,
		Username:     r.Username,
		Role:         r.Role,
	}
}

// decodeJSONObject 读请求体并解析成 JSON 对象。返回的字符串是"已经拼好的 detail"，
// 空串表示没问题。四种失败各自对应生产侧的一种文案（见上面那张实测表）。
//
// Go 在 dev 中直接作为公开入口，不能依赖 nginx 才限制认证请求体；上传不走此解析器。
func decodeJSONObject(r *http.Request) (map[string]json.RawMessage, string) {
	// Content-Type 取媒体类型（去掉 "; charset=…"），大小写不敏感。
	mediaType := strings.ToLower(strings.TrimSpace(strings.SplitN(r.Header.Get("Content-Type"), ";", 2)[0]))
	if mediaType != "" && mediaType != "application/json" {
		return nil, msgBodyNotAnObject
	}

	const maxAuthBodyBytes = 1024 * 1024
	raw, err := io.ReadAll(io.LimitReader(r.Body, maxAuthBodyBytes+1))
	if len(raw) > maxAuthBodyBytes {
		return nil, "请求体超过 1 MiB 限制"
	}
	if err != nil {
		return nil, msgJSONDecode
	}
	if len(strings.TrimSpace(string(raw))) == 0 {
		// 空 body：pydantic 报的是"整个请求体缺失"，loc 只有 ("body",) → 字段名落到 "请求体"
		return nil, msgBodyRequired
	}

	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		// 既覆盖"不是合法 JSON"，也覆盖"是合法 JSON 但不是对象"（如 [] 或 "x"）。
		// 生产侧对前者报 "1: JSON decode error"、对后者报 "请求体: Input should be a valid
		// dictionary or object…"；这里合成一条，取前者——前端只会发对象或发坏，
		// 而 contracts/error-codes.md 明确给了 Go 余地（"直接发 400 + 一句话即可"）。
		var typeErr *json.UnmarshalTypeError
		if errors.As(err, &typeErr) {
			return nil, msgBodyNotAnObject
		}
		return nil, msgJSONDecode
	}
	if fields == nil {
		// JSON 里显式的 null 会解成 nil map
		return nil, msgBodyNotAnObject
	}
	return fields, ""
}

// stringField 取一个字符串字段。返回 (值, 请求里给了没有, 校验文案)。
//
// "缺键"与"给了 null"在生产侧结论不同，必须分开：
// 缺必填键 → "Field required"；给了 null → "Input should be a valid string"（实测如此）。
// 可选字段给 null 等于没给（Python 那边是 None）。
func stringField(fields map[string]json.RawMessage, name string, required bool) (value string, given bool, problem string) {
	raw, present := fields[name]
	if !present || string(raw) == "null" {
		if required {
			msg := msgFieldRequired
			if present {
				msg = msgInvalidString
			}
			return "", false, name + ": " + msg
		}
		return "", false, ""
	}
	var s string
	if err := json.Unmarshal(raw, &s); err != nil {
		return "", false, name + ": " + msgInvalidString
	}
	return s, true, ""
}

func appendIf(list []string, item string) []string {
	if item == "" {
		return list
	}
	return append(list, item)
}
