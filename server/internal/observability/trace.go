// Package observability 提供 slog 配置与 trace_id 传播。
package observability

import (
	"context"
	"crypto/rand"
	"encoding/hex"
)

// TraceIDHeader 是跨进程传递请求追踪号的头。Go 在边缘生成或沿用，注入后透传给 Python，
// 两端日志因此能按同一个 id 关联。
// ⚠️ 这个名字目前只是**两端代码里的共同约定**，还没进 contracts/openapi.yaml
// （原先注释写"由 P0-4 写进契约锁定"是假的，grep 得到 0 次命中）。补进契约是
// G01 设计审查批准后的动作，差距登记在台账 C38——别把"打算锁定"读成"已锁定"。
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
