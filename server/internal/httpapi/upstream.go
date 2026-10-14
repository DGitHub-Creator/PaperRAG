package httpapi

import (
	"log/slog"
	"net/http"
	"net/http/httputil"
	"net/url"
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
	// 信封只能有一处形状（01 §6.3）：上游不可达/超时时给 {"detail": ...}，
	// 与其余错误同形，前端的 detailFromJson 不必为这一条单独分支。
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		logger.Error("upstream_proxy_failed", "method", r.Method, "path", r.URL.Path, "error", err)
		WriteError(w, http.StatusBadGateway, "上游服务不可用")
	}
	return proxy
}
