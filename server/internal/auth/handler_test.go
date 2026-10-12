package auth

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// 这一层的用例几乎全在钉**文案与状态码**，看着琐碎，但它们是跨语言契约的实际内容：
// 前端按 detail 字符串分支（例如把 409 显示成"用户名已被占用"），两侧文案差一个字母
// 就会变成"同样的操作在 Go 与 Python 下提示不同"。所有期望值都是 2026-10-12 用生产侧
// 的 handler 与 schema 现跑取数的，不是我按印象写的（取数方法见 handler.go 顶部那张表）。

func doJSON(t *testing.T, h http.HandlerFunc, method, target, contentType, body string, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	var reader *strings.Reader
	if body == "" {
		reader = strings.NewReader("")
	} else {
		reader = strings.NewReader(body)
	}
	req := httptest.NewRequest(method, target, reader)
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

// detailOf 断言响应是 {"detail": ...} 信封并取出 detail 字符串。
// 全仓只有一种错误信封（01 §6.1，决策 K1/K4 之后没有第二种形状），
// 所以任何非 2xx 都必须能这样解出来。
func detailOf(t *testing.T, rec *httptest.ResponseRecorder) string {
	t.Helper()
	var envelope struct {
		Detail json.RawMessage `json:"detail"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("响应不是 JSON 信封: %v；原文=%s", err, rec.Body.String())
	}
	if len(envelope.Detail) == 0 {
		t.Fatalf("信封里没有 detail 字段；原文=%s", rec.Body.String())
	}
	var s string
	if err := json.Unmarshal(envelope.Detail, &s); err != nil {
		t.Fatalf("detail 应是字符串（决策 K4 之后不再有数组形状）: %v；原文=%s", err, rec.Body.String())
	}
	return s
}

func decodeBody(t *testing.T, rec *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var out map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("响应不是 JSON 对象: %v；原文=%s", err, rec.Body.String())
	}
	return out
}

// ── register ──────────────────────────────────────────────────────────

func TestRegisterHandlerSuccess(t *testing.T) {
	store := newFakeStore()
	h := RegisterHandler(testService(store))

	rec := doJSON(t, h, http.MethodPost, "/api/v1/auth/register", "application/json",
		`{"username":"alice","password":"Abcdef12"}`, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200（As-Is：注册即登录，不是 201），实得 %d：%s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	// 五个字段一个都不能少：token_type 在 pydantic 里有默认值，但它确实出现在响应体里，
	// 前端 api/types.ts 按契约声明了它。
	for _, field := range []string{"access_token", "refresh_token", "token_type", "username", "role"} {
		if _, ok := body[field]; !ok {
			t.Errorf("响应缺字段 %q；实得 %v", field, body)
		}
	}
	if len(body) != 5 {
		t.Errorf("响应应恰好是 5 个字段（多出来的字段契约里没有，前端读不到还会掩盖漂移），实得 %v", body)
	}
	if body["token_type"] != "bearer" {
		t.Errorf("token_type 应是 bearer，实得 %v", body["token_type"])
	}
	if body["username"] != "alice" || body["role"] != "user" {
		t.Errorf("身份不对: %v", body)
	}
	// password_hash 绝不能出现在任何响应里
	if strings.Contains(rec.Body.String(), store.users["alice"].PasswordHash) {
		t.Error("响应体里出现了 password_hash")
	}
}

func TestRegisterHandlerValidationTexts(t *testing.T) {
	cases := []struct {
		name        string
		body        string
		contentType string
		wantDetail  string
	}{
		{"缺 password", `{"username":"alice"}`, "application/json", "password: Field required"},
		{"两个都缺（按声明顺序拼）", `{}`, "application/json", "username: Field required; password: Field required"},
		{"username 类型错", `{"username":123,"password":"Abcdef12"}`, "application/json", "username: Input should be a valid string"},
		{"password 为 null", `{"username":"alice","password":null}`, "application/json", "password: Input should be a valid string"},
		{"非法 JSON", `{not json`, "application/json", "1: JSON decode error"},
		{"空 body", ``, "application/json", "请求体: Field required"},
		{"非 JSON 的 Content-Type", `username=alice`, "application/x-www-form-urlencoded",
			"请求体: Input should be a valid dictionary or object to extract fields from"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			h := RegisterHandler(testService(newFakeStore()))
			rec := doJSON(t, h, http.MethodPost, "/api/v1/auth/register", c.contentType, c.body, nil)
			if rec.Code != http.StatusBadRequest {
				t.Fatalf("期望 400（决策 K4：422 已降级），实得 %d：%s", rec.Code, rec.Body.String())
			}
			if got := detailOf(t, rec); got != c.wantDetail {
				t.Errorf("detail 不匹配\n  期望 %q\n  实得 %q", c.wantDetail, got)
			}
		})
	}
}

// TestRegisterHandlerIgnoresUnknownFields 与 TestRegisterHandlerFoldsUnknownRole
// 一起钉住"契约比实现严"这件事的处置：openapi.yaml 的 role 引用了 enum [user, admin]，
// 但生产侧 `role: str | None`，实测 role="root" 返回 200 并被折叠成 user，多余字段也返回 200。
// Go 照**实现**走（裁判是运行中的系统），不照枚举走——否则同一个请求两侧结论不同。
func TestRegisterHandlerIgnoresUnknownFields(t *testing.T) {
	h := RegisterHandler(testService(newFakeStore()))
	rec := doJSON(t, h, http.MethodPost, "/api/v1/auth/register", "application/json",
		`{"username":"alice","password":"Abcdef12","zzz":1,"nested":{"a":[1,2]}}`, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("多余字段应被忽略（pydantic 默认不 forbid extra），实得 %d：%s", rec.Code, rec.Body.String())
	}
}

func TestRegisterHandlerFoldsUnknownRole(t *testing.T) {
	store := newFakeStore()
	h := RegisterHandler(testService(store))
	rec := doJSON(t, h, http.MethodPost, "/api/v1/auth/register", "application/json",
		`{"username":"alice","password":"Abcdef12","role":"root"}`, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("非法枚举值应被折叠而不是拒绝，实得 %d：%s", rec.Code, rec.Body.String())
	}
	if got := decodeBody(t, rec)["role"]; got != "user" {
		t.Errorf("role 应折叠成 user，实得 %v", got)
	}
	if store.users["alice"].Role != "user" {
		t.Errorf("存进库的角色应是 user，实得 %q", store.users["alice"].Role)
	}
}

func TestRegisterHandlerPasswordPolicyTexts(t *testing.T) {
	h := RegisterHandler(testService(newFakeStore()))

	rec := doJSON(t, h, http.MethodPost, "/api/v1/auth/register", "application/json",
		`{"username":"alice","password":"Ab1"}`, nil)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("口令太短应 400，实得 %d", rec.Code)
	}
	// 文案里的数字来自 MIN_PASSWORD_LENGTH，不能写死成 8 而丢掉配置值
	if got, want := detailOf(t, rec), "Password must be at least 8 characters"; got != want {
		t.Errorf("detail 不匹配\n  期望 %q\n  实得 %q", want, got)
	}

	rec = doJSON(t, h, http.MethodPost, "/api/v1/auth/register", "application/json",
		`{"username":"alice","password":"abcdefgh"}`, nil)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("字符类别不足应 400，实得 %d", rec.Code)
	}
	want := "Password must include at least two of lowercase, uppercase, and digits"
	if got := detailOf(t, rec); got != want {
		t.Errorf("detail 不匹配\n  期望 %q\n  实得 %q", want, got)
	}

	// strip 之后为空 → 走的是"必填"那句，不是密码策略那两句
	rec = doJSON(t, h, http.MethodPost, "/api/v1/auth/register", "application/json",
		`{"username":"   ","password":"   "}`, nil)
	if got := detailOf(t, rec); got != detailCredentialsRequired {
		t.Errorf("期望 %q，实得 %q", detailCredentialsRequired, got)
	}
}

func TestRegisterHandlerConflictAndForbiddenTexts(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "taken", "Abcdef12", "user")
	svc := NewService(store, TokenConfig{Secret: "s", ExpireMinutes: 60, RefreshExpireDays: 30},
		40000, "correct-horse", 8, discardLogger())
	h := RegisterHandler(svc)

	rec := doJSON(t, h, http.MethodPost, "/api/v1/auth/register", "application/json",
		`{"username":"taken","password":"Abcdef12"}`, nil)
	if rec.Code != http.StatusConflict {
		t.Fatalf("重名应 409，实得 %d", rec.Code)
	}
	if got := detailOf(t, rec); got != detailUsernameTaken {
		t.Errorf("期望 %q，实得 %q", detailUsernameTaken, got)
	}

	// 邀请码错 → 403
	rec = doJSON(t, h, http.MethodPost, "/api/v1/auth/register", "application/json",
		`{"username":"newbie","password":"Abcdef12","role":"admin","admin_code":"nope"}`, nil)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("邀请码错应 403，实得 %d", rec.Code)
	}
	if got := detailOf(t, rec); got != detailAdminCodeMismatch {
		t.Errorf("期望 %q，实得 %q", detailAdminCodeMismatch, got)
	}

	// 未配置邀请码 → 403，但是**另一句**：通道关闭 ≠ 你输错了
	closed := NewService(newFakeStore(), TokenConfig{Secret: "s", ExpireMinutes: 60, RefreshExpireDays: 30},
		40000, "", 8, discardLogger())
	rec = doJSON(t, RegisterHandler(closed), http.MethodPost, "/api/v1/auth/register", "application/json",
		`{"username":"newbie","password":"Abcdef12","role":"admin","admin_code":"anything"}`, nil)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("通道关闭应 403，实得 %d", rec.Code)
	}
	if got := detailOf(t, rec); got != detailAdminChannelClosed {
		t.Errorf("期望 %q，实得 %q", detailAdminChannelClosed, got)
	}

	// 邀请码对 → admin
	rec = doJSON(t, h, http.MethodPost, "/api/v1/auth/register", "application/json",
		`{"username":"root2","password":"Abcdef12","role":"admin","admin_code":"correct-horse"}`, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("邀请码正确应 200，实得 %d：%s", rec.Code, rec.Body.String())
	}
	if got := decodeBody(t, rec)["role"]; got != "admin" {
		t.Errorf("角色应是 admin，实得 %v", got)
	}
}

// ── login ─────────────────────────────────────────────────────────────

func TestLoginHandler(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	h := LoginHandler(testService(store))

	rec := doJSON(t, h, http.MethodPost, "/api/v1/auth/login", "application/json",
		`{"username":"alice","password":"Abcdef12"}`, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("登录应 200，实得 %d：%s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	if len(body) != 5 || body["token_type"] != "bearer" || body["username"] != "alice" {
		t.Errorf("响应形状不对: %v", body)
	}

	// 密码错与用户不存在都是同一句 401（不给枚举机会）
	for name, payload := range map[string]string{
		"密码错":   `{"username":"alice","password":"WrongPass1"}`,
		"用户不存在": `{"username":"nobody","password":"Abcdef12"}`,
	} {
		t.Run(name, func(t *testing.T) {
			rec := doJSON(t, h, http.MethodPost, "/api/v1/auth/login", "application/json", payload, nil)
			if rec.Code != http.StatusUnauthorized {
				t.Fatalf("期望 401，实得 %d", rec.Code)
			}
			if got := detailOf(t, rec); got != detailInvalidLogin {
				t.Errorf("期望 %q，实得 %q", detailInvalidLogin, got)
			}
			// 401 也要带 WWW-Authenticate？生产侧 login 的 HTTPException **没有**带这个头
			// （只有 get_current_user 带）。这里如实断言"没有"，别顺手加。
			if got := rec.Header().Get("WWW-Authenticate"); got != "" {
				t.Errorf("login 的 401 生产侧不带 WWW-Authenticate，实得 %q", got)
			}
		})
	}

	// 缺字段的 400 与 register 同款
	rec = doJSON(t, h, http.MethodPost, "/api/v1/auth/login", "application/json", `{"username":"alice"}`, nil)
	if got := detailOf(t, rec); got != "password: Field required" {
		t.Errorf("期望 %q，实得 %q", "password: Field required", got)
	}
}

// ── me ────────────────────────────────────────────────────────────────

func TestMeHandlerSuccess(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "admin")
	svc := testService(store)
	token, err := IssueAccessToken(svc.Tokens, "alice", "admin")
	if err != nil {
		t.Fatal(err)
	}

	rec := doJSON(t, MeHandler(svc), http.MethodGet, "/api/v1/auth/me", "", "",
		map[string]string{"Authorization": "Bearer " + token})
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，实得 %d：%s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	// CurrentUserResponse 只有两项；多出来的字段（尤其 id 与 created_at）契约里没有
	if len(body) != 2 {
		t.Errorf("me 的响应应恰好两项，实得 %v", body)
	}
	if body["username"] != "alice" || body["role"] != "admin" {
		t.Errorf("身份不对: %v", body)
	}
}

func TestMeHandlerUnauthorizedTexts(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)
	h := MeHandler(svc)

	cases := []struct {
		name       string
		header     string
		wantDetail string
	}{
		// 缺头与"方案不是 bearer"在生产侧是**同一句**（2026-10-12 实测 OAuth2PasswordBearer：
		// Basic 方案也回 "Not authenticated"，不是 "Invalid authentication credentials"）
		{"缺 Authorization", "", detailNotAuthenticated},
		{"Basic 方案", "Basic abc", detailNotAuthenticated},
		{"空值", " ", detailNotAuthenticated},
		// 下面几条都过了 bearer 这一关，失败在令牌校验，所以是另一句
		{"Bearer 后为空", "Bearer ", detailInvalidToken},
		{"只有 Bearer 一个词", "Bearer", detailInvalidToken},
		{"乱码令牌", "Bearer not-a-jwt", detailInvalidToken},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			headers := map[string]string{}
			if c.header != "" {
				headers["Authorization"] = c.header
			}
			rec := doJSON(t, h, http.MethodGet, "/api/v1/auth/me", "", "", headers)
			if rec.Code != http.StatusUnauthorized {
				t.Fatalf("期望 401，实得 %d：%s", rec.Code, rec.Body.String())
			}
			if got := detailOf(t, rec); got != c.wantDetail {
				t.Errorf("detail 不匹配\n  期望 %q\n  实得 %q", c.wantDetail, got)
			}
			// 三处 401 都带 WWW-Authenticate: Bearer（生产侧同款）
			if got := rec.Header().Get("WWW-Authenticate"); got != "Bearer" {
				t.Errorf("WWW-Authenticate 应是 Bearer，实得 %q", got)
			}
		})
	}

	// refresh 当访问凭证用 → 与"令牌无效"同一句（对外不区分失败原因）
	refresh, err := IssueRefreshToken(svc.Tokens, "alice", "user")
	if err != nil {
		t.Fatal(err)
	}
	rec := doJSON(t, h, http.MethodGet, "/api/v1/auth/me", "", "",
		map[string]string{"Authorization": "Bearer " + refresh})
	if rec.Code != http.StatusUnauthorized || detailOf(t, rec) != detailInvalidToken {
		t.Errorf("refresh 当访问凭证应回 401 %q，实得 %d %q",
			detailInvalidToken, rec.Code, detailOf(t, rec))
	}
}

// TestBearerSchemeIsCaseInsensitive 对齐 Starlette 的 `scheme.lower() != "bearer"`：
// 小写 bearer 也算（实测生产侧 200）。Go 若大小写敏感，同一个前端在两侧就会一边通一边不通。
func TestBearerSchemeIsCaseInsensitive(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)
	token, err := IssueAccessToken(svc.Tokens, "alice", "user")
	if err != nil {
		t.Fatal(err)
	}
	for _, scheme := range []string{"Bearer", "bearer", "BEARER", "bEaReR"} {
		rec := doJSON(t, MeHandler(svc), http.MethodGet, "/api/v1/auth/me", "", "",
			map[string]string{"Authorization": scheme + " " + token})
		if rec.Code != http.StatusOK {
			t.Errorf("方案名 %q 应被接受（大小写不敏感），实得 %d：%s", scheme, rec.Code, rec.Body.String())
		}
	}
}

// TestStoreFailureBecomes500WithProductionText 钉住"库故障"的对外形状：
// 500 + "Internal server error"（小写 s），与生产侧 unhandled_error_handler 逐字一致。
// 不能是 401——那会让前端以为登录态过期，把用户踢去登录页，而真正的问题是库连不上。
func TestStoreFailureBecomes500WithProductionText(t *testing.T) {
	svc := testService(&brokenStore{err: errors.New("connection refused")})
	token, err := IssueAccessToken(svc.Tokens, "alice", "user")
	if err != nil {
		t.Fatal(err)
	}

	rec := doJSON(t, MeHandler(svc), http.MethodGet, "/api/v1/auth/me", "", "",
		map[string]string{"Authorization": "Bearer " + token})
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("库故障应 500（不是 401），实得 %d", rec.Code)
	}
	if got := detailOf(t, rec); got != detailInternalError {
		t.Errorf("期望 %q，实得 %q", detailInternalError, got)
	}
	if strings.Contains(rec.Body.String(), "connection refused") {
		t.Error("内部错误细节不该出现在响应体里（只进日志）")
	}

	rec = doJSON(t, LoginHandler(svc), http.MethodPost, "/api/v1/auth/login", "application/json",
		`{"username":"alice","password":"Abcdef12"}`, nil)
	if rec.Code != http.StatusInternalServerError {
		t.Errorf("login 遇到库故障应 500，实得 %d", rec.Code)
	}
}

func TestHandlersDoNotLeakSecretsInResponseBody(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)

	for name, rec := range map[string]*httptest.ResponseRecorder{
		"register": doJSON(t, RegisterHandler(svc), http.MethodPost, "/api/v1/auth/register",
			"application/json", `{"username":"bob","password":"Abcdef12"}`, nil),
		"login": doJSON(t, LoginHandler(svc), http.MethodPost, "/api/v1/auth/login",
			"application/json", `{"username":"alice","password":"Abcdef12"}`, nil),
		"login-fail": doJSON(t, LoginHandler(svc), http.MethodPost, "/api/v1/auth/login",
			"application/json", `{"username":"alice","password":"WrongPass1"}`, nil),
	} {
		body := rec.Body.String()
		if strings.Contains(body, svc.Tokens.Secret) {
			t.Errorf("%s 的响应体里出现了 JWT 密钥", name)
		}
		for _, hash := range []string{store.users["alice"].PasswordHash, store.users["bob"].PasswordHash} {
			if hash != "" && strings.Contains(body, hash) {
				t.Errorf("%s 的响应体里出现了 password_hash", name)
			}
		}
	}
}
