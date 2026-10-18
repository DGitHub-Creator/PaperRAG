// Package observability 提供 slog 配置与 trace_id 传播。
package observability

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"regexp"
)

// TraceIDHeader 是跨进程传递请求追踪号的头。Go 在边缘生成或沿用，注入后透传给 Python，
// 两端日志因此能按同一个 id 关联。
// 头名与接受集合已进契约（`contracts/openapi.yaml` 的 `components.parameters.TraceId`，
// 台账 C38  closes）；改这里的规则会同时被 `scripts/check_contracts.py` 和契约核对拦住。
const TraceIDHeader = "X-Trace-Id"

// TraceIDRule 是契约声明的接受集合：1–128 个 ASCII 字母、数字、`.`、`_`、`-`。
// 三处（契约 / 这里 / backend/core/logging_config.py）必须是同一串字面量，由门禁核对。
const TraceIDRule = `^[A-Za-z0-9._-]{1,128}$`

var traceIDPattern = regexp.MustCompile(TraceIDRule)

type traceIDKey struct{}

// SanitizeTraceID 决定本次请求用哪个追踪号：入站合法就沿用，非法或缺失就生成新的。
// 非法值**不回显**（响应头里只会是这里的返回值），也不参与认证或授权判定。
// 用 regexp 而不是手写长度检查，是为了让契约的 pattern 与实现只有一个差异点：那份 pattern 本身。
func SanitizeTraceID(inbound string) string {
	if traceIDPattern.MatchString(inbound) {
		return inbound
	}
	return NewTraceID()
}

// NewTraceID 生成 16 位十六进制追踪号。用 crypto/rand 而非 math/rand：
// 追踪号会出现在日志与响应头里，可预测的 id 等于给请求关联做了个公开序号。
// Python 直连时生成 32 位；两侧只统一**接受集合**，不统一生成长度（设计审查 §6 第 1 项）。
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
