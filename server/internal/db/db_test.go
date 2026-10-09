package db

import (
	"context"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgtype"
)

// recordingDBTX 记下"将要发给 PG 的 SQL 与参数"，不连库。
// 这一层能机检的正是三样：SQL 文本、参数顺序与个数、生成的字段集合。
// 真库行为（unique violation 的具体约束名、timestamp 的时区语义）不在这里假装验证，
// 那是 P0-5 / P0-8 的 real 级证据。
type recordingDBTX struct {
	sql  string
	args []any
	// scanValues 的个数必须等于生成代码里 Scan 的目标个数；对不上就报错，
	// 于是"sqlc 重新生成后字段集合变了"会在这里红，而不是在线上以 nil 出现。
	scanValues []any
	scanErr    error
}

func (r *recordingDBTX) Exec(context.Context, string, ...any) (pgconn.CommandTag, error) {
	return pgconn.CommandTag{}, errors.New("本切片不该出现 Exec：写操作走 INSERT ... RETURNING")
}

func (r *recordingDBTX) Query(context.Context, string, ...any) (pgx.Rows, error) {
	return nil, errors.New("本切片不该出现多行 Query")
}

func (r *recordingDBTX) QueryRow(_ context.Context, sql string, args ...any) pgx.Row {
	r.sql = sql
	r.args = args
	return &fakeRow{values: r.scanValues, err: r.scanErr}
}

type fakeRow struct {
	values []any
	err    error
	done   bool
}

func (f *fakeRow) Scan(dest ...any) error {
	if f.err != nil {
		return f.err
	}
	if f.done {
		return errors.New("同一条 Row 被 Scan 了两次")
	}
	f.done = true
	if len(dest) != len(f.values) {
		return fmt.Errorf("Scan 目标数 %d 与 fake 值数 %d 不一致：生成代码的字段集合变了，测试要跟着改",
			len(dest), len(f.values))
	}
	// 逐个回写，且要求类型可赋值：这样"字段增删"和"字段类型变了"都会以测试失败的形式出现
	for i, d := range dest {
		target := reflect.ValueOf(d)
		if target.Kind() != reflect.Pointer || target.IsNil() {
			return fmt.Errorf("第 %d 个 Scan 目标不是非空指针: %T", i, d)
		}
		src := reflect.ValueOf(f.values[i])
		if !src.Type().AssignableTo(target.Elem().Type()) {
			return fmt.Errorf("第 %d 个字段类型不匹配：fake 给 %s，生成代码要 %s",
				i, src.Type(), target.Elem().Type())
		}
		target.Elem().Set(src)
	}
	return nil
}

func TestInsertUserPassesRoleAndCreatedAtExplicitly(t *testing.T) {
	db := &recordingDBTX{scanValues: []any{int32(1), "alice", "user", pgtype.Timestamp{}}}
	q := New(db)
	got, err := q.InsertUser(context.Background(), InsertUserParams{
		Username:     "alice",
		PasswordHash: "pbkdf2_sha256$260000$salt$digest",
		Role:         "user",
		CreatedAt:    pgtype.Timestamp{Time: time.Now().UTC(), Valid: true},
	})
	if err != nil {
		t.Fatalf("InsertUser: %v", err)
	}
	if got.ID != 1 || got.Username != "alice" {
		t.Fatalf("RETURNING 没被读回: %+v", got)
	}
	// 库里没有 DEFAULT，列清单漏一个就是 NOT NULL violation
	for _, col := range []string{"username", "password_hash", "role", "created_at"} {
		if !strings.Contains(db.sql, col) {
			t.Errorf("INSERT 未显式列出 %s: %s", col, db.sql)
		}
	}
	if len(db.args) != 4 {
		t.Fatalf("参数个数 %d，期望 4（顺序变了 $1..$4 就错位）", len(db.args))
	}
	if db.args[0] != "alice" || db.args[2] != "user" {
		t.Errorf("参数顺序不对: %#v", db.args)
	}
	if _, ok := db.args[3].(pgtype.Timestamp); !ok {
		t.Errorf("created_at 应以 timestamp 传，不该传字符串或 time.Time: %T", db.args[3])
	}
	if !strings.Contains(db.sql, "RETURNING") {
		t.Error("INSERT 缺 RETURNING：拿不到 id 就得回查，多开一个竞态窗口")
	}
}

func TestGetUserByIDNeverSelectsPasswordHash(t *testing.T) {
	// /me 的响应里绝不能出现密码哈希。在生成层就把这一列选掉，
	// 比指望每个 handler 都记得剔除可靠。
	db := &recordingDBTX{scanValues: []any{int32(1), "alice", "user", pgtype.Timestamp{}}}
	if _, err := New(db).GetUserByID(context.Background(), 1); err != nil {
		t.Fatalf("GetUserByID: %v", err)
	}
	if strings.Contains(db.sql, "password_hash") {
		t.Errorf("GetUserByID 选了 password_hash: %s", db.sql)
	}
	if strings.Contains(db.sql, "SELECT *") {
		t.Errorf("用了 SELECT *：将来加一列就漏进响应: %s", db.sql)
	}
}

func TestGetUserByUsernameSelectsPasswordHashForVerification(t *testing.T) {
	db := &recordingDBTX{scanValues: []any{int32(1), "alice", "hash", "user", pgtype.Timestamp{}}}
	if _, err := New(db).GetUserByUsername(context.Background(), "alice"); err != nil {
		t.Fatalf("GetUserByUsername: %v", err)
	}
	if !strings.Contains(db.sql, "password_hash") {
		t.Errorf("登录路径必须能读到 password_hash: %s", db.sql)
	}
}

func TestQueryErrorsArePassedThroughUnchanged(t *testing.T) {
	// 用户名重复要靠 PG 的 unique violation 由上层翻译成 409；
	// 生成层吞掉错误，上层就永远等不到那个信号。
	want := errors.New(`duplicate key value violates unique constraint "users_username_key"`)
	db := &recordingDBTX{scanErr: want}
	_, err := New(db).GetUserByUsername(context.Background(), "alice")
	if !errors.Is(err, want) {
		t.Fatalf("错误被改写: got %v want %v", err, want)
	}
}

func TestNewPoolRejectsEmptyDatabaseURL(t *testing.T) {
	// pgxpool 是惰性的：空串若被放过，调用方拿到的是一个"看起来能用"的池
	if _, err := NewPool(context.Background(), "", PoolOptions{}); err == nil {
		t.Fatal("空 DATABASE_URL 应当报错")
	}
}

func TestPoolOptionsDefaultsAreApplied(t *testing.T) {
	// compose 不传这些键时也要有确定值：pgx 里 MaxConns=0 的语义是"不限"，
	// 让零值直接进池等于给生产开一个无上限连接数。
	o := PoolOptions{}
	o.withDefaults()
	if o.MaxConns != 8 || o.MinConns != 1 || o.ConnectTimeout != 5*time.Second {
		t.Fatalf("默认值不对: %+v", o)
	}
	custom := PoolOptions{MaxConns: 2}
	custom.withDefaults()
	if custom.MaxConns != 2 || custom.HealthCheckPing != 3*time.Second {
		t.Fatalf("显式值应保留、缺省值应补齐: %+v", custom)
	}
}

func TestNewPoolFailsFastOnUnreachableHost(t *testing.T) {
	// 启动时 Ping 的意义就在这：连接串写错要在起进程时就炸，而不是第一个业务请求
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	pool, err := NewPool(ctx, "postgres://nope:nope@127.0.0.1:1/nope", PoolOptions{ConnectTimeout: time.Second})
	if err == nil {
		pool.Close()
		t.Fatal("不可达的连接串应当报错")
	}
	if !strings.Contains(err.Error(), "连接数据库失败") {
		t.Errorf("错误应当指明是 Ping 阶段: %v", err)
	}
}
