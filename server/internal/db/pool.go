// Package db 是 Go 侧的数据访问层。
//
// 分层是硬性的：`*.sql.go` 与 `models.go` 由 sqlc 生成、入库、禁止手改（决策 K2）；
// 本文件是唯一手写的部分，只管连接与事务入口。业务 SQL 一律写在 `server/sql/queries/`，
// 不在 Go 里拼字符串——能被机检的东西不要靠约定（08 原则③）。
package db

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// PoolOptions 是连接池的可调项。零值走默认，由 withDefaults 补齐——
// 不在调用点写 magic number，compose 里那几个环境变量才是唯一来源。
//
// 这里**故意没有** "query timeout" 这类字段：本层不做每查询超时，超时由调用方
// 传入的 context 控制。留一个没人执行的旋钮，比不留更糟（01 §4 记录过的那种
// "配置项只进日志不进行为"的坑）。
type PoolOptions struct {
	MaxConns        int32
	MinConns        int32
	ConnectTimeout  time.Duration
	HealthCheckPing time.Duration
}

func (o *PoolOptions) withDefaults() {
	if o.MaxConns <= 0 {
		o.MaxConns = 8
	}
	if o.MinConns <= 0 {
		o.MinConns = 1
	}
	if o.ConnectTimeout <= 0 {
		o.ConnectTimeout = 5 * time.Second
	}
	if o.HealthCheckPing <= 0 {
		o.HealthCheckPing = 3 * time.Second
	}
}

// NewPool 建连接池并做一次 Ping 确认连通。
//
// Ping 是故意的：pgxpool.New 是惰性的，连接串写错也要到第一个业务请求才炸，
// 那时报错已经和真正的原因（配置）隔了一层。启动时就失败更便宜。
func NewPool(ctx context.Context, databaseURL string, opts PoolOptions) (*pgxpool.Pool, error) {
	if databaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL 为空，不建连接池")
	}
	opts.withDefaults()

	cfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("解析 DATABASE_URL 失败: %w", err)
	}
	cfg.MaxConns = opts.MaxConns
	cfg.MinConns = opts.MinConns
	cfg.ConnConfig.ConnectTimeout = opts.ConnectTimeout
	// 空闲连接被 PG 或中间层悄悄掐断时，取用前先探一次，别让业务请求当探针
	cfg.HealthCheckPeriod = opts.HealthCheckPing

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("创建连接池失败: %w", err)
	}

	pingCtx, cancel := context.WithTimeout(ctx, opts.ConnectTimeout)
	defer cancel()
	if err := pool.Ping(pingCtx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("连接数据库失败: %w", err)
	}
	return pool, nil
}
