package session

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/auth"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
)

// newRouter 把三条路由挂进真的 chi 路由器：DeleteHandler 靠 chi.URLParam 取会话号，
// 不经过路由器直接调 handler 的话，测出来的"通过"只证明了我自己那半截。
func newRouter(svc *Service) *chi.Mux {
	r := chi.NewRouter()
	r.Get("/api/v1/sessions", ListHandler(svc))
	r.Get("/api/v1/sessions/{session_id}", DetailHandler(svc))
	r.Delete("/api/v1/sessions/{session_id}", DeleteHandler(svc))
	return r
}

func aliceToken(t *testing.T) string {
	t.Helper()
	token, err := auth.IssueAccessToken(auth.TokenConfig{Secret: testSecret, ExpireMinutes: 60, RefreshExpireDays: 30}, "alice", "user")
	if err != nil {
		t.Fatal(err)
	}
	return token
}

func do(t *testing.T, h http.Handler, method, path, authHeader string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, nil)
	if authHeader != "" {
		req.Header.Set("Authorization", authHeader)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func bodyOf(t *testing.T, rec *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	raw, err := io.ReadAll(rec.Body)
	if err != nil {
		t.Fatal(err)
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("响应不是 JSON：%q", string(raw))
	}
	return out
}

// ── 401 的两句文案不能混 ──────────────────────────────────────────────

func TestUnauthorizedTextsAreTheTwoProductionOnes(t *testing.T) {
	r := newRouter(newTestService(&fakeStore{}))
	token := "Bearer " + aliceToken(t)
	cases := []struct {
		name    string
		header  string
		want    string
		comment string
	}{
		{"缺头", "", "Not authenticated", "缺 Authorization 与方案不是 bearer 是同一句，这是 OAuth2PasswordBearer 的现状"},
		{"非 bearer 方案", "Basic abc", "Not authenticated", "换成 HTTPBearer 那句就是跨语言分歧"},
		{"令牌无效", "Bearer not-a-jwt", "无效或过期的认证令牌", "令牌本身的问题才是这一句"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rec := do(t, r, http.MethodGet, "/api/v1/sessions", tc.header)
			if rec.Code != http.StatusUnauthorized {
				t.Fatalf("期望 401，实得 %d：%s", rec.Code, rec.Body.String())
			}
			if got := bodyOf(t, rec)["detail"]; got != tc.want {
				t.Errorf("detail = %v，期望 %q（%s）", got, tc.want, tc.comment)
			}
		})
	}
	// 正向对照：带对了就必须是 200，否则上面三条只是因为"全都拒绝"而通过
	if rec := do(t, r, http.MethodGet, "/api/v1/sessions", token); rec.Code != http.StatusOK {
		t.Fatalf("带合法令牌应 200，实得 %d", rec.Code)
	}
}

// ── 列表 ─────────────────────────────────────────────────────────────

func TestListResponseShape(t *testing.T) {
	store := &fakeStore{rows: []db.ListSessionInfosForUserRow{
		{SessionID: "s-a", UpdatedAt: timestamp(2026, 10, 14, 7, 8, 10, 123456), MessageCount: 2},
	}}
	rec := do(t, newRouter(newTestService(store)), http.MethodGet, "/api/v1/sessions", "Bearer "+aliceToken(t))
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，实得 %d：%s", rec.Code, rec.Body.String())
	}
	out := bodyOf(t, rec)
	sessions, ok := out["sessions"].([]any)
	if !ok || len(sessions) != 1 {
		t.Fatalf("sessions 应当是长度 1 的数组，实得 %v", out["sessions"])
	}
	first := sessions[0].(map[string]any)
	if len(first) != 3 {
		t.Errorf("每条会话应当正好 3 个键（session_id/updated_at/message_count），实得 %v", first)
	}
	if first["session_id"] != "s-a" || first["updated_at"] != "2026-10-14T07:08:10.123456" || first["message_count"] != float64(2) {
		t.Errorf("字段不对：%v", first)
	}
}

func TestEmptyListSerialisesAsArray(t *testing.T) {
	rec := do(t, newRouter(newTestService(&fakeStore{})), http.MethodGet, "/api/v1/sessions", "Bearer "+aliceToken(t))
	raw := rec.Body.String()
	if !containsSessionsArray(raw) {
		t.Errorf("空结果应当是 {\"sessions\":[]}，实得 %q", raw)
	}
}

func containsSessionsArray(raw string) bool {
	var probe struct {
		Sessions *[]any `json:"sessions"`
	}
	if err := json.Unmarshal([]byte(raw), &probe); err != nil {
		return false
	}
	return probe.Sessions != nil && len(*probe.Sessions) == 0
}

// ── 删除 ─────────────────────────────────────────────────────────────

func TestDeleteSuccessBody(t *testing.T) {
	rec := do(t, newRouter(newTestService(&fakeStore{deleted: 1})), http.MethodDelete, "/api/v1/sessions/s-a", "Bearer "+aliceToken(t))
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，实得 %d：%s", rec.Code, rec.Body.String())
	}
	out := bodyOf(t, rec)
	if out["session_id"] != "s-a" || out["message"] != "Session deleted" {
		t.Errorf("响应体不对：%v", out)
	}
}

func TestDeleteMissingSessionIs404WithProductionText(t *testing.T) {
	rec := do(t, newRouter(newTestService(&fakeStore{deleted: 0})), http.MethodDelete, "/api/v1/sessions/nope", "Bearer "+aliceToken(t))
	if rec.Code != http.StatusNotFound {
		t.Fatalf("期望 404，实得 %d", rec.Code)
	}
	if got := bodyOf(t, rec)["detail"]; got != "Session does not exist" {
		t.Errorf("detail = %v，必须是 backend/api/sessions.py:60 那句", got)
	}
}

// 没登录时先回 401，而不是先查库回 404——否则这个接口可以用来探测"某人的会话号存在吗"。
func TestDeleteChecksAuthBeforeExistence(t *testing.T) {
	rec := do(t, newRouter(newTestService(&fakeStore{deleted: 0})), http.MethodDelete, "/api/v1/sessions/someone-elses", "")
	if rec.Code != http.StatusUnauthorized {
		t.Errorf("未登录应当 401，实得 %d（404 等于泄露了会话号的存在性）", rec.Code)
	}
}

func TestStoreFailureIs500Not404(t *testing.T) {
	// 404 会让人以为路由没挂，那是完全错误的排查方向（与 cmd/api 的 unavailableStore 同一口径）
	svc := newTestService(&fakeStore{listErr: errors.New("池不可用")})
	rec := do(t, newRouter(svc), http.MethodGet, "/api/v1/sessions", "Bearer "+aliceToken(t))
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("期望 500，实得 %d：%s", rec.Code, rec.Body.String())
	}
	if got := bodyOf(t, rec)["detail"]; got != "Internal server error" {
		t.Errorf("500 的文案必须是生产侧那句（小写 s），实得 %v", got)
	}
}

func TestUnassembledStoreIs500(t *testing.T) {
	svc := newTestService(nil)
	rec := do(t, newRouter(svc), http.MethodDelete, "/api/v1/sessions/s-a", "Bearer "+aliceToken(t))
	if rec.Code != http.StatusInternalServerError {
		t.Errorf("未装配 Store 应 500，实得 %d", rec.Code)
	}
}
