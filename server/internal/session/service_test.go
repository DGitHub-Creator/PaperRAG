package session

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgtype"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/auth"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
)

// ── 测试替身 ──────────────────────────────────────────────────────────

type fakeStore struct {
	rows       []db.ListSessionInfosForUserRow
	listErr    error
	deleted    int64
	deleteErr  error
	deleteSeen db.DeleteSessionForUserParams

	messages     []db.ListMessagesForUserSessionRow
	messagesErr  error
	messagesSeen db.ListMessagesForUserSessionParams
}

func (f *fakeStore) ListSessionInfosForUser(context.Context, int32) ([]db.ListSessionInfosForUserRow, error) {
	return f.rows, f.listErr
}

func (f *fakeStore) DeleteSessionForUser(_ context.Context, arg db.DeleteSessionForUserParams) (int64, error) {
	f.deleteSeen = arg
	return f.deleted, f.deleteErr
}

func (f *fakeStore) ListMessagesForUserSession(_ context.Context, arg db.ListMessagesForUserSessionParams) ([]db.ListMessagesForUserSessionRow, error) {
	f.messagesSeen = arg
	return f.messages, f.messagesErr
}

// fakeUsers 只需要满足 /me 那一条查询：令牌换身份靠的是 GetProfileByUsername。
type fakeUsers struct{ err error }

func (f fakeUsers) GetProfileByUsername(context.Context, string) (db.GetProfileByUsernameRow, error) {
	if f.err != nil {
		return db.GetProfileByUsernameRow{}, f.err
	}
	return db.GetProfileByUsernameRow{ID: 7, Username: "alice", Role: "user"}, nil
}

func (f fakeUsers) GetUserByUsername(context.Context, string) (db.User, error) {
	return db.User{}, errors.New("本切片用不到：角色一律回库取，走的是 GetProfileByUsername")
}

func (f fakeUsers) InsertUser(context.Context, db.InsertUserParams) (db.InsertUserRow, error) {
	return db.InsertUserRow{}, errors.New("会话切片不写 users")
}

func (f fakeUsers) UpdateUserPasswordByUsername(context.Context, db.UpdateUserPasswordByUsernameParams) (db.UpdateUserPasswordByUsernameRow, error) {
	return db.UpdateUserPasswordByUsernameRow{}, errors.New("会话切片不改口令")
}

func nopLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

const testSecret = "test-secret"

func newTestService(store Store) *Service {
	tokens := auth.TokenConfig{Secret: testSecret, ExpireMinutes: 60, RefreshExpireDays: 30}
	return &Service{Auth: auth.NewService(fakeUsers{}, tokens, 40000, "", 8, nopLogger()), Store: store, Logger: nopLogger()}
}

func timestamp(y int, mo time.Month, d, hh, mm, ss, us int) pgtype.Timestamp {
	return pgtype.Timestamp{Time: time.Date(y, mo, d, hh, mm, ss, us*1000, time.UTC), Valid: true}
}

// ── isoFormat：Python datetime.isoformat() 的形状，不是 RFC3339 ────────

func TestISOFormatMatchesPythonIsoformat(t *testing.T) {
	cases := []struct {
		name string
		ts   pgtype.Timestamp
		want string
	}{
		{"微秒为 0 时整段省略", timestamp(2026, 10, 14, 7, 8, 9, 0), "2026-10-14T07:08:09"},
		{"非零微秒固定 6 位", timestamp(2026, 10, 14, 7, 8, 10, 123456), "2026-10-14T07:08:10.123456"},
		{"1 微秒补零到 6 位", timestamp(2026, 10, 14, 7, 8, 10, 1), "2026-10-14T07:08:10.000001"},
		{"不补零到 6 位是 RFC3339Nano 的行为", timestamp(2026, 10, 14, 7, 8, 10, 500000), "2026-10-14T07:08:10.500000"},
		{"NULL 列给空串而不是 panic", pgtype.Timestamp{}, ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := isoFormat(tc.ts); got != tc.want {
				t.Errorf("isoFormat = %q，期望 %q", got, tc.want)
			}
		})
	}
}

func TestISOFormatHasNoZoneSuffix(t *testing.T) {
	// 库里是 TIMESTAMP（无时区）。带出 Z 或 +08:00 就说明有人做了时区换算，
	// 而 timestamp-audit.md 量过：这类列一旦混进时区换算就是 8 小时的显示偏差。
	got := isoFormat(timestamp(2026, 10, 14, 7, 8, 9, 0))
	if len(got) != 19 {
		t.Errorf("naive 值应当正好 19 个字符（无时区后缀），实得 %d：%q", len(got), got)
	}
	if strings.HasSuffix(got, "Z") || strings.Contains(got[len(got)-6:], "+") {
		t.Errorf("不该带时区后缀：%q", got)
	}
}

// ── List ─────────────────────────────────────────────────────────────

func TestListEmptyIsArrayNotNull(t *testing.T) {
	svc := newTestService(&fakeStore{rows: nil})
	out, err := svc.List(context.Background(), &auth.Identity{ID: 7, Username: "alice", Role: "user"})
	if err != nil {
		t.Fatal(err)
	}
	if out.Sessions == nil {
		t.Fatal("空列表必须是 []，nil 会序列化成 null，前端 .map() 直接炸")
	}
	if len(out.Sessions) != 0 {
		t.Errorf("期望 0 条，实得 %d", len(out.Sessions))
	}
}

func TestListProjectsRowsIntoContractShape(t *testing.T) {
	svc := newTestService(&fakeStore{rows: []db.ListSessionInfosForUserRow{
		{SessionID: "s-new", UpdatedAt: timestamp(2026, 10, 14, 7, 8, 10, 123456), MessageCount: 2},
		{SessionID: "s-old", UpdatedAt: timestamp(2026, 10, 13, 9, 0, 0, 0), MessageCount: 0},
	}})
	out, err := svc.List(context.Background(), &auth.Identity{ID: 7})
	if err != nil {
		t.Fatal(err)
	}
	if len(out.Sessions) != 2 {
		t.Fatalf("期望 2 条，实得 %d", len(out.Sessions))
	}
	if out.Sessions[0].SessionID != "s-new" || out.Sessions[0].UpdatedAt != "2026-10-14T07:08:10.123456" {
		t.Errorf("第一条不对：%+v", out.Sessions[0])
	}
	if out.Sessions[1].MessageCount != 0 || out.Sessions[1].UpdatedAt != "2026-10-13T09:00:00" {
		t.Errorf("第二条不对：%+v", out.Sessions[1])
	}
}

func TestListPropagatesStoreError(t *testing.T) {
	// 与 Python 的**有意分歧**（那边把异常吞成空列表）：这里必须如实报错，
	// 否则"读不出来"会伪装成"你没有会话"。
	svc := newTestService(&fakeStore{listErr: errors.New("boom")})
	if _, err := svc.List(context.Background(), &auth.Identity{ID: 7}); err == nil {
		t.Fatal("存储层失败必须上抛，不许静默回空列表")
	}
}

func TestListWithoutStoreIsError(t *testing.T) {
	svc := newTestService(nil)
	if _, err := svc.List(context.Background(), &auth.Identity{ID: 7}); !errors.Is(err, ErrStoreUnavailable) {
		t.Errorf("未装配 Store 应回 ErrStoreUnavailable，实得 %v", err)
	}
}

// ── Delete ───────────────────────────────────────────────────────────

func TestDeleteUsesUserIDAndSessionID(t *testing.T) {
	store := &fakeStore{deleted: 1}
	svc := newTestService(store)
	deleted, err := svc.Delete(context.Background(), &auth.Identity{ID: 7}, "s-a")
	if err != nil || !deleted {
		t.Fatalf("deleted=%v err=%v", deleted, err)
	}
	if store.deleteSeen.UserID != 7 || store.deleteSeen.SessionID != "s-a" {
		t.Errorf("删除条件必须同时带 user_id 与 session_id，实得 %+v", store.deleteSeen)
	}
}

func TestDeleteZeroRowsIsNotDeleted(t *testing.T) {
	// 不存在与"属于别人"必须走同一个 false 分支——分开返回会让这个接口变成归属探测器。
	svc := newTestService(&fakeStore{deleted: 0})
	deleted, err := svc.Delete(context.Background(), &auth.Identity{ID: 7}, "nope")
	if err != nil {
		t.Fatal(err)
	}
	if deleted {
		t.Error("0 行不得算成已删除")
	}
}
