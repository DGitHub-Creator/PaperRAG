package auth

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
)

// 改密码是新开的 Go 面（没有 Python 对照），所以这一组用例钉的是**内部不变量**：
// 旧口令错不落库、新口令规则与 register 同源、写进去的是哈希而不是明文、
// 以及"旧口令错回 400 而不是 401"这条会直接影响前端登录态的取舍。

// ── service ───────────────────────────────────────────────────────────

func TestChangePasswordHappyPathWritesNewHash(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)
	token := mustToken(t, svc, "alice", "user")
	oldHash := store.users["alice"].PasswordHash

	if err := svc.ChangePassword(context.Background(), token, "Abcdef12", "Zyxwvu98"); err != nil {
		t.Fatalf("改密码应成功，实得 %v", err)
	}
	if store.updatePasswordCalls != 1 {
		t.Fatalf("应恰好写一次库，实得 %d", store.updatePasswordCalls)
	}
	newHash := store.users["alice"].PasswordHash
	if newHash == oldHash {
		t.Error("哈希应已改变")
	}
	// 写进去的必须是哈希，明文绝不能出现在任何一层（这条同时钉住"写入方给的是已哈希串"）。
	if store.lastPasswordHash == "Zyxwvu98" {
		t.Error("落库的应是哈希，不是明文")
	}
	if !VerifyPassword("Zyxwvu98", newHash) {
		t.Error("新哈希应能验过新口令")
	}
	if VerifyPassword("Abcdef12", newHash) {
		t.Error("旧口令不该还能验过")
	}
	// 旧口令仍能验旧哈希：证明我们改的是同一行、且没在别处删改记录。
	if !VerifyPassword("Abcdef12", oldHash) {
		t.Error("旧哈希本身应保持不变（种子不变性）")
	}
}

func TestChangePasswordWrongOldPasswordDoesNotWrite(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)
	token := mustToken(t, svc, "alice", "user")
	before := store.users["alice"].PasswordHash

	err := svc.ChangePassword(context.Background(), token, "WrongPass1", "Zyxwvu98")
	if !errors.Is(err, ErrWrongPassword) {
		t.Fatalf("旧口令错应回 ErrWrongPassword，实得 %v", err)
	}
	if store.updatePasswordCalls != 0 {
		t.Error("旧口令没过就不该写库")
	}
	if store.users["alice"].PasswordHash != before {
		t.Error("库里的哈希不该变")
	}
}

// TestChangePasswordNewPasswordRulesMatchRegister 钉住"新口令与 register 同一套规则"。
// 如果这里漏了长度/类别校验，用户就能把密码改成一个比注册时更弱的串——
// 那是绕过注册校验的一条侧门。
func TestChangePasswordNewPasswordRulesMatchRegister(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store) // MinPasswordLength=8
	token := mustToken(t, svc, "alice", "user")

	// 太短（7 个码点）。
	if err := svc.ChangePassword(context.Background(), token, "Abcdef12", "Abcdef1"); !errors.As(err, new(PasswordTooShortError)) {
		t.Errorf("7 字符应被长度规则拒，实得 %v", err)
	}
	// 够长但只有一类字符。
	if err := svc.ChangePassword(context.Background(), token, "Abcdef12", "abcdefgh"); !errors.Is(err, ErrPasswordTooSimple) {
		t.Errorf("纯小写应被类别规则拒，实得 %v", err)
	}
	// 码点计数：8 个汉字是 8 码点但 24 字节——按字节算会误判，这里必须放行到类别规则。
	if err := svc.ChangePassword(context.Background(), token, "Abcdef12", "密码密码密码密码"); !errors.Is(err, ErrPasswordTooSimple) {
		t.Errorf("8 个汉字（24 字节）应按码点判为够长，只栽在类别规则上，实得 %v", err)
	}
	if store.updatePasswordCalls != 0 {
		t.Error("三条被拒的都不该写库")
	}
}

// TestChangePasswordDoesNotStripNewPassword 钉住"新口令不 strip"这条刻意差别：
// 口令是不透明串，静默去掉首尾空格等于替用户改了密码（register 会 strip 是生产侧的现状，两回事）。
func TestChangePasswordDoesNotStripNewPassword(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)
	token := mustToken(t, svc, "alice", "user")

	const withSpace = " Abcdef12 "
	if err := svc.ChangePassword(context.Background(), token, "Abcdef12", withSpace); err != nil {
		t.Fatalf("带空格的合法口令应被原样接受，实得 %v", err)
	}
	if !VerifyPassword(withSpace, store.users["alice"].PasswordHash) {
		t.Error("落库的哈希应对应**带空格**的原串")
	}
	if VerifyPassword("Abcdef12", store.users["alice"].PasswordHash) {
		t.Error("去空格后的串不该能验过（说明被 strip 了）")
	}
}

func TestChangePasswordRequiresValidToken(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)

	if err := svc.ChangePassword(context.Background(), "bad-token", "Abcdef12", "Zyxwvu98"); !errors.Is(err, ErrUnauthenticated) {
		t.Errorf("坏令牌应回 ErrUnauthenticated，实得 %v", err)
	}
	if store.updatePasswordCalls != 0 {
		t.Error("令牌没过就不该碰 users 写入")
	}
}

func TestChangePasswordStoreFailureBubbles(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)
	token := mustToken(t, svc, "alice", "user")

	svc.Store = &flakyUserStore{UserStore: store, updateErr: errors.New("connection refused")}

	err := svc.ChangePassword(context.Background(), token, "Abcdef12", "Zyxwvu98")
	if err == nil || errors.Is(err, ErrUnauthenticated) || errors.Is(err, ErrWrongPassword) {
		t.Fatalf("写库故障应原样冒泡，实得 %v", err)
	}
}

// flakyUserStore 只在改密码那一步注入故障，前两步（查身份、取哈希）走真实 fake。
// 「库故障不折叠成业务失败」这条性质必须能单独钉在写入点上——否则一个把写入错误
// 吞掉并回成功的实现也能让整组测试变绿。
type flakyUserStore struct {
	UserStore
	updateErr error
}

func (f *flakyUserStore) UpdateUserPasswordByUsername(context.Context, db.UpdateUserPasswordByUsernameParams) (db.UpdateUserPasswordByUsernameRow, error) {
	return db.UpdateUserPasswordByUsernameRow{}, f.updateErr
}

// ── handler ───────────────────────────────────────────────────────────

func changePasswordRecorder(t *testing.T, svc *Service, token, body string) *httptest.ResponseRecorder {
	t.Helper()
	return doJSON(t, ChangePasswordHandler(svc), http.MethodPost, "/api/v1/auth/password",
		"application/json", body, map[string]string{"Authorization": "Bearer " + token})
}

func TestChangePasswordHandlerReturnsStatusOK(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)
	token := mustToken(t, svc, "alice", "user")

	rec := changePasswordRecorder(t, svc, token, `{"old_password":"Abcdef12","new_password":"Zyxwvu98"}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，实得 %d：%s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	if body["status"] != "ok" {
		t.Errorf("成功体应是 {\"status\":\"ok\"}，实得 %v", body)
	}
	if len(body) != 1 {
		t.Errorf("成功体不该带别的字段（尤其不该回 token），实得 %v", body)
	}
}

// TestChangePasswordHandlerWrongOldIs400NotUnauthorized 是这一组里最要紧的一条：
// 401 会让前端清 token 把用户踢回登录页，而"旧密码打错了"完全不该有那个后果。
func TestChangePasswordHandlerWrongOldIs400NotUnauthorized(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)
	token := mustToken(t, svc, "alice", "user")

	rec := changePasswordRecorder(t, svc, token, `{"old_password":"WrongPass1","new_password":"Zyxwvu98"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("旧口令错应 400（不是 401），实得 %d：%s", rec.Code, rec.Body.String())
	}
	if got := detailOf(t, rec); got != detailWrongPassword {
		t.Errorf("期望 %q，实得 %q", detailWrongPassword, got)
	}
	if rec.Header().Get("WWW-Authenticate") != "" {
		t.Error("400 不该带 WWW-Authenticate（那是 401 的语义）")
	}
}

func TestChangePasswordHandlerReusesRegisterPasswordTexts(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store) // MinPasswordLength=8
	token := mustToken(t, svc, "alice", "user")

	rec := changePasswordRecorder(t, svc, token, `{"old_password":"Abcdef12","new_password":"Abcdef1"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("过短应 400，实得 %d", rec.Code)
	}
	if got := detailOf(t, rec); got != "Password must be at least 8 characters" {
		t.Errorf("长度文案应与 register 逐字一致，实得 %q", got)
	}

	rec = changePasswordRecorder(t, svc, token, `{"old_password":"Abcdef12","new_password":"abcdefgh"}`)
	if got := detailOf(t, rec); got != detailPasswordTooSimple {
		t.Errorf("类别文案应与 register 逐字一致，实得 %q", got)
	}
}

func TestChangePasswordHandlerRequiresBearer(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)

	rec := doJSON(t, ChangePasswordHandler(svc), http.MethodPost, "/api/v1/auth/password",
		"application/json", `{"old_password":"Abcdef12","new_password":"Zyxwvu98"}`, nil)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("缺 Authorization 应 401，实得 %d", rec.Code)
	}
	if got := detailOf(t, rec); got != detailNotAuthenticated {
		t.Errorf("期望 %q，实得 %q", detailNotAuthenticated, got)
	}
	if rec.Header().Get("WWW-Authenticate") != "Bearer" {
		t.Error("401 必须带 WWW-Authenticate: Bearer")
	}
}

func TestChangePasswordHandlerBodyValidation(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)
	token := mustToken(t, svc, "alice", "user")

	cases := []struct {
		name string
		body string
		want string
	}{
		{"两键都缺", `{}`, "old_password: " + msgFieldRequired + "; new_password: " + msgFieldRequired},
		{"缺新口令", `{"old_password":"Abcdef12"}`, "new_password: " + msgFieldRequired},
		{"新口令给 null", `{"old_password":"Abcdef12","new_password":null}`, "new_password: " + msgInvalidString},
		{"空 body", ``, msgBodyRequired},
		{"非法 JSON", `{`, msgJSONDecode},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rec := changePasswordRecorder(t, svc, token, tc.body)
			if rec.Code != http.StatusBadRequest {
				t.Fatalf("期望 400，实得 %d：%s", rec.Code, rec.Body.String())
			}
			if got := detailOf(t, rec); got != tc.want {
				t.Errorf("期望 %q，实得 %q", tc.want, got)
			}
		})
	}
	// 校验失败不该改动任何东西。
	if store.updatePasswordCalls != 0 {
		t.Error("请求体不合法的用例不该写库")
	}
}
