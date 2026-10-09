package httpapi

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func testDeps(checks ...Check) Deps {
	return Deps{
		Logger:  slog.New(slog.NewTextHandler(io.Discard, nil)),
		Version: "test",
		Checks:  checks,
		Timeout: time.Second,
	}
}

func do(t *testing.T, h http.Handler, method, path string, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, nil)
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func decode(t *testing.T, rec *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("响应不是合法 JSON: %v / body=%q", err, rec.Body.String())
	}
	return body
}

func okCheck(name string) Check {
	return Check{Name: name, Probe: func(context.Context) (bool, string) { return true, "connected" }}
}

func badCheck(name, why string) Check {
	return Check{Name: name, Probe: func(context.Context) (bool, string) { return false, why }}
}

func TestHealth(t *testing.T) {
	h := NewRouter(testDeps())
	for _, path := range []string{"/api/v1/health", "/health"} {
		rec := do(t, h, http.MethodGet, path, nil)
		if rec.Code != http.StatusOK {
			t.Fatalf("%s 期望 200，得到 %d", path, rec.Code)
		}
		body := decode(t, rec)
		if body["status"] != "ok" || body["version"] != "test" {
			t.Fatalf("%s 响应形状不对: %v", path, body)
		}
		if len(body) != 2 {
			t.Errorf("%s 不该带多余字段（与 Python 的 {status, version} 对齐）: %v", path, body)
		}
	}
}

func TestReadyAllOK(t *testing.T) {
	h := NewRouter(testDeps(okCheck("database")))
	rec := do(t, h, http.MethodGet, "/api/v1/ready", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，得到 %d body=%s", rec.Code, rec.Body.String())
	}
	body := decode(t, rec)
	if body["status"] != "ok" {
		t.Fatalf("status 应为 ok，得到 %v", body["status"])
	}
	checks := body["checks"].(map[string]any)
	db := checks["database"].(map[string]any)
	if db["status"] != "ok" || db["detail"] != "connected" {
		t.Fatalf("database 检查项形状不对: %v", db)
	}
}

// 就绪失败时 Python 走 HTTPException(detail={...})，线上形状是 {"detail": {...}}。
// 这条测试锁死该差异：成功是平铺、失败带信封，别让监控在两种状态码下解析两套结构。
func TestReadyFailureUsesDetailEnvelope(t *testing.T) {
	h := NewRouter(testDeps(okCheck("database"), badCheck("redis", "disconnected: dial tcp")))
	rec := do(t, h, http.MethodGet, "/api/v1/ready", nil)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("期望 503，得到 %d", rec.Code)
	}
	detail, ok := decode(t, rec)["detail"].(map[string]any)
	if !ok {
		t.Fatalf("失败响应必须是 {\"detail\": {...}}，得到 %s", rec.Body.String())
	}
	if detail["status"] != "unhealthy" {
		t.Errorf("status 应为 unhealthy，得到 %v", detail["status"])
	}
	checks := detail["checks"].(map[string]any)
	if checks["database"].(map[string]any)["status"] != "ok" {
		t.Errorf("database 应保持 ok，不受 redis 失败影响: %v", checks)
	}
	if checks["redis"].(map[string]any)["status"] != "error" {
		t.Errorf("redis 应为 error: %v", checks)
	}
}

func TestReadyTimeoutIsPerCheckAndNotFatal(t *testing.T) {
	slow := Check{Name: "milvus", Probe: func(ctx context.Context) (bool, string) {
		select {
		case <-ctx.Done():
			return false, "should not reach"
		case <-time.After(3 * time.Second):
			return true, "too late"
		}
	}}
	h := NewRouter(testDeps(okCheck("database"), slow))
	start := time.Now()
	rec := do(t, h, http.MethodGet, "/api/v1/ready", nil)
	if elapsed := time.Since(start); elapsed > 2*time.Second {
		t.Fatalf("单项超时应被 Timeout 截住，实际耗时 %s", elapsed)
	}
	detail := decode(t, rec)["detail"].(map[string]any)
	m := detail["checks"].(map[string]any)["milvus"].(map[string]any)
	if m["status"] != "error" || m["detail"] != "timeout after 1s" {
		t.Fatalf("超时语义应与 Python 的 \"timeout after Ns\" 一致，得到 %v", m)
	}
}

func TestPanicInCheckDoesNotCrashProbe(t *testing.T) {
	boom := Check{Name: "database", Probe: func(context.Context) (bool, string) { panic("boom") }}
	h := NewRouter(testDeps(boom))
	rec := do(t, h, http.MethodGet, "/api/v1/ready", nil)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("期望 503，得到 %d", rec.Code)
	}
	m := decode(t, rec)["detail"].(map[string]any)["checks"].(map[string]any)["database"].(map[string]any)
	if m["status"] != "error" {
		t.Fatalf("panic 应转成 error 项，得到 %v", m)
	}
}

func TestErrorsAlsoUseEnvelope(t *testing.T) {
	h := NewRouter(testDeps())

	rec := do(t, h, http.MethodGet, "/api/v1/nope", nil)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("未知路径期望 404，得到 %d", rec.Code)
	}
	if got := decode(t, rec)["detail"]; got != "Not Found" {
		t.Fatalf("404 信封应与 FastAPI 一致，得到 %v", got)
	}

	rec = do(t, h, http.MethodPost, "/api/v1/health", nil)
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("方法不匹配期望 405，得到 %d", rec.Code)
	}
	if got := decode(t, rec)["detail"]; got != "Method Not Allowed" {
		t.Fatalf("405 信封应与 FastAPI 一致，得到 %v", got)
	}
}

func TestRecoverTurnsPanicIntoEnvelope(t *testing.T) {
	defer func() {
		if v := recover(); v != nil {
			t.Fatalf("Recover 应吞掉 handler panic，结果冒泡到测试: %v", v)
		}
	}()
	h := Recover(testDeps().Logger)(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { panic("handler blew up") }))
	rec := do(t, h, http.MethodGet, "/boom", nil)
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("期望 500，得到 %d", rec.Code)
	}
	if got := decode(t, rec)["detail"]; got != "Internal Server Error" {
		t.Fatalf("500 也必须是 {\"detail\": ...} 信封，得到 %v", got)
	}
}

func TestTraceID(t *testing.T) {
	h := NewRouter(testDeps())

	rec := do(t, h, http.MethodGet, "/api/v1/health", nil)
	if id := rec.Header().Get("X-Trace-Id"); len(id) != 16 {
		t.Fatalf("响应头应带回生成的 trace_id，得到 %q", id)
	}

	rec = do(t, h, http.MethodGet, "/api/v1/health", map[string]string{"X-Trace-Id": "deadbeefdeadbeef"})
	if id := rec.Header().Get("X-Trace-Id"); id != "deadbeefdeadbeef" {
		t.Fatalf("上游给的 trace_id 必须透传，得到 %q", id)
	}
}
