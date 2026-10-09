// Package config 读取 Go 侧进程的环境配置。
//
// 规则与 Python 侧一致：只在进程入口读一次环境变量，其余包接收结构体，
// 不在业务代码里散落 os.Getenv（backend/core/config 同构）。
package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

// Config 是单个进程的运行时配置。
type Config struct {
	// Service 是进程名，进 slog 的固定字段，用于在 compose 日志里区分 go-api / go-worker。
	Service string
	// Env 取自 APP_ENV，development（默认）或 production。与 Python 共用同一个键。
	Env string
	// Addr 是 HTTP 监听地址。对外只有 go-api 经 nginx，go-worker 只监听回环。
	Addr string
	// DatabaseURL 是 PostgreSQL 连接串。为空时 go-api 仍能起，/ready 会报 database 不可用；
	// production 下直接拒绝启动（与 A0-3 的 JWT 密钥 fail-fast 同一条律）。
	DatabaseURL string
	// Version 进 /health 响应，与 Python 侧的 version 字段同位。
	Version string
	// ReadyTimeout 是单项依赖探测的超时上限，默认对齐 backend/api/health.py 的 3s。
	ReadyTimeout time.Duration
}

// IsProduction 判断是否生产环境，语义与 backend.core.config.is_production 一致（prod|production）。
func (c Config) IsProduction() bool {
	return c.Env == "prod" || c.Env == "production"
}

// Load 读取配置并给默认值；只在 production 且必需项缺失时报错。
func Load(service, defaultAddr string) (Config, error) {
	cfg := Config{
		Service:      service,
		Env:          envString("APP_ENV", "development"),
		Addr:         defaultAddr,
		DatabaseURL:  os.Getenv("DATABASE_URL"),
		Version:      envString("VERSION", "dev"),
		ReadyTimeout: envDuration("READY_TIMEOUT", 3*time.Second),
	}
	if port := os.Getenv("PORT"); port != "" {
		cfg.Addr = ":" + port
	}
	if cfg.IsProduction() && cfg.DatabaseURL == "" {
		return cfg, fmt.Errorf("生产环境必须提供 DATABASE_URL，拒绝启动")
	}
	return cfg, nil
}

func envString(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envDuration(key string, fallback time.Duration) time.Duration {
	raw := os.Getenv(key)
	if raw == "" {
		return fallback
	}
	// 同时接受 "3"（秒）与 "3s"：compose 里写纯数字更顺手
	if secs, err := strconv.Atoi(raw); err == nil {
		return time.Duration(secs) * time.Second
	}
	d, err := time.ParseDuration(raw)
	if err != nil {
		return fallback
	}
	return d
}
