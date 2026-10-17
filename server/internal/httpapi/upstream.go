package httpapi

import (
	"log/slog"
	"net/http"
	"net/http/httputil"
	"net/url"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/observability"
)

// NewUpstreamProxy 把 Go 尚未接管的路径转发给 Python 上游（14 §19 铁律 2「门面先于重写」）。
//
// 为什么用 httputil 的 ReverseProxy 而不是自己拼 http.Request：它已经处理了
// WebSocket 升级（Connection: Upgrade 时接管连接做双向拷贝）、Trailer、以及
// 流式响应的逐块 flush——这三样正是 /api/v1/ws/chat 与 /chat/stream 需要的，
// 手写一定会漏，而漏了的表现是"连上了但不推流"，最难排查。
//
// 路径与查询串原样转发；不裁剪前缀，因为上游 Python 的路由就是按完整路径挂的
// （backend/app.py 把 auth 挂在 /api/v1，documents 也挂在 /api/v1）。
func NewUpstreamProxy(target *url.URL, logger *slog.Logger) http.Handler {
	if logger == nil {
		logger = slog.Default()
	}
	proxy := httputil.NewSingleHostReverseProxy(target)
	director := proxy.Director
	proxy.Director = func(r *http.Request) {
		director(r)
		// 新生成的追踪号也必须到达 Python，不能只出现在 Go 的响应头里。
		r.Header.Set(observability.TraceIDHeader, observability.TraceID(r.Context()))
	}
	// 响应侧归一：Python 的 _trace_middleware 也会回写这个头，而 ReverseProxy 是
	// **逐值 Add**，Go 先前 Set 的那一份不会被覆盖——2026-10-17 真栈实测
	// `curl -D - :8080/metrics` 看到同一行出现两次（台账 C38）。
	//
	// 这里**删掉上游那份**而不是覆盖：Trace 中间件在进代理之前就已经把权威值 Set 进
	// w.Header()，代理再 Add 一次才是重复的来源；把 ModifyResponse 写成 Set 只把
	// 上游的 2 个值收成 1 个，总量仍是 2（第一版就是这么错的，被单测当场抓住）。
	// 上游的回写本来就是同一值的重复表达，删掉不丢信息；追踪号由 Go 单点决定。
	proxy.ModifyResponse = func(res *http.Response) error {
		res.Header.Del(observability.TraceIDHeader)
		return nil
	}
	// 信封只能有一处形状（01 §6.3）：上游不可达/超时时给 {"detail": ...}，
	// 与其余错误同形，前端的 detailFromJson 不必为这一条单独分支。
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		observability.WithTrace(logger, r.Context()).Error("上游转发失败", "method", r.Method, "path", r.URL.Path, "error", err)
		WriteError(w, http.StatusBadGateway, "上游服务不可用")
	}
	return proxy
}
