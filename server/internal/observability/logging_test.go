package observability

import (
	"context"
	"encoding/json"
	"log/slog"
	"regexp"
	"strings"
	"testing"
)

var hexID = regexp.MustCompile(`^[0-9a-f]{16}$`)

func TestNewTraceID(t *testing.T) {
	id := NewTraceID()
	if !hexID.MatchString(id) {
		t.Fatalf("trace_id 应是 16 位十六进制，得到 %q", id)
	}
	seen := make(map[string]bool, 500)
	for range 500 {
		next := NewTraceID()
		if seen[next] {
			t.Fatalf("第 %d 次生成出现重复 id %q，碰撞风险不可接受", len(seen)+1, next)
		}
		seen[next] = true
	}
}

func TestTraceIDContextRoundTrip(t *testing.T) {
	if got := TraceID(context.Background()); got != "" {
		t.Fatalf("没有追踪号时应返回空串，得到 %q", got)
	}
	ctx := WithTraceID(context.Background(), "abc123")
	if got := TraceID(ctx); got != "abc123" {
		t.Fatalf("取回的值不对: %q", got)
	}
}

// 日志是跨语言排查的唯一线索：必须是单行 JSON、带 service，
// WithTrace 之后还要带上当前请求的 trace_id。
func TestLoggerOutputsJSONWithServiceAndTrace(t *testing.T) {
	var buf strings.Builder
	base := slog.New(slog.NewJSONHandler(&buf, nil)).With("service", "go-api")
	ctx := WithTraceID(context.Background(), "feedfacefeedface")

	WithTrace(base, ctx).Info("http_request", "path", "/api/v1/health")

	var record map[string]any
	if err := json.Unmarshal([]byte(buf.String()), &record); err != nil {
		t.Fatalf("日志行必须是 JSON: %v / %q", err, buf.String())
	}
	if record["service"] != "go-api" || record["trace_id"] != "feedfacefeedface" {
		t.Fatalf("缺少 service 或 trace_id: %v", record)
	}
	if record["msg"] != "http_request" {
		t.Fatalf("msg 不对: %v", record)
	}

	buf.Reset()
	WithTrace(base, context.Background()).Info("worker_idle")
	var idle map[string]any
	if err := json.Unmarshal([]byte(buf.String()), &idle); err != nil {
		t.Fatal(err)
	}
	if _, ok := idle["trace_id"]; ok {
		t.Errorf("后台任务没有请求上下文，不该出现 trace_id 字段: %v", idle)
	}
}

func TestNewVerboseTurnsOnDebug(t *testing.T) {
	if !New("go-api", true).Enabled(context.Background(), slog.LevelDebug) {
		t.Error("开发环境应放行 Debug")
	}
	if New("go-api", false).Enabled(context.Background(), slog.LevelDebug) {
		t.Error("生产环境不该放行 Debug")
	}
}
