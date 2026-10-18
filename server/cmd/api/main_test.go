package main

// cmd/api 的第一条单测：管的是"接管"这个词本身，而不是响应长得像不像。
//
// 设计审查 §0 写得很清楚：经反代拿到逐字相同的 JSON **不能**证明 Go 原生读取。
// 所以这里不比对报文，而是把上游换成一个"被碰到就记一笔"的桩——
// 已接管的路由必须一次都不碰它，未接管的必须碰。这条判据不会因为 Python 侧
// 改了实现而一起变绿，正好是它该有的样子。

import (
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/auth"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/config"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/httpapi"
)

const testSecret = "session-takeover-test-secret"

func discardLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// buildRouter 起一套真实装配，但**没有数据库**：三条会话面会走到"未装配 Store"那条分支。
// 这不影响判据——要点是请求由 Go 的 handler 处理，而不是被转给上游。
func buildRouter(t *testing.T, upstream http.Handler) chi.Router {
	t.Helper()
	rate, err := httpapi.NewRateLimiter("redis://127.0.0.1:6379/0", "unit_test", "", "")
	if err != nil {
		t.Fatal(err)
	}
	defer rate.Close()
	logger := discardLogger()
	router := httpapi.NewRouter(httpapi.Deps{
		Logger:   logger,
		Version:  "test",
		Checks:   nil,
		Timeout:  time.Second,
		Upstream: upstream,
	})
	cfg := config.Config{
		Service:              "go-api",
		JWTSecretKey:         testSecret,
		JWTAlgorithm:         "HS256",
		JWTExpireMinutes:     60,
		JWTRefreshExpireDays: 30,
		PasswordPBKDF2Rounds: 40000,
		MinPasswordLength:    8,
	}
	noPool := errors.New("单测不连库")
	authSvc := mountAuthRoutes(router, cfg, nil, noPool, logger, rate)
	mountSessionRoutes(router, authSvc, nil, noPool, logger, rate)
	return router
}

func aliceToken(t *testing.T) string {
	t.Helper()
	token, err := auth.IssueAccessToken(
		auth.TokenConfig{Secret: testSecret, ExpireMinutes: 60, RefreshExpireDays: 30}, "alice", "user")
	if err != nil {
		t.Fatal(err)
	}
	return token
}

func TestTakenOverSessionRoutesNeverReachTheUpstream(t *testing.T) {
	var reached atomic.Int64
	upstream := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		reached.Add(1)
		w.WriteHeader(http.StatusNotImplemented) // 501：只有"还在转给 Python"才会出现
		_, _ = io.WriteString(w, `{"detail":"upstream reached"}`)
	})
	router := buildRouter(t, upstream)
	authHeader := "Bearer " + aliceToken(t)

	takenOver := []struct{ method, path string }{
		{http.MethodGet, "/api/v1/sessions"},
		{http.MethodGet, "/api/v1/sessions/chain-sess-newer"}, // 本切片接管的那条
		{http.MethodDelete, "/api/v1/sessions/chain-sess-newer"},
	}
	for _, tc := range takenOver {
		req := httptest.NewRequest(tc.method, tc.path, nil)
		req.Header.Set("Authorization", authHeader)
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, req)
		if rec.Code == http.StatusNotImplemented {
			t.Errorf("%s %s 被转给了上游，说明这条根本没接管", tc.method, tc.path)
		}
		if rec.Code != http.StatusInternalServerError {
			t.Errorf("%s %s 期望 Go 自己的 500（无库），实得 %d：%s", tc.method, tc.path, rec.Code, rec.Body.String())
		}
	}
	if got := reached.Load(); got != 0 {
		t.Errorf("已接管的路由一次都不该碰上游，实得 %d 次", got)
	}

	// 反向对照：没接管的面上游必须被碰到。少了这一条，上面三个断言可能只是因为
	// "整台路由器压根没转发挥作用"而通过。
	req := httptest.NewRequest(http.MethodGet, "/api/v1/documents", nil)
	req.Header.Set("Authorization", authHeader)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotImplemented {
		t.Errorf("未接管的面应转给上游（501），实得 %d：%s", rec.Code, rec.Body.String())
	}
	if reached.Load() != 1 {
		t.Errorf("上游桩应被命中一次，实得 %d", reached.Load())
	}
}

func TestSessionDetailRouteIsRegisteredExplicitly(t *testing.T) {
	// chi 的具体度匹配是接管机制的地基：`{session_id}` 必须赢过 `/api/*` 通配。
	// 这条把"注册了什么模式"钉下来，上面那条钉"请求落在谁手里"。
	router := buildRouter(t, nil)
	patterns := map[string]bool{}
	err := chi.Walk(router, func(method, route string, _ http.Handler, _ ...func(http.Handler) http.Handler) error {
		patterns[method+" "+route] = true
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if !patterns["GET /api/v1/sessions/{session_id}"] {
		t.Errorf("会话详情没按契约路径注册，实得模式集：%v", patterns)
	}
}
