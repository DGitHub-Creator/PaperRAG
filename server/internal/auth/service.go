package auth

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
)

// UserStore 是本包需要的 users 访问面，由 *db.Queries 实现。
//
// 接口定义在**消费方**而不是 db 包，两处理由：一是 Go 的惯例（谁用谁定义，只列自己要的方法），
// 二是 `server/sqlc.yaml` 明确写了 `emit_interface: false`——只有一个实现时，db 包自带的
// Querier 接口是纯粹的间接层（原则④）。这里不同：单测必须在**不连库**的前提下跑完，
// 而 P0-6 的验收命令是 `go test ./internal/auth/...`，本机没有 PG。
type UserStore interface {
	GetUserByUsername(ctx context.Context, username string) (db.User, error)
	GetProfileByUsername(ctx context.Context, username string) (db.GetProfileByUsernameRow, error)
	InsertUser(ctx context.Context, arg db.InsertUserParams) (db.InsertUserRow, error)
	// UpdateUserPasswordByUsername 供改密码路径使用（P0-8 后的设置页）。入参已是哈希串。
	UpdateUserPasswordByUsername(ctx context.Context, arg db.UpdateUserPasswordByUsernameParams) (db.UpdateUserPasswordByUsernameRow, error)
}

// pgUniqueViolation 是 PostgreSQL 的唯一约束冲突码。用户名重复靠它翻译成 409。
const pgUniqueViolation = "23505"

// 业务失败原因。HTTP 状态码与 detail 文案在 handler.go 里映射——文案必须与
// backend/api/auth.py 逐字一致（含"中英文混用"这个现状），所以这里只给语义、不给文案。
var (
	// ErrMissingCredentials 对应 register 的 400 "Username and password are required"。
	ErrMissingCredentials = errors.New("用户名与密码必填")
	// ErrPasswordTooSimple 对应 register 的 400（字符类别不足两类）。
	ErrPasswordTooSimple = errors.New("密码字符类别不足")
	// ErrUsernameTaken 对应 register 的 409。
	ErrUsernameTaken = errors.New("用户名已存在")
	// ErrInvalidCredentials 对应 login 的 401：用户不存在与密码错误**必须是同一个错误**，
	// 否则接口就成了用户名枚举器（生产侧 authenticate_user 对两者都返回 None）。
	ErrInvalidCredentials = errors.New("用户名或密码错误")
	// ErrAdminChannelClosed / ErrAdminCodeMismatch 对应 resolve_role 的两个 403。
	ErrAdminChannelClosed = errors.New("管理员注册通道已关闭")
	ErrAdminCodeMismatch  = errors.New("管理员邀请码错误")
	// ErrUnauthenticated 对应 me 的 401：令牌层任何失败与"用户已不在库里"都折叠成它。
	ErrUnauthenticated = errors.New("令牌无效或已过期")
	// ErrWrongPassword 对应改密码的 400：旧口令对不上。
	// **刻意不是 401**——前端把 401 当"会话过期"来收尾（清 token 并跳登录页），
	// 而"旧口令打错了"不该把用户踢出登录态。语义上它是请求体的校验失败，不是身份失效。
	ErrWrongPassword = errors.New("当前密码不正确")
)

// PasswordTooShortError 带上配置值，因为生产的文案里含这个数字：
// f"Password must be at least {MIN_PASSWORD_LENGTH} characters"。
type PasswordTooShortError struct{ Min int }

func (e PasswordTooShortError) Error() string {
	return fmt.Sprintf("密码长度不足 %d", e.Min)
}

// RegisterInput 是注册请求。Role 与 AdminCode 用指针，为的是区分
// "客户端没给"与"客户端给了空串"——生产侧 `role: str | None = "user"`，
// 而 `resolve_role` 里 `(requested_role or "user")` 把 None 与 "" 都当 user，
// 所以这个区分在 role 上不影响结果；但 admin_code 的 None 与 "" 同样都走"不匹配"，
// 用指针只是为了让 handler 解码时能如实反映请求里有没有这个键。
type RegisterInput struct {
	Username  string
	Password  string
	Role      *string
	AdminCode *string
}

// AuthResult 是 register / login 的成功产物，对应契约的 AuthResponse。
type AuthResult struct {
	AccessToken  string
	RefreshToken string
	// TokenType 固定 "bearer"：生产侧 AuthResponse 的这个字段有默认值且从不变，
	// 但它**确实出现在响应体里**（pydantic 会序列化带默认值的字段），所以 Go 也必须给。
	TokenType string
	Username  string
	Role      string
}

// Identity 是 me 的成功产物，对应契约的 CurrentUserResponse（只有两项）。
type Identity struct {
	// ID 是 users.id。响应里**不带**它（契约只有 username/role），
	// 但依赖用户的其它面（如偏好读写）需要它来定位行，所以放在这里共享同一次查库。
	ID       int32
	Username string
	// Role 一律取自数据库行，不采信令牌里的 role 声明——生产侧
	// get_user_from_bearer_token 的注释写明了理由：避免降级/改名后旧令牌继续持有旧权限。
	Role string
}

// Service 是认证切片的业务面：不碰 HTTP，也不碰环境变量。
type Service struct {
	Store  UserStore
	Tokens TokenConfig
	// PBKDF2Rounds 是**新写入**哈希的迭代数（对齐 PASSWORD_PBKDF2_ROUNDS，默认 310000）。
	// 验证旧哈希时用的是哈希串里自带的那个，与本字段无关。
	PBKDF2Rounds int
	// AdminInviteCode 为空表示管理员注册通道关闭。
	AdminInviteCode string
	// MinPasswordLength 为 0 时关闭长度与字符类别两条校验（生产侧同款开关：
	// `if MIN_PASSWORD_LENGTH > 0 and ...`）。
	MinPasswordLength int
	// Prefs 是偏好读写面（见 preferences.go）。为 nil 时偏好路由回 500：
	// 单测与不面向浏览器的进程不需要它，故不放进 NewService 的参数表。
	Prefs  PrefsStore
	Logger *slog.Logger
}

// NewService 组装 Service 并给零值兜底，省得每个调用方都写一遍 if nil。
func NewService(store UserStore, tokens TokenConfig, rounds int, adminInviteCode string, minPasswordLength int, logger *slog.Logger) *Service {
	if logger == nil {
		logger = slog.Default()
	}
	if rounds <= 0 {
		rounds = 310000
	}
	return &Service{
		Store:             store,
		Tokens:            tokens,
		PBKDF2Rounds:      rounds,
		AdminInviteCode:   adminInviteCode,
		MinPasswordLength: minPasswordLength,
		Logger:            logger,
	}
}

// Register 对齐 backend/api/auth.py:register，**含它的校验先后顺序**。
//
// 顺序这件事不是洁癖：生产侧先查用户名是否已存在（409），再解析角色（403）。
// 所以"用户名重复 + 邀请码错误"同时成立时，答案是 409 而不是 403。
// 下面既保留了那次预查（为了顺序一致），也保留了 insert 的唯一约束翻译
// （为了并发正确）——预查与插入之间的窗口里别人可能刚好插入同名用户，
// 只靠预查就是并发下的假成功（users.sql 里那条注释说的就是这个）。
func (s *Service) Register(ctx context.Context, in RegisterInput) (*AuthResult, error) {
	// strip 是生产侧的行为：`username = (request.username or "").strip()`。
	// 所以 " alice " 注册出来的用户名是 "alice"。
	username := strings.TrimSpace(in.Username)
	password := strings.TrimSpace(in.Password)
	if username == "" || password == "" {
		return nil, ErrMissingCredentials
	}

	// ⚠️ 长度按**码点**算，不是字节：生产侧是 `len(password)`，Python 的 str 长度就是码点。
	// 用 len(password)（字节）会让 "密码abc12" 这种含多字节字符的口令在 Go 侧被判得更严，
	// 而同一个口令 Python 放行——那就是"注册在两边结论不同"的 bug。
	if s.MinPasswordLength > 0 && utf8.RuneCountInString(password) < s.MinPasswordLength {
		return nil, PasswordTooShortError{Min: s.MinPasswordLength}
	}
	// 与 Python 的 [a-z]/[A-Z]/\d 一致，数字类别包含 Unicode Nd。
	if s.MinPasswordLength > 0 && passwordCategories(password) < 2 {
		return nil, ErrPasswordTooSimple
	}

	if _, err := s.Store.GetProfileByUsername(ctx, username); err == nil {
		return nil, ErrUsernameTaken
	} else if !errors.Is(err, pgx.ErrNoRows) {
		return nil, fmt.Errorf("预查用户名失败: %w", err)
	}

	role, err := s.resolveRole(in.Role, in.AdminCode)
	if err != nil {
		return nil, err
	}

	hash, err := HashPassword(password, s.PBKDF2Rounds)
	if err != nil {
		return nil, err
	}

	// created_at 显式给 UTC 值，不吃库侧 DEFAULT now()：now() 取的是会话时区，
	// 而 05 §4 的时间列语义审计还没做完（users.sql 里那条注释记了同一件事）。
	row, err := s.Store.InsertUser(ctx, db.InsertUserParams{
		Username:     username,
		PasswordHash: hash,
		Role:         role,
		CreatedAt:    pgtype.Timestamp{Time: time.Now().UTC(), Valid: true},
	})
	if err != nil {
		if isUniqueViolation(err) {
			return nil, ErrUsernameTaken
		}
		return nil, fmt.Errorf("写入用户失败: %w", err)
	}

	result, err := s.issue(row.Username, row.Role)
	if err != nil {
		return nil, err
	}
	// 只记用户名与角色：口令与哈希一律不进日志（生产侧同样只记这两项）。
	s.Logger.Info("用户注册成功", "username", row.Username, "role", row.Role)
	return result, nil
}

// Login 对齐 backend/api/auth.py:login 与 core/auth.py:authenticate_user。
//
// 两处刻意与 register **不同**，都是照抄生产侧：
//  1. 不 strip。login 直接把 request.username / request.password 交给 authenticate_user，
//     所以用 " alice " 登录会失败（即使注册时写进去的是 "alice"）。这个不一致是现状，
//     Go 照抄——"顺手修好"会让同一份凭据在两侧结论不同。
//  2. 用户不存在与密码错误返回**同一个**错误，不给外部区分的机会。
func (s *Service) Login(ctx context.Context, username, password string) (*AuthResult, error) {
	user, err := s.Store.GetUserByUsername(ctx, username)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			s.Logger.Info("登录失败：用户不存在", "username", username)
			return nil, ErrInvalidCredentials
		}
		return nil, fmt.Errorf("查询用户失败: %w", err)
	}

	// bcrypt 族 Go 验不了（见 password.go 的 FamilyBCrypt）。对外仍是同一句 401，
	// 但对内必须**看得见**：接管 users 之后若库里还有这类行，这批人会被静默锁死，
	// 而唯一的线索就是这条日志。原真库已随 Docker 数据卷消失（台账 C20），
	// "到底还有没有这类行"已无法离线核查，所以 P1 接管前的前置动作是跑
	// `export_pbkdf2_golden.py --from-db` 看 families 里有没有 bcrypt。
	if family := HashFamily(user.PasswordHash); family != FamilyPBKDF2 {
		s.Logger.Warn("这行的 password_hash 不是 pbkdf2_sha256 族，Go 验不了；用户会被锁死，需先强制改密",
			"username", user.Username, "family", family)
	}

	if !VerifyPassword(password, user.PasswordHash) {
		s.Logger.Info("登录失败：密码错误", "username", username)
		return nil, ErrInvalidCredentials
	}

	result, err := s.issue(user.Username, user.Role)
	if err != nil {
		return nil, err
	}
	s.Logger.Info("用户登录成功", "username", user.Username)
	return result, nil
}

// CurrentUser 对齐 core/auth.py:get_user_from_bearer_token + api/auth.py:me。
//
// 令牌层的三项校验在 ParseAccessToken 里，第四项（用户是否仍在库里）在这里回库。
// 这一步**不能省**：jwt_golden.json 的 unknown-user 向量钉的就是它——
// 一枚签名、type、exp 全对的令牌，只要用户已经不在库里就必须拒。
// 角色也在这一步从库里取，令牌里的 role 声明从头到尾没被读过。
func (s *Service) CurrentUser(ctx context.Context, bearerToken string) (*Identity, error) {
	username, err := ParseAccessToken(s.Tokens, bearerToken)
	if err != nil {
		// 具体原因只进日志：对外一律同一句 401，不泄露"是签名错还是过期还是类型不对"。
		s.Logger.Warn("令牌校验失败", "reason", err.Error())
		return nil, ErrUnauthenticated
	}

	profile, err := s.Store.GetProfileByUsername(ctx, username)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			s.Logger.Warn("令牌有效但用户已不在库里", "username", username)
			return nil, ErrUnauthenticated
		}
		return nil, fmt.Errorf("查询用户身份失败: %w", err)
	}
	return &Identity{ID: profile.ID, Username: profile.Username, Role: profile.Role}, nil
}

// ChangePassword 校验旧口令后写入新口令的哈希（设置页的「改密码」）。
//
// 与 register 的一处刻意差别：新口令**不 strip**。register 会 strip 是生产侧的现状
// （Go 照抄是为了两侧同一份凭据结论相同），而本端点没有需要对齐的 Python 面——
// 口令是不透明串，静默去掉首尾空格等于替用户改密码。
//
// 旧口令错回 ErrWrongPassword（400），**不是 401**：前端把 401 当"会话过期"收尾，
// 而"旧口令打错了"不该把用户踢出登录态（理由见 service.go 顶部那条注释）。
func (s *Service) ChangePassword(ctx context.Context, bearerToken, oldPassword, newPassword string) error {
	identity, err := s.CurrentUser(ctx, bearerToken)
	if err != nil {
		return err
	}

	user, err := s.Store.GetUserByUsername(ctx, identity.Username)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ErrUnauthenticated
		}
		return fmt.Errorf("查询用户失败: %w", err)
	}
	if family := HashFamily(user.PasswordHash); family != FamilyPBKDF2 {
		s.Logger.Warn("这行的 password_hash 不是 pbkdf2_sha256 族，Go 验不了旧口令；需走管理侧重置",
			"username", user.Username, "family", family)
	}
	if !VerifyPassword(oldPassword, user.PasswordHash) {
		s.Logger.Info("改密码失败：当前密码不正确", "username", user.Username)
		return ErrWrongPassword
	}

	// 新口令走与 register 同一套规则（长度按码点 + 至少两类字符），开关同为 MinPasswordLength。
	// ⚠️ 长度按码点，不是字节——理由与 register 里那条注释相同。
	if s.MinPasswordLength > 0 && utf8.RuneCountInString(newPassword) < s.MinPasswordLength {
		return PasswordTooShortError{Min: s.MinPasswordLength}
	}
	if s.MinPasswordLength > 0 && passwordCategories(newPassword) < 2 {
		return ErrPasswordTooSimple
	}

	hash, err := HashPassword(newPassword, s.PBKDF2Rounds)
	if err != nil {
		return err
	}
	if _, err := s.Store.UpdateUserPasswordByUsername(ctx, db.UpdateUserPasswordByUsernameParams{
		Username:     user.Username,
		PasswordHash: hash,
	}); err != nil {
		return fmt.Errorf("写入新口令失败: %w", err)
	}
	s.Logger.Info("密码已更新", "username", user.Username)
	return nil
}

// resolveRole 对齐 core/auth.py:resolve_role。
//
// 注意它**不做枚举校验**：生产侧 `role: str | None`，任意字符串都收，
// 非 "admin" 的一律折叠成 "user"（openapi.yaml 的 Role 枚举描述的是值域，
// 不是入参校验；实测 `role: "root"` 返回 200）。Go 同构，否则同一个请求两侧结论不同。
//
// 邀请码用 `==` 比对，与生产侧一致（那边也是 `admin_code == ADMIN_INVITE_CODE`，
// 非常量时间）。这里刻意不"顺手改严"：改了就成了两侧行为分歧，而邀请码的时序侧信道
// 要真利用，得先能无限次请求注册接口——那是限流的活（P1）。
func (s *Service) resolveRole(requested, adminCode *string) (string, error) {
	role := "user"
	if requested != nil {
		role = *requested
	}
	role = strings.ToLower(strings.TrimSpace(role))
	if role != "admin" {
		return "user", nil
	}
	if s.AdminInviteCode == "" {
		s.Logger.Warn("收到管理员注册请求，但系统未配置 ADMIN_INVITE_CODE")
		return "", ErrAdminChannelClosed
	}
	if adminCode != nil && *adminCode == s.AdminInviteCode {
		s.Logger.Info("管理员邀请码验证通过，分配 admin 角色")
		return "admin", nil
	}
	// 不回显收到的邀请码，避免凭据进日志（生产侧同一句注释）。
	s.Logger.Warn("管理员邀请码验证失败")
	return "", ErrAdminCodeMismatch
}

func (s *Service) issue(username, role string) (*AuthResult, error) {
	access, err := IssueAccessToken(s.Tokens, username, role)
	if err != nil {
		return nil, fmt.Errorf("签发 access token 失败: %w", err)
	}
	refresh, err := IssueRefreshToken(s.Tokens, username, role)
	if err != nil {
		return nil, fmt.Errorf("签发 refresh token 失败: %w", err)
	}
	return &AuthResult{
		AccessToken:  access,
		RefreshToken: refresh,
		TokenType:    "bearer",
		Username:     username,
		Role:         role,
	}, nil
}

// passwordCategories 数口令命中了 ASCII 小写 / 大写 / 数字三类里的几类，
// 对齐生产侧那三个 re.search。生产侧要求至少两类（且只在 MIN_PASSWORD_LENGTH > 0 时生效）。
func passwordCategories(password string) int {
	var lower, upper, digit bool
	for _, c := range password {
		switch {
		case c >= 'a' && c <= 'z':
			lower = true
		case c >= 'A' && c <= 'Z':
			upper = true
		case unicode.IsDigit(c):
			digit = true
		}
	}
	n := 0
	for _, hit := range []bool{lower, upper, digit} {
		if hit {
			n++
		}
	}
	return n
}

func isUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == pgUniqueViolation
}
