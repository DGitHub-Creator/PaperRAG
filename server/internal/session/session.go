// Package session 是 Go 接管的第一条**业务**读接口：会话列表与会话删除（P1-1）。
//
// 为什么不放进 internal/auth（那里写过偏好面的理由）：偏好面只需要"令牌→身份"和一套
// 请求体解码，而会话面要路径参数、要 COUNT、要复刻 naive TIMESTAMP 的序列化形状。
// 把这些塞进 auth 只会让那个包长成"所有和登录有关的东西"——而后面每接管一条业务面
// 都会往里加，归属就再也说不清了。所以这里只借 auth 的身份解析，数据访问自己有一份。
//
// 真相只有一份：Python 侧的 ConversationStorage 也是直连 chat_sessions / chat_messages
// （Redis 只是缓存，`conversation_storage.py:137-218`），所以这不是双写，是同一张表的第二个读者。
package session

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"

	"github.com/jackc/pgx/v5/pgtype"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/auth"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
)

// ErrStoreUnavailable 表示服务装配时没塞 Store（单测之外的进程都应给真的）。
var ErrStoreUnavailable = errors.New("会话读写面未装配")

// Store 是本包需要的数据访问面，由 *db.Queries 实现（emit_interface: false，故在消费方定义）。
type Store interface {
	ListSessionInfosForUser(ctx context.Context, userID int32) ([]db.ListSessionInfosForUserRow, error)
	DeleteSessionForUser(ctx context.Context, arg db.DeleteSessionForUserParams) (int64, error)
	ListMessagesForUserSession(ctx context.Context, arg db.ListMessagesForUserSessionParams) ([]db.ListMessagesForUserSessionRow, error)
}

// Info 对应 backend/schemas/schemas.py:286 的 SessionInfo（response_model 会把它投影成这三个键）。
type Info struct {
	SessionID string `json:"session_id"`
	UpdatedAt string `json:"updated_at"`
	// MessageCount 是 chat_messages 的行数，由查询里的 COUNT 给出
	MessageCount int32 `json:"message_count"`
}

// Message 对应 backend/schemas/schemas.py:211 的 MessageInfo：四个键恒在。
//
// RagTrace 用 json.RawMessage 而不是具体结构体：投影在 trace.go 里按 openapi 声明做完，
// 这里只负责按 Python 的键序把它塞进响应。nil 会序列化成 `null`，正是"无追踪/不合法"的对外形状。
type Message struct {
	Type      string          `json:"type"`
	Content   string          `json:"content"`
	Timestamp string          `json:"timestamp"`
	RagTrace  json.RawMessage `json:"rag_trace"`
}

// ListResponse 对应 SessionListResponse。空列表必须是 `[]` 而不是 `null`——
// 前端 `sessions.map(...)` 对 null 会炸，而 Python 侧返回的一直是空数组。
type ListResponse struct {
	Sessions []Info `json:"sessions"`
}

// DetailResponse 对应 SessionMessagesResponse；同样禁止 null（`messages.map` 是前端的常态写法）。
type DetailResponse struct {
	Messages []Message `json:"messages"`
}

// DeleteResponse 对应 SessionDeleteResponse；message 那句是逐字照抄，不做 i18n。
type DeleteResponse struct {
	SessionID string `json:"session_id"`
	Message   string `json:"message"`
}

const deletedMessage = "Session deleted"

// Service 是会话业务面：不碰 HTTP。
type Service struct {
	Auth   *auth.Service
	Store  Store
	Logger *slog.Logger
}

// List 返回当前用户的会话摘要，按最后更新时间倒序。
//
// Go 与 Python 均直接读 PG，不缓存会话；数据库异常由 handler 返回错误。
func (s *Service) List(ctx context.Context, identity *auth.Identity) (*ListResponse, error) {
	if s.Store == nil {
		return nil, ErrStoreUnavailable
	}
	rows, err := s.Store.ListSessionInfosForUser(ctx, identity.ID)
	if err != nil {
		return nil, fmt.Errorf("查询会话列表失败: %w", err)
	}
	// 预分配并显式建空切片：rows 为 nil 时 make(...,0,0) 仍序列化出 []
	items := make([]Info, 0, len(rows))
	for _, row := range rows {
		items = append(items, Info{
			SessionID:    row.SessionID,
			UpdatedAt:    isoFormat(row.UpdatedAt),
			MessageCount: row.MessageCount,
		})
	}
	return &ListResponse{Sessions: items}, nil
}

// Detail 返回当前用户某个会话的消息，按写入顺序（chat_messages.id 升序，不是时间序）。
//
// "会话不存在"与"会话属于别人"都返回 200 + 空数组，而不是 404：这是 Python 侧
// `backend/api/sessions.py:21` 的既有行为，前端按 `messages.length` 判空。改成 404 会多给
// 一个"这个会话号存在"的信号，而当前这条接口本来就不做任何存在性判断——接管不换语义（设计审查 §8）。
func (s *Service) Detail(ctx context.Context, identity *auth.Identity, sessionID string) (*DetailResponse, error) {
	if s.Store == nil {
		return nil, ErrStoreUnavailable
	}
	rows, err := s.Store.ListMessagesForUserSession(ctx, db.ListMessagesForUserSessionParams{
		UserID:    identity.ID,
		SessionID: sessionID,
	})
	if err != nil {
		return nil, fmt.Errorf("查询会话消息失败: %w", err)
	}
	items := make([]Message, 0, len(rows))
	for _, row := range rows {
		items = append(items, Message{
			Type:      row.MessageType,
			Content:   row.Content,
			Timestamp: isoFormat(row.Timestamp),
			// 投影失败只让 rag_trace 变 null：已保存正文是用户资产，不能被一条历史追踪拖垮
			// （与 schemas.py:225 的 wrap 校验器同一口径，台账 C34）。
			RagTrace: projectTrace(row.RagTrace),
		})
	}
	return &DetailResponse{Messages: items}, nil
}

// Delete 删除当前用户名下那个会话；第二个返回值是"真的删掉了行"，
// false 覆盖两种情况——不存在、以及属于别人，两者对外都是同一句 404（不给归属探测留缝）。
func (s *Service) Delete(ctx context.Context, identity *auth.Identity, sessionID string) (bool, error) {
	if s.Store == nil {
		return false, ErrStoreUnavailable
	}
	affected, err := s.Store.DeleteSessionForUser(ctx, db.DeleteSessionForUserParams{
		UserID:    identity.ID,
		SessionID: sessionID,
	})
	if err != nil {
		return false, fmt.Errorf("删除会话失败: %w", err)
	}
	if affected == 0 {
		return false, nil
	}
	s.Logger.Info("会话已删除", "user_id", identity.ID, "session_id", sessionID)
	return true, nil
}

// isoFormat 复刻 Python 对 **naive** datetime 调 `.isoformat()` 的结果：
// 秒以下只在非零时出现且固定 6 位，且绝不带时区后缀。
//
// 不能用 time.RFC3339Nano：它把零纳秒省成"没有"是对的，但非零时按 1–9 位可变长度输出
// （`.1` 而不是 `.100000`），而且 Go 的 time.Time 总带 location，格式串里稍不注意就多个 `Z`。
// 库里这三列都是 `TIMESTAMP`（无时区，见 000001 与 timestamp-audit.md），
// pgx 会按 UTC 给一个 time.Time——所以这里**只取墙上时钟的字段**，不做任何时区换算。
func isoFormat(ts pgtype.Timestamp) string {
	if !ts.Valid {
		return ""
	}
	t := ts.Time
	out := t.Format("2006-01-02T15:04:05")
	if us := t.Nanosecond() / 1000; us != 0 {
		out += fmt.Sprintf(".%06d", us)
	}
	return out
}
