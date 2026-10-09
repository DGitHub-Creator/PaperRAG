package observability

import (
	"context"
	"log/slog"
	"os"
)

// New 建 JSON 结构的 slog logger，固定带上 service 字段。
//
// JSON 是唯一形态：容器里 stdout 由 Docker Desktop / k8s 采集，人读由外部工具负责，
// Go 侧不再维护第二套"漂亮输出"（Python 的 JSON_LOG 键属其历史行为，P1 迁移时一并收敛）。
func New(service string, verbose bool) *slog.Logger {
	level := slog.LevelInfo
	if verbose {
		level = slog.LevelDebug
	}
	return slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: level})).
		With("service", service)
}

// WithTrace 派生一个带当前请求 trace_id 的 logger；没有追踪号（后台任务）时原样返回。
func WithTrace(logger *slog.Logger, ctx context.Context) *slog.Logger {
	if id := TraceID(ctx); id != "" {
		return logger.With("trace_id", id)
	}
	return logger
}
