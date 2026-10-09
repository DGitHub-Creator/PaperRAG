package httpapi

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

// PostgresCheck 把连接池的 Ping 包成就绪探测。api 与 worker 共用同一个语义，
// 免得两边的 "database" 键各写一套判定（01 §2 第 2 条的键名在此对齐）。
func PostgresCheck(pool *pgxpool.Pool) Check {
	return Check{
		Name: "database",
		Probe: func(ctx context.Context) (bool, string) {
			if err := pool.Ping(ctx); err != nil {
				return false, fmt.Sprintf("disconnected: %v", err)
			}
			return true, "connected"
		},
	}
}

// NotConfiguredCheck 用于必需依赖没配的情况：进程照常起来，/ready 报 error。
// 比直接 panic 好——健康检查存在的意义就是把"哪里没就绪"说出来。
func NotConfiguredCheck(name, why string) Check {
	return Check{
		Name: name,
		Probe: func(context.Context) (bool, string) {
			return false, why
		},
	}
}
