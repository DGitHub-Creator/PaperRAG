package httpapi

import (
	"bufio"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/observability"
)

func TestLoggerPreservesStreamingFlush(t *testing.T) {
	release := make(chan struct{})
	h := RequestLogger(testDeps().Logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = io.WriteString(w, "data: first\n\n")
		if err := http.NewResponseController(w).Flush(); err != nil {
			t.Errorf("流式刷新失败: %v", err)
			return
		}
		select {
		case <-release:
		case <-r.Context().Done():
		}
	}))
	srv := httptest.NewServer(h)
	defer srv.Close()
	defer close(release)
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get(srv.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	line, err := bufio.NewReader(resp.Body).ReadString('\n')
	if err != nil || line != "data: first\n" {
		t.Fatalf("上游未结束前必须收到首帧: %q, %v", line, err)
	}
}

func TestLoggerPreservesConnectionUpgrade(t *testing.T) {
	h := RequestLogger(testDeps().Logger)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		conn, rw, err := http.NewResponseController(w).Hijack()
		if err != nil {
			t.Errorf("连接升级失败: %v", err)
			return
		}
		defer conn.Close()
		_, _ = rw.WriteString("HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n")
		_ = rw.Flush()
	}))
	srv := httptest.NewServer(h)
	defer srv.Close()
	conn, err := net.DialTimeout("tcp", strings.TrimPrefix(srv.URL, "http://"), 2*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(2 * time.Second))
	_, _ = fmt.Fprint(conn, "GET / HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n")
	resp, err := http.ReadResponse(bufio.NewReader(conn), nil)
	if err != nil || resp.StatusCode != http.StatusSwitchingProtocols {
		t.Fatalf("期望协议升级响应，得到 %v, %v", resp, err)
	}
}

// TestTraceMiddlewareEnforcesTheContractedAcceptanceSet 钉的是边缘那一步：
// 非法入站值不会被写回响应头，也不会被注入上游（台账 C38 的"不回显"口径）。
func TestTraceMiddlewareEnforcesTheContractedAcceptanceSet(t *testing.T) {
	carrier := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// 把 context 里的值暴露出来：注入给 Python 的必须是清洗后的那一个。
		_, _ = io.WriteString(w, observability.TraceID(r.Context()))
	})
	run := func(header string) (response string, seenHeader []string, contextID string) {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/health", nil)
		if header != "" {
			req.Header.Set("X-Trace-Id", header)
		}
		rec := httptest.NewRecorder()
		Trace(carrier).ServeHTTP(rec, req)
		return rec.Header().Get("X-Trace-Id"), rec.Header().Values("X-Trace-Id"), rec.Body.String()
	}

	if got, values, ctxID := run("legal-id_1.2"); got != "legal-id_1.2" || len(values) != 1 || ctxID != "legal-id_1.2" {
		t.Errorf("合法值应原样沿用且单值，实得 %q / %v / ctx=%q", got, values, ctxID)
	}
	for _, bad := range []string{"has space", strings.Repeat("a", 129), "追踪", "a:b", `'q'`} {
		got, values, ctxID := run(bad)
		if len(values) != 1 {
			t.Fatalf("响应头必须恒为单值，实得 %v", values)
		}
		if got == bad {
			t.Errorf("%q 非法却被回显了", bad)
		}
		if got != ctxID {
			t.Errorf("响应头 %q 与注入下游的 %q 不是同一个 id", got, ctxID)
		}
	}
}

func TestStatusWriterKeepsFirstFinalStatus(t *testing.T) {
	rec := httptest.NewRecorder()
	w := &statusWriter{ResponseWriter: rec}
	w.WriteHeader(http.StatusCreated)
	w.WriteHeader(http.StatusInternalServerError)
	if w.status != http.StatusCreated || rec.Code != http.StatusCreated {
		t.Fatalf("最终状态码被覆盖: %d, %d", w.status, rec.Code)
	}
}
