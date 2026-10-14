package httpapi

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/url"
	"strings"
	"time"
)

// probeFallbackTimeout 只在调用方没给 ctx 死线时兜底（/ready 走的是 ReadyTimeout，
// 单测直调 Probe 时才会落到这里）。值与 router.go 里那个同名的兜底一致。
const probeFallbackTimeout = 3 * time.Second

// RedisCheck 探一次 Redis：连上、发一条命令、读回一行。
//
// **为什么不引 go-redis**：这个探针需要的只是"能不能按 RESP 说上一句话"，
// 为一个健康检查加一个客户端依赖，换来的是版本漂移与多一条供应链——不值。
// 手写的好处还有一层：探测路径上没有连接池、没有重试、没有后台 goroutine，
// 它不会因为 /ready 被反复打而拖住进程。
//
// 语义与 Python 的 `_check_redis` 逐字对齐（`backend/api/health.py:54`）：
// 成功是 `connected`，失败是 `disconnected: <原因>`，探测键名是 `redis`。
// 键名与文案不是小事——compose 的 healthcheck、监控看板与前端都按这些字符串读。
func RedisCheck(rawURL string) Check {
	return Check{
		Name: "redis",
		Probe: func(ctx context.Context) (bool, string) {
			addr, user, pass, err := parseRedisURL(rawURL)
			if err != nil {
				return false, "disconnected: " + err.Error()
			}
			d := net.Dialer{}
			conn, err := d.DialContext(ctx, "tcp", addr)
			if err != nil {
				return false, "disconnected: " + err.Error()
			}
			defer conn.Close()
			if dl, ok := ctx.Deadline(); ok {
				// 单条命令的超时由 /ready 的那个 ctx 决定，这里不自造第二套时限
				_ = conn.SetDeadline(dl)
			} else {
				_ = conn.SetDeadline(time.Now().Add(probeFallbackTimeout))
			}

			// 带口令的 Redis 上，裸 PING 会被 -NOAUTH 打回，于是"Go 报 error / Python 报 ok"
			// 成了假分歧；所以 URL 里有 userinfo 就先 AUTH。
			if pass != "" {
				if err := roundTrip(conn, "AUTH", user, pass); err != nil {
					return false, "disconnected: " + err.Error()
				}
			}
			if err := roundTrip(conn, "PING"); err != nil {
				return false, "disconnected: " + err.Error()
			}
			return true, "connected"
		},
	}
}

// parseRedisURL 支持 redis:// / rediss:// 与 redis://user:pass@host:port/db 几种写法。
// 返回的 user 在没有用户名时按 Redis 6 的 ACL 默认用户 `default` 处理。
func parseRedisURL(rawURL string) (addr, user, pass string, err error) {
	if rawURL == "" {
		return "", "", "", fmt.Errorf("REDIS_URL 未配置")
	}
	u, err := url.Parse(rawURL)
	if err != nil {
		return "", "", "", fmt.Errorf("REDIS_URL 解析失败: %w", err)
	}
	switch u.Scheme {
	case "redis", "rediss":
	default:
		return "", "", "", fmt.Errorf("REDIS_URL 协议不认识: %q", u.Scheme)
	}
	host := u.Hostname()
	if host == "" {
		return "", "", "", fmt.Errorf("REDIS_URL 没有主机名: %q", rawURL)
	}
	port := u.Port()
	if port == "" {
		port = "6379"
	}
	if u.User != nil {
		user = u.User.Username()
		if user == "" {
			user = "default"
		}
		// 口令可能本身就是空串（只有用户名的写法），Passphrase 的第二返回值分得开这两种
		pass, _ = u.User.Password()
	}
	return net.JoinHostPort(host, port), user, pass, nil
}

// roundTrip 按 RESP 数组编码发一条命令，并确认回复不是错误。
// 用数组编码而不是 `AUTH user pass` 那种内联写法，是因为口令里出现空格或 CRLF
// 会把内联协议切成两条命令——编码版没有这个问题。
func roundTrip(conn net.Conn, args ...string) error {
	var b strings.Builder
	b.WriteString("*")
	b.WriteString(fmt.Sprint(len(args)))
	b.WriteString("\r\n")
	for _, a := range args {
		b.WriteString("$")
		b.WriteString(fmt.Sprint(len(a)))
		b.WriteString("\r\n")
		b.WriteString(a)
		b.WriteString("\r\n")
	}
	if _, err := conn.Write([]byte(b.String())); err != nil {
		return fmt.Errorf("发送失败: %w", err)
	}

	buf := make([]byte, 256)
	n, err := conn.Read(buf)
	if err != nil && !(err == io.EOF && n > 0) {
		return fmt.Errorf("读取失败: %w", err)
	}
	line := string(buf[:n])
	switch {
	case strings.HasPrefix(line, "-"):
		// 只带回首条单词：整行原文可能包含配置值，探针的失败文案是会进日志与响应的
		return fmt.Errorf("Redis 拒绝: %s", firstToken(strings.TrimPrefix(line, "-")))
	case strings.HasPrefix(line, "+"):
		return nil
	default:
		// PING 的 +PONG 与批量结果之外的形态，说明对面不是（或不只是）一个 Redis
		return fmt.Errorf("意外的响应形态: %q", firstToken(line))
	}
}

func firstToken(s string) string {
	s = strings.TrimSpace(s)
	if i := strings.IndexAny(s, " \r\n"); i >= 0 {
		return s[:i]
	}
	if len(s) > 80 {
		return s[:80]
	}
	return s
}
