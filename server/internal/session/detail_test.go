package session

// 会话详情（GET /api/v1/sessions/{session_id}）的 Go 侧单测（P1-1 第二切片）。
//
// 这里只锁"Go 自己那半截"的正确性：过滤键、空数组、naive 时间形状、坏历史追踪只丢追踪不丢正文。
// 跨语言是否逐字相同不在单测的射程里——那是 tests/chain/test_go_read_session_detail.py 的判据。

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/auth"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
)

func detailRow(messageType, content string, trace string) db.ListMessagesForUserSessionRow {
	ts := timestamp(2026, 10, 14, 7, 8, 10, 123456)
	row := db.ListMessagesForUserSessionRow{MessageType: messageType, Content: content, Timestamp: ts}
	if trace != "" {
		row.RagTrace = []byte(trace)
	}
	return row
}

func TestDetailQueriesByUserIDAndSessionID(t *testing.T) {
	store := &fakeStore{}
	if _, err := newTestService(store).Detail(context.Background(), &auth.Identity{ID: 7}, "s-1"); err != nil {
		t.Fatal(err)
	}
	if store.messagesSeen.UserID != 7 || store.messagesSeen.SessionID != "s-1" {
		t.Errorf("必须按 (user_id, session_id) 过滤，实得 %+v", store.messagesSeen)
	}
}

func TestDetailWithoutStoreIsError(t *testing.T) {
	// 空实现冒充迁移是禁的（08 §10）：没装配 Store 必须报错，不能回 {"messages": []} 装成"读到了空会话"。
	if _, err := (&Service{Logger: nopLogger()}).Detail(context.Background(), &auth.Identity{ID: 7}, "s"); err == nil {
		t.Fatal("期望 ErrStoreUnavailable")
	} else if !errors.Is(err, ErrStoreUnavailable) {
		t.Fatalf("期望 ErrStoreUnavailable，实得 %v", err)
	}
}

func TestDetailEmptyResultSerialisesAsArray(t *testing.T) {
	// 不存在的会话、别人的会话都走到这里：200 + {"messages": []}，没有 404 这条分支。
	rec := do(t, newRouter(newTestService(&fakeStore{})), http.MethodGet, "/api/v1/sessions/nope", "Bearer "+aliceToken(t))
	if rec.Code != http.StatusOK {
		t.Fatalf("未知会话应 200（与 Python 一致），实得 %d：%s", rec.Code, rec.Body.String())
	}
	if body := rec.Body.String(); body != `{"messages":[]}` {
		t.Errorf(`空结果必须恰好是 {"messages":[]}，实得 %s`, body)
	}
}

func TestDetailRequiresAuthenticationBeforeAnythingElse(t *testing.T) {
	rec := do(t, newRouter(newTestService(&fakeStore{})), http.MethodGet, "/api/v1/sessions/whatever", "")
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("无令牌必须 401，实得 %d", rec.Code)
	}
	if body := bodyOf(t, rec); body["detail"] != "Not authenticated" {
		t.Errorf("401 文案与 Python 不同：%v", body["detail"])
	}
}

func TestDetailMessageShapeAndTimeFormat(t *testing.T) {
	store := &fakeStore{messages: []db.ListMessagesForUserSessionRow{
		detailRow("human", "问题", ""),
		detailRow("ai", "回答", `{"tool_used":true,"tool_name":"rag","query":"问题"}`),
	}}
	rec := do(t, newRouter(newTestService(store)), http.MethodGet, "/api/v1/sessions/s-1", "Bearer "+aliceToken(t))
	if rec.Code != http.StatusOK {
		t.Fatalf("期望 200，实得 %d：%s", rec.Code, rec.Body.String())
	}
	var out struct {
		Messages []Message `json:"messages"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatal(err)
	}
	if len(out.Messages) != 2 {
		t.Fatalf("两行消息都要出来，实得 %d", len(out.Messages))
	}
	// naive TIMESTAMP 的 isoformat 形状：6 位微秒、无时区后缀（列语义与列表接口同一条）
	if got := out.Messages[0].Timestamp; got != "2026-10-14T07:08:10.123456" {
		t.Errorf("时间形状不对：%s", got)
	}
	if out.Messages[0].RagTrace != nil && string(out.Messages[0].RagTrace) != "null" {
		t.Errorf("非 RAG 消息的 rag_trace 必须是 null，实得 %s", out.Messages[0].RagTrace)
	}
	body := rec.Body.String()
	if !strings.Contains(body, `"rag_trace":{"tool_used":true,"tool_name":"rag","query":"问题"`) {
		t.Errorf("追踪没按声明顺序投影：%s", body)
	}
	// 键序即契约：type/content/timestamp/rag_trace，与 MessageInfo 的声明顺序一致
	if !strings.HasPrefix(body, `{"messages":[{"type":"human","content":`) {
		t.Errorf("响应首键必须是 messages，且消息首键是 type：%s", body)
	}
}

func TestDetailKeepsAnswerWhenTraceIsUnusable(t *testing.T) {
	// 台账 C34 的口径：追踪不合法只让 rag_trace 变 null，正文必须原样留着。
	store := &fakeStore{messages: []db.ListMessagesForUserSessionRow{
		detailRow("ai", "MPC lets parties compute jointly.", `{"query":"mpc","sources":[{"filename":"mpc.pdf"}]}`),
	}}
	rec := do(t, newRouter(newTestService(store)), http.MethodGet, "/api/v1/sessions/s-1", "Bearer "+aliceToken(t))
	out := bodyOf(t, rec)
	items := out["messages"].([]any)
	msg := items[0].(map[string]any)
	if msg["rag_trace"] != nil {
		t.Errorf("缺 tool_used/tool_name 的历史追踪应投影成 null，实得 %v", msg["rag_trace"])
	}
	if msg["content"] != "MPC lets parties compute jointly." {
		t.Errorf("正文不能因为追踪不合法而丢失：%v", msg["content"])
	}
	if len(msg) != 4 {
		t.Errorf("消息恒为 4 个键，实得 %v", msg)
	}
}

func TestDetailStoreFailureIs500NotEmptyAnswer(t *testing.T) {
	// 把库失败伪装成"这个会话没有消息"是禁的：前端会显示空历史，而真相是查询挂了。
	store := &fakeStore{messagesErr: errors.New("connection reset by peer")}
	rec := do(t, newRouter(newTestService(store)), http.MethodGet, "/api/v1/sessions/s-1", "Bearer "+aliceToken(t))
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("库失败必须 500，实得 %d：%s", rec.Code, rec.Body.String())
	}
	if body := bodyOf(t, rec); body["detail"] != "Internal server error" {
		t.Errorf("500 文案与 Python 不同：%v", body["detail"])
	}
}

func TestTimestampHelperIsNaiveUTC(t *testing.T) {
	// 自校验：这些用例赖以断言的时间戳确实是 naive（无 offset），否则 isoFormat 的断言毫无意义。
	if got := timestamp(2026, time.October, 14, 7, 8, 10, 0).Time.Location(); got != time.UTC {
		t.Errorf("期望 UTC naive，实得 %v", got)
	}
}
