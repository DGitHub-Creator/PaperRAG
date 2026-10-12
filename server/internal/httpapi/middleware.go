package httpapi

import (
	"log/slog"
	"net/http"
	"runtime/debug"
	"time"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/observability"
)

// Trace 透传上游的 X-Trace-Id，没有就新生成一个，并写回响应头供前端排查。
func Trace(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get(observability.TraceIDHeader)
		if id == "" {
			id = observability.NewTraceID()
		}
		w.Header().Set(observability.TraceIDHeader, id)
		next.ServeHTTP(w, r.WithContext(observability.WithTraceID(r.Context(), id)))
	})
}

// statusWriter 记下状态码与字节数，供访问日志用。
type statusWriter struct {
	http.ResponseWriter
	status int
	bytes  int
}

func (w *statusWriter) WriteHeader(code int) {
	if w.status == 0 {
		w.status = code
	}
	w.ResponseWriter.WriteHeader(code)
}

func (w *statusWriter) Write(p []byte) (int, error) {
	if w.status == 0 {
		w.status = http.StatusOK
	}
	n, err := w.ResponseWriter.Write(p)
	w.bytes += n
	return n, err
}

// RequestLogger 每个请求一行结构化访问日志（含 trace_id）。
func RequestLogger(logger *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			rec := &statusWriter{ResponseWriter: w}
			defer func() {
				observability.WithTrace(logger, r.Context()).Info("http_request",
					"method", r.Method,
					"path", r.URL.Path,
					"status", rec.status,
					"bytes", rec.bytes,
					"duration_ms", float64(time.Since(start).Microseconds())/1000,
				)
			}()
			next.ServeHTTP(rec, r)
		})
	}
}

// Recover 把 panic 转成 500 信封：连接不裸断，日志里带堆栈与 trace_id。
func Recover(logger *slog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			defer func() {
				if v := recover(); v != nil {
					observability.WithTrace(logger, r.Context()).Error("panic_recovered",
						"panic", v, "path", r.URL.Path, "stack", string(debug.Stack()))
					// 文案与生产侧 backend/core/exceptions.py:unhandled_error_handler 逐字一致
					// （注意是小写 s 的 "server error"）；此前这里写的是 "Internal Server Error"，
					// 那是 Starlette **没注册** handler 时的纯文本兜底，本项目注册了，所以以注册的那句为准。
					WriteError(w, http.StatusInternalServerError, "Internal server error")
				}
			}()
			next.ServeHTTP(w, r)
		})
	}
}
