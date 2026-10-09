// Package observability 提供 slog 配置与 trace_id 传播。
package observability

import (
	"context"
	"crypto/rand"
	"encoding/hex"
)

// TraceIDHeader 是跨进程传递请求追踪号的头。Go 注入后透传给 Python，
// 两端日志用同一个 id 关联；该名字由 P0-4 写进 contracts/openapi.yaml 锁定。
const TraceIDHeader = "X-Trace-Id"

type traceIDKey struct{}

// NewTraceID 生成 16 位十六进制追踪号。用 crypto/rand 而非 math/rand：
// 追踪号会出现在日志与响应头里，可预测的 id 等于给请求关联做了个公开序号。
func NewTraceID() string {
	var b [8]byte
	// crypto/rand.Read 在受支持的平台上不会失败，失败路径无需为骨架阶段编造兜底
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}

// WithTraceID 把追踪号放进 context。
func WithTraceID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, traceIDKey{}, id)
}

// TraceID 取回追踪号；不存在时返回空串（后台任务没有请求上下文属正常）。
func TraceID(ctx context.Context) string {
	if v, ok := ctx.Value(traceIDKey{}).(string); ok {
		return v
	}
	return ""
}
