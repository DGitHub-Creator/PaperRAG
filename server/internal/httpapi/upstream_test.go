package httpapi

import (
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/observability"
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
		if r.Header.Get("X-Trace-Id") == "" {
			t.Error("Go 生成的追踪号必须传到上游")
		}
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

// 追踪号在响应里只能出现一次（台账 C38）。
//
// 2026-10-17 真栈实测：`curl -D - http://127.0.0.1:8080/metrics` 给出两行相同的
// X-Trace-Id——Go 的 Trace 中间件先 Set，ReverseProxy 把上游同名头逐值 Add 上来。
// 值相同所以语义没坏，但"一个头两个值"会让前端 headers[...] 读到拼接串、
// APM 采集出现重复关联键。这条用例钉的是**只有一个值**，不是"值相等"。
func TestUpstreamEmitsExactlyOneTraceHeader(t *testing.T) {
	const inbound = "probe-abc-123"
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got := r.Header.Get(observability.TraceIDHeader)
		if got != inbound {
			t.Errorf("上游收到的追踪号应沿用入站值，得到 %q", got)
		}
		// 故意用 Add：真实 Python 侧的回写就是往响应里加这个头，
		// 若上游写的是别的值（直连时它自己生成的形态），也必须由边缘丢弃它、只留 Go 的那一份。
		w.Header().Add(observability.TraceIDHeader, got)
		w.Header().Add(observability.TraceIDHeader, "python-self-generated-32hex")
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	req := httptest.NewRequest(http.MethodGet, "/api/v1/unhandled", nil)
	req.Header.Set(observability.TraceIDHeader, inbound)
	rec := httptest.NewRecorder()
	NewRouter(upstreamDeps(t, upstream.URL)).ServeHTTP(rec, req)

	values := rec.Header().Values(observability.TraceIDHeader)
	if len(values) != 1 {
		t.Fatalf("响应头必须只有一个值，得到 %d 个：%v", len(values), values)
	}
	if values[0] != inbound {
		t.Fatalf("边缘值必须以 Go 的为准，得到 %q", values[0])
	}
}
