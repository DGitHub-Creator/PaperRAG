package httpapi

import (
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
)

// upstreamDeps 造一个挂了反代的 Deps，其余与 testDeps 一致（同一包的 helper）。
func upstreamDeps(t *testing.T, upstreamURL string) Deps {
	t.Helper()
	u, err := url.Parse(upstreamURL)
	if err != nil {
		t.Fatalf("上游地址非法: %v", err)
	}
	d := testDeps()
	d.Upstream = NewUpstreamProxy(u, d.Logger)
	return d
}

// 未接管的路径要原样落到上游：路径不被裁剪、查询串保留、状态码与响应体透传。
// 这三条一起钉，是因为"缺一条"都会变成难查的线上问题（少查询串=分页失灵，
// 少状态码=错误被吞成 200）。
func TestUpstreamForwardsUnhandledPaths(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Upstream-Path", r.URL.Path)
		w.Header().Set("X-Upstream-Query", r.URL.RawQuery)
		w.WriteHeader(http.StatusTeapot)
		_, _ = io.WriteString(w, `{"from":"python"}`)
	}))
	defer upstream.Close()

	h := NewRouter(upstreamDeps(t, upstream.URL))
	rec := do(t, h, http.MethodGet, "/api/v1/sessions?limit=3", nil)

	if rec.Code != http.StatusTeapot {
		t.Fatalf("状态码应透传，得到 %d", rec.Code)
	}
	if got := rec.Header().Get("X-Upstream-Path"); got != "/api/v1/sessions" {
		t.Fatalf("路径不应被裁剪，得到 %q", got)
	}
	if got := rec.Header().Get("X-Upstream-Query"); got != "limit=3" {
		t.Fatalf("查询串应保留，得到 %q", got)
	}
	if got := rec.Body.String(); got != `{"from":"python"}` {
		t.Fatalf("响应体应透传，得到 %q", got)
	}
}

// Go 自己注册的静态路由必须盖过通配转发——否则 /api/v1/health 会被送到 Python，
// "Go 是唯一入口"里那些已经搬过来的面就成了摆设。
func TestUpstreamDoesNotShadowNativeRoutes(t *testing.T) {
	called := false
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer upstream.Close()

	h := NewRouter(upstreamDeps(t, upstream.URL))
	for _, path := range []string{"/api/v1/health", "/health"} {
		rec := do(t, h, http.MethodGet, path, nil)
		if rec.Code != http.StatusOK {
			t.Fatalf("%s 应由 Go 自答 200，得到 %d", path, rec.Code)
		}
		if body := decode(t, rec); body["version"] != "test" {
			t.Fatalf("%s 不该是上游的响应: %v", path, body)
		}
	}
	if called {
		t.Fatal("原生路由被转发到了上游")
	}
}

// 上游不可达时不能把连接错误原样抛给浏览器：信封形状要与其余错误一致（01 §6.3）。
func TestUpstreamUnreachableGivesEnvelope(t *testing.T) {
	dead := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	deadURL := dead.URL
	dead.Close() // 立刻关掉，让转发必然失败

	h := NewRouter(upstreamDeps(t, deadURL))
	rec := do(t, h, http.MethodGet, "/api/v1/sessions", nil)

	if rec.Code != http.StatusBadGateway {
		t.Fatalf("上游不可达期望 502，得到 %d", rec.Code)
	}
	if got := decode(t, rec)["detail"]; got != "上游服务不可用" {
		t.Fatalf("502 也必须是 {\"detail\": ...} 信封，得到 %v", got)
	}
}

// 没配上游（go-worker 与旧单测）时维持旧行为：未命中就是 JSON 404，不偷偷转发。
func TestNoUpstreamKeepsJSON404(t *testing.T) {
	h := NewRouter(testDeps())
	rec := do(t, h, http.MethodGet, "/api/v1/sessions", nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("无上游时期望 404，得到 %d", rec.Code)
	}
}
