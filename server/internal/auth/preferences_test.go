package auth

import (
	"context"
	"errors"
	"net/http"
	"sync"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
)

// fakePrefs 是 PrefsStore 的内存实现。它记两次调用的入参，因为这一面的性质
// （"库里的 created_at/updated_at 由写入方给 UTC"）只能靠**看写进去的那两个值**来断言——
// 库里那两列没有 DEFAULT，写方给什么就是什么。
type fakePrefs struct {
	mu           sync.Mutex
	rows         map[int32]db.UserPreference
	getErr       error
	upsertErr    error
	getCalls     int
	upsertCalls  int
	lastUpsert   db.UpsertUserPreferencesParams
	lastGetUserI int32
}

func newFakePrefs() *fakePrefs {
	return &fakePrefs{rows: map[int32]db.UserPreference{}}
}

func (f *fakePrefs) GetUserPreferences(_ context.Context, userID int32) (db.UserPreference, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.getCalls++
	f.lastGetUserI = userID
	if f.getErr != nil {
		return db.UserPreference{}, f.getErr
	}
	row, ok := f.rows[userID]
	if !ok {
		return db.UserPreference{}, pgx.ErrNoRows
	}
	return row, nil
}

func (f *fakePrefs) UpsertUserPreferences(_ context.Context, arg db.UpsertUserPreferencesParams) (db.UserPreference, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.upsertCalls++
	f.lastUpsert = arg
	if f.upsertErr != nil {
		return db.UserPreference{}, f.upsertErr
	}
	row := db.UserPreference(arg)
	// 冲突分支只用 updated_at：已存在时保留首次的 created_at，与 SQL 的
	// `DO UPDATE SET ... updated_at = EXCLUDED.updated_at` 同形。
	if old, ok := f.rows[arg.UserID]; ok {
		row.CreatedAt = old.CreatedAt
	}
	f.rows[arg.UserID] = row
	return row, nil
}

// prefsService 给一个既有用户（id 从 1 起）与可达的偏好面。
func prefsService(t *testing.T) (*Service, *fakeStore, *fakePrefs) {
	t.Helper()
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store)
	prefs := newFakePrefs()
	svc.Prefs = prefs
	return svc, store, prefs
}

func mustToken(t *testing.T, svc *Service, username, role string) string {
	t.Helper()
	token, err := IssueAccessToken(svc.Tokens, username, role)
	if err != nil {
		t.Fatal(err)
	}
	return token
}

// ── service：读 ───────────────────────────────────────────────────────

// TestGetPreferencesMissingRowIsDefaults 钉住"库里没有行不是 404"：
// 用户从没改过设置是**正常路径**，回档默认值。若这里改成 404，前端启动时
// 每个新用户都会看到一次"设置读取失败"。
func TestGetPreferencesMissingRowIsDefaults(t *testing.T) {
	svc, _, prefs := prefsService(t)
	token := mustToken(t, svc, "alice", "user")

	got, err := svc.GetPreferences(context.Background(), token)
	if err != nil {
		t.Fatalf("没有行时应回默认值而不是错：%v", err)
	}
	if got.Theme != ThemeSystem || got.StartView != DefaultStartView {
		t.Errorf("期望默认 %s/%s，实得 %s/%s", ThemeSystem, DefaultStartView, got.Theme, got.StartView)
	}
	if prefs.getCalls != 1 {
		t.Errorf("应恰好查一次库，实得 %d", prefs.getCalls)
	}
}

func TestGetPreferencesReturnsStoredRow(t *testing.T) {
	svc, _, prefs := prefsService(t)
	token := mustToken(t, svc, "alice", "user")
	prefs.rows[1] = db.UserPreference{UserID: 1, Theme: ThemeDark, StartView: "library"}

	got, err := svc.GetPreferences(context.Background(), token)
	if err != nil {
		t.Fatal(err)
	}
	if got.Theme != ThemeDark || got.StartView != "library" {
		t.Errorf("实得 %s/%s", got.Theme, got.StartView)
	}
}

func TestGetPreferencesRejectsBadToken(t *testing.T) {
	svc, _, prefs := prefsService(t)

	if _, err := svc.GetPreferences(context.Background(), "not-a-token"); !errors.Is(err, ErrUnauthenticated) {
		t.Errorf("坏令牌应回 ErrUnauthenticated，实得 %v", err)
	}
	if prefs.getCalls != 0 {
		t.Error("令牌没过就不该碰偏好面")
	}
}

// TestGetPreferencesVanishedUserIsUnauthenticated 与 /me 同一性质：
// 令牌层全对但用户已不在库 → 401，而不是把身份查空后继续。
func TestGetPreferencesVanishedUserIsUnauthenticated(t *testing.T) {
	svc, store, prefs := prefsService(t)
	token := mustToken(t, svc, "ghost", "user")
	delete(store.users, "ghost")

	if _, err := svc.GetPreferences(context.Background(), token); !errors.Is(err, ErrUnauthenticated) {
		t.Errorf("用户已不在库应回 ErrUnauthenticated，实得 %v", err)
	}
	if prefs.getCalls != 0 {
		t.Error("身份都没确认就不该读偏好")
	}
}

// TestGetPreferencesStoreFailureBubbles 钉住"库故障不折叠成业务失败"：
// 读偏好时库挂了要原样冒泡（handler 层才会给 500），不能当成"没有行"回默认值——
// 那会把一次故障伪装成"用户就是这么设置的"。
func TestGetPreferencesStoreFailureBubbles(t *testing.T) {
	svc, _, prefs := prefsService(t)
	token := mustToken(t, svc, "alice", "user")
	prefs.getErr = errors.New("connection refused")

	_, err := svc.GetPreferences(context.Background(), token)
	if err == nil || errors.Is(err, ErrUnauthenticated) {
		t.Fatalf("库故障应原样冒泡，实得 %v", err)
	}
}

// ── service：写 ───────────────────────────────────────────────────────

func TestPutPreferencesWritesUTCTimestamps(t *testing.T) {
	svc, _, prefs := prefsService(t)
	token := mustToken(t, svc, "alice", "user")

	got, err := svc.PutPreferences(context.Background(), token, ThemeLight, "reader")
	if err != nil {
		t.Fatal(err)
	}
	if got.Theme != ThemeLight || got.StartView != "reader" {
		t.Errorf("实得 %s/%s", got.Theme, got.StartView)
	}
	w := prefs.lastUpsert
	if w.UserID != 1 {
		t.Errorf("应写当前用户的 user_id=1，实得 %d", w.UserID)
	}
	// 000003 的口径：两列没有 DEFAULT，写方必须给值，且必须是 UTC
	// （05 §4 的时间列语义审计：naive 列落 +8 小时那个坑）。
	for name, ts := range map[string]pgtype.Timestamptz{"created_at": w.CreatedAt, "updated_at": w.UpdatedAt} {
		if !ts.Valid {
			t.Errorf("%s 必须给值（库里没有 DEFAULT）", name)
			continue
		}
		if off := ts.Time.UTC().Sub(ts.Time); off != 0 {
			t.Errorf("%s 必须是 UTC，实得偏移 %v", name, off)
		}
		if ts.Time.IsZero() {
			t.Errorf("%s 不应是零值时间", name)
		}
	}
}

func TestPutPreferencesRejectsUnknownTheme(t *testing.T) {
	svc, _, prefs := prefsService(t)
	token := mustToken(t, svc, "alice", "user")

	for _, bad := range []string{"", "Light", "auto", "solarized"} {
		if _, err := svc.PutPreferences(context.Background(), token, bad, "chat"); !errors.Is(err, ErrInvalidTheme) {
			t.Errorf("主题 %q 应被拒（闭集只有 light/dark/system），实得 %v", bad, err)
		}
	}
	if prefs.upsertCalls != 0 {
		t.Error("非法主题不该落到写库")
	}
}

// TestPutPreferencesStartViewIsShapeOnly 钉住"Go 不抄前端的路由表"：
// 形状合法就放行（哪怕这个名字 Go 不认识），形状不合法才拒。
func TestPutPreferencesStartViewIsShapeOnly(t *testing.T) {
	svc, _, _ := prefsService(t)
	token := mustToken(t, svc, "alice", "user")

	if _, err := svc.PutPreferences(context.Background(), token, ThemeDark, "a-view-name-go-never-heard-of"); err != nil {
		t.Errorf("形状合法的 slug 应放行（认识与否是前端的事），实得 %v", err)
	}
	for _, bad := range []string{"", "Chat", "1chat", "-chat", "chat view", "chat/view"} {
		if _, err := svc.PutPreferences(context.Background(), token, ThemeDark, bad); !errors.Is(err, ErrInvalidStartView) {
			t.Errorf("默认页 %q 应被拒（只收小写 slug），实得 %v", bad, err)
		}
	}
}

// TestPutPreferencesUpsertSecondTimeKeepsCreatedAt 是幂等性的服务层对应断言：
// 第二次写同一个用户走的是冲突分支，created_at 应保持第一次的值。
func TestPutPreferencesUpsertSecondTimeKeepsCreatedAt(t *testing.T) {
	svc, _, prefs := prefsService(t)
	token := mustToken(t, svc, "alice", "user")

	if _, err := svc.PutPreferences(context.Background(), token, ThemeLight, "chat"); err != nil {
		t.Fatal(err)
	}
	first := prefs.rows[1].CreatedAt
	if _, err := svc.PutPreferences(context.Background(), token, ThemeDark, "library"); err != nil {
		t.Fatal(err)
	}
	if !prefs.rows[1].CreatedAt.Time.Equal(first.Time) {
		t.Errorf("第二次写不该改 created_at：%v → %v", first.Time, prefs.rows[1].CreatedAt.Time)
	}
	if prefs.rows[1].Theme != ThemeDark {
		t.Errorf("第二次写应覆盖 theme，实得 %s", prefs.rows[1].Theme)
	}
}

func TestPutPreferencesWithoutPrefsStoreIs500(t *testing.T) {
	store := newFakeStore()
	store.seed(t, "alice", "Abcdef12", "user")
	svc := testService(store) // Prefs 故意留 nil（go-worker 与单测里的形态）
	token := mustToken(t, svc, "alice", "user")

	rec := doJSON(t, PutPreferencesHandler(svc), http.MethodPut, "/api/v1/me/preferences",
		"application/json", `{"theme":"dark","start_view":"chat"}`,
		map[string]string{"Authorization": "Bearer " + token})
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("没装配偏好面应 500，实得 %d：%s", rec.Code, rec.Body.String())
	}
}

// ── handler ───────────────────────────────────────────────────────────

func TestGetPreferencesHandlerSuccessShape(t *testing.T) {
	svc, _, prefs := prefsService(t)
	token := mustToken(t, svc, "alice", "user")
	prefs.rows[1] = db.UserPreference{UserID: 1, Theme: ThemeDark, StartView: "library"}

	rec := doJSON(t, GetPreferencesHandler(svc), http.MethodGet, "/api/v1/me/preferences", "", "",
		map[string]string{"Authorization": "Bearer " + token})
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，实得 %d：%s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	if body["theme"] != ThemeDark || body["start_view"] != "library" {
		t.Errorf("实得 %v", body)
	}
	if len(body) != 2 {
		t.Errorf("响应应恰好两个字段（契约 UserPreferences 只有两项），实得 %v", body)
	}
}

func TestPreferencesHandlersRequireBearer(t *testing.T) {
	svc, _, _ := prefsService(t)

	rec := doJSON(t, GetPreferencesHandler(svc), http.MethodGet, "/api/v1/me/preferences", "", "", nil)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("缺 Authorization 应 401，实得 %d", rec.Code)
	}
	if got := detailOf(t, rec); got != detailNotAuthenticated {
		t.Errorf("期望 %q，实得 %q", detailNotAuthenticated, got)
	}
	if rec.Header().Get("WWW-Authenticate") != "Bearer" {
		t.Error("401 必须带 WWW-Authenticate: Bearer")
	}

	rec = doJSON(t, PutPreferencesHandler(svc), http.MethodPut, "/api/v1/me/preferences",
		"application/json", `{"theme":"dark","start_view":"chat"}`,
		map[string]string{"Authorization": "Basic YWxpY2U6eA=="})
	if rec.Code != http.StatusUnauthorized {
		t.Errorf("非 bearer 方案应 401，实得 %d", rec.Code)
	}
}

func TestPutPreferencesHandlerValidationOrder(t *testing.T) {
	svc, _, _ := prefsService(t)
	token := mustToken(t, svc, "alice", "user")
	auth := map[string]string{"Authorization": "Bearer " + token}

	// 缺键与给 null 在生产侧结论不同（pydantic：Field required / 不是合法字符串），
	// 与 register/login 同一套文案，所以这里逐条钉住。
	cases := []struct {
		name string
		body string
		want string
	}{
		{"缺 theme", `{"start_view":"chat"}`, "theme: " + msgFieldRequired},
		{"theme 给 null", `{"theme":null,"start_view":"chat"}`, "theme: " + msgInvalidString},
		{"两个都缺", `{}`, "theme: " + msgFieldRequired + "; start_view: " + msgFieldRequired},
		{"theme 类型错", `{"theme":123,"start_view":"chat"}`, "theme: " + msgInvalidString},
		{"空 body", ``, msgBodyRequired},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rec := doJSON(t, PutPreferencesHandler(svc), http.MethodPut, "/api/v1/me/preferences",
				"application/json", tc.body, auth)
			if rec.Code != http.StatusBadRequest {
				t.Fatalf("期望 400，实得 %d：%s", rec.Code, rec.Body.String())
			}
			if got := detailOf(t, rec); got != tc.want {
				t.Errorf("期望 %q，实得 %q", tc.want, got)
			}
		})
	}
}

func TestPutPreferencesHandlerRejectsUnknownThemeWithItsOwnText(t *testing.T) {
	svc, _, _ := prefsService(t)
	token := mustToken(t, svc, "alice", "user")

	rec := doJSON(t, PutPreferencesHandler(svc), http.MethodPut, "/api/v1/me/preferences",
		"application/json", `{"theme":"auto","start_view":"chat"}`,
		map[string]string{"Authorization": "Bearer " + token})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("未知主题应 400，实得 %d", rec.Code)
	}
	if got := detailOf(t, rec); got != detailInvalidTheme {
		t.Errorf("期望 %q，实得 %q", detailInvalidTheme, got)
	}

	rec = doJSON(t, PutPreferencesHandler(svc), http.MethodPut, "/api/v1/me/preferences",
		"application/json", `{"theme":"dark","start_view":"Chat"}`,
		map[string]string{"Authorization": "Bearer " + token})
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("非法默认页应 400，实得 %d", rec.Code)
	}
	if got := detailOf(t, rec); got != detailInvalidStartView {
		t.Errorf("期望 %q，实得 %q", detailInvalidStartView, got)
	}
}

func TestPutPreferencesHandlerRoundTripsThroughGet(t *testing.T) {
	svc, _, _ := prefsService(t)
	token := mustToken(t, svc, "alice", "user")
	auth := map[string]string{"Authorization": "Bearer " + token}

	rec := doJSON(t, PutPreferencesHandler(svc), http.MethodPut, "/api/v1/me/preferences",
		"application/json", `{"theme":"dark","start_view":"library"}`, auth)
	if rec.Code != http.StatusOK {
		t.Fatalf("写入应 200，实得 %d：%s", rec.Code, rec.Body.String())
	}
	if body := decodeBody(t, rec); body["theme"] != ThemeDark || body["start_view"] != "library" {
		t.Errorf("写入响应应回显实际落库值，实得 %v", body)
	}

	rec = doJSON(t, GetPreferencesHandler(svc), http.MethodGet, "/api/v1/me/preferences", "", "", auth)
	if body := decodeBody(t, rec); body["theme"] != ThemeDark || body["start_view"] != "library" {
		t.Errorf("读回应与写入一致，实得 %v", body)
	}
}
