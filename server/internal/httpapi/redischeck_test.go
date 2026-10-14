package httpapi

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"net"
	"strconv"
	"strings"
	"testing"
	"time"
)

// fakeRedis 起一个会讲 RESP 的假服务端：按命令名查表决定怎么回话，并把收到的命令依次送进 got。
//
// 用真 TCP 而不是注入一个 dialer——这个探针的价值就在"真的会连、真的会按时撒手"，
// 把网络层抽象掉之后，超时那条用例就变成在测我自己的 mock 了。
// replyFor 返回空串表示"这条不回"，专门用来造挂死的对面。
func fakeRedis(t *testing.T, replyFor func(cmd string) string, got chan<- string) string {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = ln.Close() })

	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			go func(conn net.Conn) {
				defer conn.Close()
				reader := bufio.NewReader(conn)
				for {
					cmd, args, err := readRESPCommand(reader)
					if err != nil {
						return
					}
					if got != nil {
						got <- strings.ToUpper(cmd)
					}
					_ = args
					switch reply := replyFor(cmd); {
					case reply == "":
						return // 不回话，让客户端撞超时
					default:
						if _, err := conn.Write([]byte(reply)); err != nil {
							return
						}
					}
				}
			}(conn)
		}
	}()
	return ln.Addr().String()
}

// readRESPCommand 读一条 RESP 数组命令，返回命令名与其参数。
func readRESPCommand(r *bufio.Reader) (string, []string, error) {
	head, err := r.ReadString('\n')
	if err != nil {
		return "", nil, err
	}
	head = strings.TrimRight(head, "\r\n")
	if !strings.HasPrefix(head, "*") {
		return "", nil, fmt.Errorf("期望 RESP 数组，实得 %q", head)
	}
	n, err := strconv.Atoi(head[1:])
	if err != nil {
		return "", nil, err
	}
	args := make([]string, 0, n)
	for i := 0; i < n; i++ {
		line, err := r.ReadString('\n')
		if err != nil {
			return "", nil, err
		}
		line = strings.TrimRight(line, "\r\n")
		if !strings.HasPrefix(line, "$") {
			return "", nil, fmt.Errorf("期望批量字符串，实得 %q", line)
		}
		size, err := strconv.Atoi(line[1:])
		if err != nil {
			return "", nil, err
		}
		buf := make([]byte, size+2) // 值本身 + 结尾的 \r\n
		if _, err := io.ReadFull(r, buf); err != nil {
			return "", nil, err
		}
		args = append(args, string(buf[:size]))
	}
	if len(args) == 0 {
		return "", args, nil
	}
	return args[0], args[1:], nil
}

func probe(t *testing.T, rawURL string, timeout time.Duration) (bool, string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	return RedisCheck(rawURL).Probe(ctx)
}

// ── URL 解析 ──────────────────────────────────────────────────────────

func TestParseRedisURL(t *testing.T) {
	cases := []struct {
		name     string
		in       string
		wantAddr string
		wantUser string
		wantPass string
		wantErr  bool
	}{
		{"默认端口 6379", "redis://127.0.0.1:6379/0", "127.0.0.1:6379", "", "", false},
		{"省略端口", "redis://cache", "cache:6379", "", "", false},
		{"带口令", "redis://rp:secret@127.0.0.1:6379/0", "127.0.0.1:6379", "rp", "secret", false},
		{"只给用户名时按 ACL 默认用户", "redis://alice@127.0.0.1:6380", "127.0.0.1:6380", "alice", "", false},
		{"空值", "", "", "", "", true},
		{"协议不认识", "http://127.0.0.1:6379", "", "", "", true},
		{"没有主机名", "redis://", "", "", "", true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			addr, user, pass, err := parseRedisURL(tc.in)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("非法输入 %q 必须报错", tc.in)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if addr != tc.wantAddr || user != tc.wantUser || pass != tc.wantPass {
				t.Errorf("解析 %q = (%q,%q,%q)，期望 (%q,%q,%q)", tc.in, addr, user, pass, tc.wantAddr, tc.wantUser, tc.wantPass)
			}
		})
	}
}

// ── 探测行为 ──────────────────────────────────────────────────────────

func TestRedisCheckConnected(t *testing.T) {
	addr := fakeRedis(t, func(string) string { return "+PONG\r\n" }, nil)
	ok, detail := probe(t, "redis://"+addr, 2*time.Second)
	if !ok || detail != "connected" {
		t.Errorf("期望 (true, connected)，实得 (%v, %q)", ok, detail)
	}
}

func TestRedisCheckErrorReplyKeepsOnlyFirstToken(t *testing.T) {
	// 失败文案会进日志与 /ready 响应，所以不能把服务端整行原文带回去——
	// 那行里可能带着配置值，而 detail 是公开的。
	addr := fakeRedis(t, func(string) string { return "-NOAUTH Authentication required with password xxx\r\n" }, nil)
	ok, detail := probe(t, "redis://"+addr, 2*time.Second)
	if ok {
		t.Fatal("错误回复不得算成 connected")
	}
	if !strings.HasPrefix(detail, "disconnected: ") {
		t.Errorf("失败文案必须是 Python 那句 disconnected: 开头，实得 %q", detail)
	}
	if strings.Contains(detail, "Authentication") {
		t.Errorf("detail 不该带上整行原文：%q", detail)
	}
}

func TestRedisCheckUnexpectedFormIsError(t *testing.T) {
	// 对面回了个批量字符串——那不是 Redis 对 PING 的答法，宁可报 error 也别当成连通
	addr := fakeRedis(t, func(string) string { return "$5\r\nhello\r\n" }, nil)
	ok, detail := probe(t, "redis://"+addr, 2*time.Second)
	if ok || !strings.HasPrefix(detail, "disconnected: ") {
		t.Errorf("形态不对就该报 error，实得 (%v, %q)", ok, detail)
	}
}

func TestRedisCheckSendsAuthBeforePing(t *testing.T) {
	// 带口令的 Redis 上裸 PING 会被 -NOAUTH 打回，于是"Go 报 error / Python 报 ok"
	// 成了说不清的假分歧。这条证明 AUTH 确实先发、且顺序在 PING 之前。
	cmds := make(chan string, 8)
	addr := fakeRedis(t, func(cmd string) string {
		switch strings.ToUpper(cmd) {
		case "AUTH":
			return "+OK\r\n"
		default:
			return "+PONG\r\n"
		}
	}, cmds)

	if ok, detail := probe(t, "redis://rp:secret@"+addr, 2*time.Second); !ok {
		t.Fatalf("带口令的 URL 应该探通，实得 %q", detail)
	}

	var seen []string
	for done := false; !done; {
		select {
		case c := <-cmds:
			seen = append(seen, c)
			if c == "PING" {
				done = true
			}
		case <-time.After(2 * time.Second):
			done = true
		}
	}
	if len(seen) < 2 || seen[0] != "AUTH" || seen[1] != "PING" {
		t.Errorf("命令顺序应为 [AUTH, PING]，实得 %v", seen)
	}
}

func TestRedisCheckUnreachableIsNotACrash(t *testing.T) {
	// 先占一个端口再关掉，得到一个"立刻拒绝"的地址
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	addr := ln.Addr().String()
	_ = ln.Close()

	ok, detail := probe(t, "redis://"+addr, 2*time.Second)
	if ok || !strings.HasPrefix(detail, "disconnected: ") {
		t.Errorf("连不上必须如实报 error，实得 (%v, %q)", ok, detail)
	}
}

func TestRedisCheckHonoursContextDeadline(t *testing.T) {
	// 健康检查最要紧的一条：对面 accept 但不回话时探针必须按时撒手，
	// 否则 /ready 会被一个挂死的依赖拖成整站超时（Python 侧靠 READY_CHECK_TIMEOUT 拦这事）。
	addr := fakeRedis(t, func(string) string { return "" }, nil)

	start := time.Now()
	ok, detail := probe(t, "redis://"+addr, 300*time.Millisecond)
	elapsed := time.Since(start)

	if ok {
		t.Fatal("对面不回话却报 connected")
	}
	if elapsed > 2*time.Second {
		t.Errorf("超时没生效，耗了 %v", elapsed)
	}
	if !strings.HasPrefix(detail, "disconnected: ") {
		t.Errorf("detail 应当是 disconnected: 开头，实得 %q", detail)
	}
}

func TestRedisCheckBadURLIsErrorNotPanic(t *testing.T) {
	for _, bad := range []string{"", "redis://", "://x", "http://127.0.0.1:6379"} {
		ok, detail := probe(t, bad, 500*time.Millisecond)
		if ok || !strings.HasPrefix(detail, "disconnected: ") {
			t.Errorf("非法 REDIS_URL %q 应如实报 error，实得 (%v, %q)", bad, ok, detail)
		}
	}
}
