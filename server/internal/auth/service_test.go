package auth

import (
	"context"
	"errors"
	"log/slog"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
)

// fakeStore 是 UserStore 的内存实现，让 P0-6 的验收命令 `go test ./internal/auth/...`
// 在本机没有 PG 的前提下也能跑完。它同时记录**哪条查询被调过**，
// 因为"/me 不该碰到 password_hash"这种性质只能靠调用记录来断言。
type fakeStore struct {
	mu sync.Mutex
	// users 按用户名索引。PasswordHash 为空表示"这行不该被读到哈希"。
	users           map[string]db.User
	insertErr       error
	byUsernameCalls int
	profileCalls    int
	insertCalls     int
	lastInsert      db.InsertUserParams
	// 改密码路径的调用记录：新哈希落进 users，同时留一份给用例断言
	// （"重名 409 先于邀请码 403"那种顺序性质靠计数，改密码靠 lastPasswordHash 验真写进去了）。
	updatePasswordCalls int
	lastPasswordHash    string
}

func newFakeStore() *fakeStore {
	return &fakeStore{users: map[string]db.User{}}
}

// seed 放一个已存在的用户。hash 为空时用 pbkdf2 现算一个，省得每条用例都写一长串。
func (f *fakeStore) seed(t *testing.T, username, password, role string) {
	t.Helper()
	hash, err := HashPassword(password, 40000)
	if err != nil {
		t.Fatalf("造种子用户失败: %v", err)
	}
	f.users[username] = db.User{
		ID:           int32(len(f.users) + 1),
		Username:     username,
		PasswordHash: hash,
		Role:         role,
		CreatedAt:    pgtype.Timestamp{Time: time.Now().UTC(), Valid: true},
	}
}

func (f *fakeStore) GetUserByUsername(_ context.Context, username string) (db.User, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.byUsernameCalls++
	user, ok := f.users[username]
	if !ok {
		return db.User{}, pgx.ErrNoRows
	}
	return user, nil
}

func (f *fakeStore) GetProfileByUsername(_ context.Context, username string) (db.GetProfileByUsernameRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.profileCalls++
	user, ok := f.users[username]
	if !ok {
		return db.GetProfileByUsernameRow{}, pgx.ErrNoRows
	}
	return db.GetProfileByUsernameRow{
		ID:        user.ID,
		Username:  user.Username,
		Role:      user.Role,
		CreatedAt: user.CreatedAt,
	}, nil
}

func (f *fakeStore) InsertUser(_ context.Context, arg db.InsertUserParams) (db.InsertUserRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.insertCalls++
	f.lastInsert = arg
	if f.insertErr != nil {
		return db.InsertUserRow{}, f.insertErr
	}
	if _, ok := f.users[arg.Username]; ok {
		return db.InsertUserRow{}, &pgconn.PgError{Code: pgUniqueViolation}
	}
	f.users[arg.Username] = db.User{
		ID:           int32(len(f.users) + 1),
		Username:     arg.Username,
		PasswordHash: arg.PasswordHash,
		Role:         arg.Role,
		CreatedAt:    arg.CreatedAt,
	}
	return db.InsertUserRow{
		ID:        int32(len(f.users)),
		Username:  arg.Username,
		Role:      arg.Role,
		CreatedAt: arg.CreatedAt,
	}, nil
}

func (f *fakeStore) UpdateUserPasswordByUsername(_ context.Context, arg db.UpdateUserPasswordByUsernameParams) (db.UpdateUserPasswordByUsernameRow, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.updatePasswordCalls++
	f.lastPasswordHash = arg.PasswordHash
	user, ok := f.users[arg.Username]
	if !ok {
		return db.UpdateUserPasswordByUsernameRow{}, pgx.ErrNoRows
	}
	user.PasswordHash = arg.PasswordHash
	f.users[arg.Username] = user
	return db.UpdateUserPasswordByUsernameRow{ID: user.ID, Username: user.Username, Role: user.Role}, nil
}

func testService(store UserStore) *Service {
	return NewService(store,
		TokenConfig{Secret: "test-secret", ExpireMinutes: 60, RefreshExpireDays: 30},
		40000, "", 8, discardLogger())
}

func discardLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(discardWriter{}, nil))
}

type discardWriter struct{}

func (discardWriter) Write(p []byte) (int, error) { return len(p), nil }

// ── register ──────────────────────────────────────────────────────────

func TestRegisterSucceedsAndStoresAVerifiableHash(t *testing.T) {
	store := newFakeStore()
	svc := testService(store)

	result, err := svc.Register(context.Background(), RegisterInput{Username: "alice", Password: "Abcdef12"})
	if err != nil {
		t.Fatalf("注册失败: %v", err)
	}
	if result.Username != "alice" || result.Role != "user" {
		t.Errorf("返回的身份不对: %+v", result)
	}
	if result.TokenType != "bearer" {
		t.Errorf("token_type 应固定为 bearer（生产侧 AuthResponse 的默认值，且确实出现在响应体里），实得 %q", result.TokenType)
	}
	if result.AccessToken == "" || result.RefreshToken == "" {
		t.Error("注册即登录：两个 token 都必须返回")
	}

	stored := store.users["alice"]
	if !VerifyPassword("Abcdef12", stored.PasswordHash) {
		t.Error("存进去的哈希验不过刚注册的口令")
	}
	if !stored.CreatedAt.Valid {
		t.Error("created_at 必须显式给值（不吃库侧 DEFAULT now()，那个取会话时区）")
	}
	if stored.CreatedAt.Time.Location() != time.UTC {
		t.Errorf("created_at 应是 UTC，实得时区 %v", stored.CreatedAt.Time.Location())
	}
	// refresh 不能当 access 用
	if _, err := ParseAccessToken(svc.Tokens, result.RefreshToken); !errors.Is(err, ErrTokenType) {
		t.Errorf("返回的 refresh_token 被当成访问凭证接受了: %v", err)
	}
	if username, err := ParseAccessToken(svc.Tokens, result.AccessToken); err != nil || username != "alice" {
		t.Errorf("返回的 access_token 自验不过: username=%q err=%v", username, err)
	}
}

func TestRegisterStripsWhitespaceLikeProduction(t *testing.T) {
	store := newFakeStore()
	svc := testService(store)

	// 生产侧：username = (request.username or "").strip()
	if _, err := svc.Register(context.Background(), RegisterInput{Username: "  bob  ", Password: "Abcdef12"}); err != nil {
		t.Fatalf("注册失败: %v", err)
	}
	if _, ok := store.users["bob"]; !ok {
		t.Errorf("用户名应被 strip 成 bob，实际存进去的是: %v", keys(store.users))
	}
	// strip 之后为空 → 必填校验
	if _, err := svc.Register(context.Background(), RegisterInput{Username: "   ", Password: "Abcdef12"}); !errors.Is(err, ErrMissingCredentials) {
		t.Errorf("全空格用户名应报 %v，实得 %v", ErrMissingCredentials, err)
	}
	if _, err := svc.Register(context.Background(), RegisterInput{Username: "carol", Password: "  "}); !errors.Is(err, ErrMissingCredentials) {
		t.Errorf("全空格口令应报 %v，实得 %v", ErrMissingCredentials, err)
	}
}

// TestRegisterPasswordLengthCountsRunesNotBytes 钉住一条很容易写错的分歧：
// 生产侧是 `len(password) < MIN_PASSWORD_LENGTH`，Python 的 str 长度是**码点**；
// Go 的 len(string) 是**字节**。用字节数会让含中文的口令在 Go 侧被判得更严——
// 同一个口令 Python 放行、Go 拒绝，那就是"注册在两边结论不同"的 bug。
func TestRegisterPasswordLengthCountsRunesNotBytes(t *testing.T) {
	store := newFakeStore()
	svc := testService(store)

	// 8 个码点，但 UTF-8 下是 22 字节。按字节算会通过、按码点算刚好卡在门槛上。
	password := "密码口令八字节测试" // 9 个码点 / 27 字节
	if got := len(password); got <= 9 {
		t.Fatalf("这条用例的前提不成立：字节数应远大于码点数，实得 %d 字节", got)
	}
	// 9 个码点 ≥ 8，且含小写字母？不含——所以类别校验会拦。补一个字母进去。
	password = "密码口令测试ab1" // 8 个码点：6 个汉字 + a + b + 1 → 类别命中小写与数字两类
	if _, err := svc.Register(context.Background(), RegisterInput{Username: "dave", Password: password}); err != nil {
		t.Fatalf("8 个码点（含两类字符）应通过，实得 %v —— 长度是不是按字节算了？", err)
	}

	// 7 个码点、字节数远超 8：必须被长度校验拦住
	short := "密码口令ab1" // 7 个码点
	if _, err := svc.Register(context.Background(), RegisterInput{Username: "erin", Password: short}); !errors.As(err, &PasswordTooShortError{}) {
		t.Errorf("7 个码点应报长度不足，实得 %v —— 长度是不是按字节算了？", err)
	}
}

func TestRegisterPasswordNeedsTwoCharacterCategories(t *testing.T) {
	store := newFakeStore()
	svc := testService(store)

	cases := map[string]bool{
		"abcdefgh":     false, // 只有小写
		"ABCDEFGH":     false, // 只有大写
		"12345678":     false, // 只有数字
		"abcdefg1":     true,  // 小写 + 数字
		"Abcdefgh":     true,  // 大写 + 小写
		"ABCDEFG1":     true,  // 大写 + 数字
		"Abcdefg1":     true,  // 三类
		"!!!!!!!!":     false, // 符号不算任何一类
		"abcdefg1!!!!": true,  // 符号不影响已有的两类
	}
	i := 0
	for password, shouldPass := range cases {
		i++
		username := "cat" + string(rune('a'+i))
		_, err := svc.Register(context.Background(), RegisterInput{Username: username, Password: password})
		tooSimple := errors.Is(err, ErrPasswordTooSimple)
		if shouldPass && err != nil {
			t.Errorf("口令 %q 应通过，实得 %v", password, err)
		}
		if !shouldPass && !tooSimple {
			t.Errorf("口令 %q 应因字符类别不足被拒，实得 %v", password, err)
		}
	}
}

// TestRegisterChecksDuplicateBeforeRole 钉住校验**顺序**：
// 生产侧先查用户名是否存在（409）再解析角色（403），所以"用户名重复 + 邀请码错误"
// 同时成立时答案是 409。顺序反过来不只是文案问题——409 会泄露用户名是否存在，
// 而 403 不会，所以哪边先答等于选择了泄露哪一条信息，两侧必须一致。
func TestRegisterChecksDuplicateBeforeRole(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "taken", "Abcdef12", "user")
	svc := NewService(store, TokenConfig{Secret: "s", ExpireMinutes: 60, RefreshExpireDays: 30},
		40000, "correct-horse", 8, discardLogger())

	wrongCode := "wrong"
	admin := "admin"
	_, err := svc.Register(context.Background(), RegisterInput{
		Username: "taken", Password: "Abcdef12", Role: &admin, AdminCode: &wrongCode,
	})
	if !errors.Is(err, ErrUsernameTaken) {
		t.Errorf("重复用户名应先于邀请码校验命中，期望 %v，实得 %v", ErrUsernameTaken, err)
	}
}

func TestRegisterTranslatesUniqueViolationTo409(t *testing.T) {
	store := newFakeStore()
	svc := testService(store)
	// 预查通过、插入时才撞唯一约束（并发窗口）：靠 23505 翻译，不能变成 500。
	store.insertErr = &pgconn.PgError{Code: pgUniqueViolation}
	if _, err := svc.Register(context.Background(), RegisterInput{Username: "frank", Password: "Abcdef12"}); !errors.Is(err, ErrUsernameTaken) {
		t.Errorf("唯一约束冲突应翻译成 %v，实得 %v", ErrUsernameTaken, err)
	}

	store.insertErr = &pgconn.PgError{Code: "23503"} // 外键冲突，不是重名
	if _, err := svc.Register(context.Background(), RegisterInput{Username: "frank2", Password: "Abcdef12"}); errors.Is(err, ErrUsernameTaken) {
		t.Error("别的 PG 错误码不该被当成用户名重复")
	}
	store.insertErr = errors.New("connection refused")
	if _, err := svc.Register(context.Background(), RegisterInput{Username: "frank3", Password: "Abcdef12"}); errors.Is(err, ErrUsernameTaken) {
		t.Error("连接失败不该被当成用户名重复（那会让前端提示「换个用户名」，而真正的问题是库连不上）")
	}
}

func TestResolveRoleFoldsAnythingButAdmin(t *testing.T) {
	store := newFakeStore()
	svc := NewService(store, TokenConfig{Secret: "s", ExpireMinutes: 60}, 40000, "correct-horse", 8, discardLogger())

	str := func(s string) *string { return &s }
	cases := []struct {
		name      string
		role      *string
		adminCode *string
		wantRole  string
		wantErr   error
	}{
		{"没给 role", nil, nil, "user", nil},
		{"给了空串", str(""), nil, "user", nil},
		// ⚠️ 契约里 role 是 enum [user, admin]，但生产侧 `role: str | None`，
		// 实测 "root" 返回 200 并被折叠成 user。Go 同构：枚举描述的是值域，不是入参校验。
		{"非法枚举值被折叠", str("root"), nil, "user", nil},
		{"大写 ADMIN 加空格", str("  ADMIN "), str("correct-horse"), "admin", nil},
		{"admin 但邀请码错", str("admin"), str("nope"), "", ErrAdminCodeMismatch},
		{"admin 但没给邀请码", str("admin"), nil, "", ErrAdminCodeMismatch},
		{"admin 且邀请码为空串", str("admin"), str(""), "", ErrAdminCodeMismatch},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, err := svc.resolveRole(c.role, c.adminCode)
			if !errors.Is(err, c.wantErr) {
				t.Fatalf("期望 err=%v，实得 %v", c.wantErr, err)
			}
			if got != c.wantRole {
				t.Errorf("期望角色 %q，实得 %q", c.wantRole, got)
			}
		})
	}
}

func TestResolveRoleAdminChannelClosedWhenNoInviteCode(t *testing.T) {
	store := newFakeStore()
	// AdminInviteCode 为空 → 管理员注册通道关闭（403），而不是"邀请码错误"。
	// 两句话在前端是不同提示，混淆会让人以为是自己输错了。
	svc := NewService(store, TokenConfig{Secret: "s", ExpireMinutes: 60}, 40000, "", 8, discardLogger())
	admin := "admin"
	code := "anything"
	if _, err := svc.resolveRole(&admin, &code); !errors.Is(err, ErrAdminChannelClosed) {
		t.Errorf("未配置邀请码时应报 %v，实得 %v", ErrAdminChannelClosed, err)
	}
}

// ── login ─────────────────────────────────────────────────────────────

func TestLoginSucceedsAndIssuesTokensForTheDatabaseRole(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "admin-user", "Abcdef12", "admin")
	svc := testService(store)

	result, err := svc.Login(context.Background(), "admin-user", "Abcdef12")
	if err != nil {
		t.Fatalf("登录失败: %v", err)
	}
	if result.Role != "admin" {
		t.Errorf("角色应取自库里的行，实得 %q", result.Role)
	}
	identity, err := svc.CurrentUser(context.Background(), result.AccessToken)
	if err != nil {
		t.Fatalf("刚签的令牌验不过: %v", err)
	}
	if identity.Username != "admin-user" || identity.Role != "admin" {
		t.Errorf("me 回显的身份不对: %+v", identity)
	}
}

// TestLoginDoesNotDistinguishUnknownUserFromWrongPassword 是安全性质，不只是行为对齐：
// 两者返回**同一个**错误值，接口就不能被当作用户名枚举器。
func TestLoginDoesNotDistinguishUnknownUserFromWrongPassword(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)

	_, errUnknown := svc.Login(context.Background(), "nobody", "Abcdef12")
	_, errWrong := svc.Login(context.Background(), "alice", "WrongPass1")
	if !errors.Is(errUnknown, ErrInvalidCredentials) || !errors.Is(errWrong, ErrInvalidCredentials) {
		t.Fatalf("两种失败都应是 %v，实得 %v / %v", ErrInvalidCredentials, errUnknown, errWrong)
	}
	if errUnknown.Error() != errWrong.Error() {
		t.Errorf("两种失败的错误文本必须相同，实得 %q / %q", errUnknown.Error(), errWrong.Error())
	}
}

// TestLoginDoesNotStrip 钉住 register 与 login 的一处**故意不一致**：
// 注册时 strip、登录时不 strip（生产侧 login 直接把原值交给 authenticate_user）。
// 所以用 " alice " 登录会失败，即使注册时写进去的是 "alice"。
// 这是现状而不是缺陷修复对象：Go"顺手修好"就会让同一份凭据在两侧结论不同。
func TestLoginDoesNotStrip(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)

	if _, err := svc.Login(context.Background(), " alice ", "Abcdef12"); !errors.Is(err, ErrInvalidCredentials) {
		t.Errorf("登录不该 strip：带空格的用户名应失败，实得 %v", err)
	}
	if _, err := svc.Login(context.Background(), "alice", " Abcdef12 "); !errors.Is(err, ErrInvalidCredentials) {
		t.Errorf("登录不该 strip：带空格的口令应失败，实得 %v", err)
	}
	if _, err := svc.Login(context.Background(), "alice", "Abcdef12"); err != nil {
		t.Errorf("原样登录应成功，实得 %v", err)
	}
}

// TestLoginSurfacesBCryptLockoutRisk 钉住"这批人会被锁死"必须**看得见**。
// 对外仍是同一句 401（不泄露区别），但日志里要有一条 WARN：
// 原真库已随 Docker 数据卷消失（台账 C20），"库里还有没有 bcrypt 族"已无法离线核查，
// 接管 users 之后这条日志是唯一的线索。
func TestLoginSurfacesBCryptLockoutRisk(t *testing.T) {
	store := newFakeStore()
	store.users["legacy"] = db.User{
		ID: 7, Username: "legacy",
		PasswordHash: "$2b$12$abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH",
		Role:         "user",
	}
	capture := &recordCapture{}
	svc := NewService(store, TokenConfig{Secret: "s", ExpireMinutes: 60}, 40000, "", 8,
		slog.New(capture))

	if _, err := svc.Login(context.Background(), "legacy", "whatever"); !errors.Is(err, ErrInvalidCredentials) {
		t.Errorf("bcrypt 族应验不过并返回 %v，实得 %v", ErrInvalidCredentials, err)
	}
	var found bool
	for _, r := range capture.snapshot() {
		if r.Level < slog.LevelWarn {
			continue
		}
		r.Attrs(func(a slog.Attr) bool {
			// 断言的是 family 这个**属性值**而不是消息文本：Family.String() 必须
			// 让日志里出现 "bcrypt" 而不是数字 1，否则这条线索在告警里等于没有信息。
			if a.Key == "family" && a.Value.String() == "bcrypt" {
				found = true
			}
			return true
		})
	}
	if !found {
		t.Errorf("应有一条 WARN 带 family=bcrypt，点明这行 Go 验不了；实得日志: %s", capture.dump())
	}
}

func TestLoginPropagatesStoreFailure(t *testing.T) {
	// 库连不上不能伪装成"密码错"：那会让用户去改密码，而真正的问题是数据库。
	// 非 ErrNoRows 的错误必须原样冒泡（handler 会翻成 500）。
	store := &brokenStore{err: errors.New("connection refused")}
	svc := testService(store)

	_, err := svc.Login(context.Background(), "alice", "Abcdef12")
	if err == nil || errors.Is(err, ErrInvalidCredentials) {
		t.Errorf("库故障应原样冒泡，实得 %v", err)
	}
	if _, err := svc.Register(context.Background(), RegisterInput{Username: "alice", Password: "Abcdef12"}); err == nil || errors.Is(err, ErrUsernameTaken) {
		t.Errorf("预查阶段的库故障应原样冒泡，实得 %v", err)
	}
	token, tokenErr := IssueAccessToken(svc.Tokens, "alice", "user")
	if tokenErr != nil {
		t.Fatal(tokenErr)
	}
	if _, err := svc.CurrentUser(context.Background(), token); err == nil || errors.Is(err, ErrUnauthenticated) {
		t.Errorf("me 路径的库故障应原样冒泡（不是 401），实得 %v", err)
	}
}

// ── me / CurrentUser ──────────────────────────────────────────────────

// TestCurrentUserRejectsVanishedUser 是 jwt_golden.json 里 rejected_by="database"
// 那条向量（unknown-user）在 service 层的对应断言：令牌签名、type、exp 全对，
// 但用户已不在库里 → 必须拒。令牌层放行、库层拒绝，两层各管一半。
func TestCurrentUserRejectsVanishedUser(t *testing.T) {
	store := newFakeStore()
	svc := testService(store)
	token, err := IssueAccessToken(svc.Tokens, "ghost", "user")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ParseAccessToken(svc.Tokens, token); err != nil {
		t.Fatalf("前提不成立：这枚令牌在令牌层应当是合法的，实得 %v", err)
	}
	if _, err := svc.CurrentUser(context.Background(), token); !errors.Is(err, ErrUnauthenticated) {
		t.Errorf("用户已不在库里应报 %v，实得 %v", ErrUnauthenticated, err)
	}
}

// TestCurrentUserTakesRoleFromDatabaseNotFromToken 是 P0-6 的核心安全性质：
// 令牌里的 role 声明**从头到尾没被读过**。否则用户被降级后，旧令牌仍带着 admin。
func TestCurrentUserTakesRoleFromDatabaseNotFromToken(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "downgraded", "Abcdef12", "user") // 库里现在是 user
	svc := testService(store)

	// 手工签一枚声称自己是 admin 的令牌（模拟降级前签发的旧令牌）
	token, err := IssueAccessToken(svc.Tokens, "downgraded", "admin")
	if err != nil {
		t.Fatal(err)
	}
	identity, err := svc.CurrentUser(context.Background(), token)
	if err != nil {
		t.Fatalf("令牌合法，应通过: %v", err)
	}
	if identity.Role != "user" {
		t.Errorf("角色必须取自数据库（期望 user），实得 %q —— 令牌里的 role 声明被采信了", identity.Role)
	}
}

func TestCurrentUserRejectsRefreshAndGarbage(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)

	refresh, err := IssueRefreshToken(svc.Tokens, "alice", "user")
	if err != nil {
		t.Fatal(err)
	}
	for name, token := range map[string]string{
		"refresh 当访问凭证": refresh,
		"空串":            "",
		"乱码":            "not-a-jwt",
		"别的密钥签的":        mustIssueWith(t, TokenConfig{Secret: "other-secret", ExpireMinutes: 60}, "alice"),
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := svc.CurrentUser(context.Background(), token); !errors.Is(err, ErrUnauthenticated) {
				t.Errorf("应报 %v，实得 %v", ErrUnauthenticated, err)
			}
		})
	}
}

// TestMePathNeverReadsPasswordHash 是结构性保证的机检：me 只该走
// GetProfileByUsername（不选 password_hash 那条），一次都不该碰 GetUserByUsername。
// 光看代码不够——将来有人在 me 里换成"能查到整行"的那条查询，这条用例就会红。
func TestMePathNeverReadsPasswordHash(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)

	token, err := IssueAccessToken(svc.Tokens, "alice", "user")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := svc.CurrentUser(context.Background(), token); err != nil {
		t.Fatal(err)
	}
	if store.byUsernameCalls != 0 {
		t.Errorf("me 路径调了 %d 次 GetUserByUsername（那条会把 password_hash 读进内存）；应只走 GetProfileByUsername", store.byUsernameCalls)
	}
	if store.profileCalls == 0 {
		t.Error("me 路径没有回库查身份：那 role 是从哪来的？")
	}
}

// ── 测试辅助 ──────────────────────────────────────────────────────────

// brokenStore 的四个方法一律返回同一个错误，用来验证"库故障"不会被折叠成业务失败。
type brokenStore struct{ err error }

func (b *brokenStore) GetUserByUsername(context.Context, string) (db.User, error) {
	return db.User{}, b.err
}

func (b *brokenStore) GetProfileByUsername(context.Context, string) (db.GetProfileByUsernameRow, error) {
	return db.GetProfileByUsernameRow{}, b.err
}

func (b *brokenStore) InsertUser(context.Context, db.InsertUserParams) (db.InsertUserRow, error) {
	return db.InsertUserRow{}, b.err
}

func (b *brokenStore) UpdateUserPasswordByUsername(context.Context, db.UpdateUserPasswordByUsernameParams) (db.UpdateUserPasswordByUsernameRow, error) {
	return db.UpdateUserPasswordByUsernameRow{}, b.err
}

type recordCapture struct {
	mu      sync.Mutex
	records []slog.Record
}

func (c *recordCapture) Enabled(context.Context, slog.Level) bool { return true }

func (c *recordCapture) Handle(_ context.Context, r slog.Record) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.records = append(c.records, r.Clone())
	return nil
}

func (c *recordCapture) WithAttrs([]slog.Attr) slog.Handler { return c }
func (c *recordCapture) WithGroup(string) slog.Handler      { return c }

func (c *recordCapture) snapshot() []slog.Record {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]slog.Record, len(c.records))
	copy(out, c.records)
	return out
}

func (c *recordCapture) dump() string {
	var b strings.Builder
	for _, r := range c.snapshot() {
		b.WriteString(r.Level.String() + " " + r.Message + "\n")
	}
	return b.String()
}

func mustIssueWith(t *testing.T, cfg TokenConfig, username string) string {
	t.Helper()
	token, err := IssueAccessToken(cfg, username, "user")
	if err != nil {
		t.Fatal(err)
	}
	return token
}

func keys(m map[string]db.User) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	return out
}
