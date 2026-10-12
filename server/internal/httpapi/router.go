package httpapi

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
)

// Check 是一项就绪探测。Name 是响应里 checks 对象的键，与 Python 侧现有键
// （database/redis/milvus）对齐，切换后端时监控不必改解析。
type Check struct {
	Name  string
	Probe func(ctx context.Context) (bool, string)
}

// Deps 是路由的依赖注入面：单测在这里塞 fake probe，不必真连数据库。
type Deps struct {
	Logger  *slog.Logger
	Version string
	Checks  []Check
	Timeout time.Duration
}

// NewRouter 组装 go-api 的路由：中间件、404/405 信封、存活与就绪探针。
//
// 返回 *chi.Mux 而不是 http.Handler，是为了让**业务路由在调用方挂载**（cmd/api）。
// 业务 handler 在 internal/auth 里，而 auth 要用本包的 WriteJSON/WriteError 写信封——
// 若在这里 import auth 就成环了。信封只能有一处实现（两种形状正是 01 §6.3 记的坑），
// 所以环从这里断开：本包不认识 auth，auth 认识本包。
// *chi.Mux 本身就实现了 http.Handler，既有调用方不受影响。
func NewRouter(d Deps) *chi.Mux {
	if d.Timeout <= 0 {
		d.Timeout = 3 * time.Second
	}
	r := chi.NewRouter()
	r.Use(Trace, RequestLogger(d.Logger), Recover(d.Logger))
	r.NotFound(http.HandlerFunc(NotFound))
	r.MethodNotAllowed(http.HandlerFunc(MethodNotAllowed))

	r.Get("/api/v1/health", HealthHandler(d))
	r.Get("/api/v1/ready", ReadyHandler(d))
	// 根路径别名：Python 现在把这两条挂在根上（01 §2 第 1、2 条），compose healthcheck 与
	// 监控脚本打的都是根路径；nginx upstream 切到 Go 时不能让它们凭空变 404。
	r.Get("/health", HealthHandler(d))
	r.Get("/ready", ReadyHandler(d))
	return r
}

type checkStatus struct {
	Status string `json:"status"`
	Detail string `json:"detail"`
}

// HealthHandler 是存活探针：只回答"进程在不在"，不碰任何依赖。
// go-worker 不挂 /api/v1（02 §2：只有 go-api 面向浏览器），故单独导出。
func HealthHandler(d Deps) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		WriteJSON(w, http.StatusOK, map[string]any{"status": "ok", "version": d.Version})
	}
}

// ReadyHandler 是就绪探针：并发跑所有探测，单项超时不拖垮整体
// （与 backend/api/health.py 的语义逐字对齐）。
func ReadyHandler(d Deps) http.HandlerFunc {
	timeout := d.Timeout
	if timeout <= 0 {
		timeout = 3 * time.Second
	}
	return func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), timeout)
		defer cancel()

		results := make([]checkStatus, len(d.Checks))
		var wg sync.WaitGroup
		for i, c := range d.Checks {
			wg.Add(1)
			go func(i int, c Check) {
				defer wg.Done()
				results[i] = runCheck(ctx, d.Logger, c, timeout)
			}(i, c)
		}
		wg.Wait()

		checks := make(map[string]checkStatus, len(results))
		allOK := true
		for i, c := range d.Checks {
			checks[c.Name] = results[i]
			if results[i].Status != "ok" {
				allOK = false
			}
		}

		body := map[string]any{"version": d.Version, "checks": checks}
		if !allOK {
			d.Logger.Warn("readiness_failed", "checks", checks)
			// Python 侧失败时走 HTTPException(detail={...})，线上形状是 {"detail": {...}}
			body["status"] = "unhealthy"
			WriteError(w, http.StatusServiceUnavailable, body)
			return
		}
		body["status"] = "ok"
		WriteJSON(w, http.StatusOK, body)
	}
}

func runCheck(ctx context.Context, logger *slog.Logger, c Check, timeout time.Duration) checkStatus {
	type outcome struct {
		ok     bool
		detail string
	}
	done := make(chan outcome, 1)
	go func() {
		defer func() {
			if v := recover(); v != nil {
				done <- outcome{false, fmt.Sprintf("error: %v", v)}
			}
		}()
		ok, detail := c.Probe(ctx)
		done <- outcome{ok, detail}
	}()

	select {
	case o := <-done:
		if o.ok {
			return checkStatus{Status: "ok", Detail: o.detail}
		}
		logger.Debug("readiness_check_failed", "name", c.Name, "detail", o.detail)
		return checkStatus{Status: "error", Detail: o.detail}
	case <-ctx.Done():
		return checkStatus{Status: "error", Detail: fmt.Sprintf("timeout after %ds", int(timeout.Seconds()))}
	}
}
