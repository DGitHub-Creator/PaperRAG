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
	// RedisURL 是 /ready 的 redis 探测目标。键名与默认值都跟 Python 共用同一份 `.env`
	// （backend/core/config 读的就是 REDIS_URL），两侧读出的必须指向同一个实例，
	// 否则"Go 说 redis ok、Python 说 error"这种分歧会一直说不清。
	// 为空时不拒绝启动：dev 形态下没 Redis 是常见状态，/ready 如实报 error 就是它的正确行为。
	RedisURL string
	// Version 进 /health 响应，与 Python 侧的 version 字段同位。
	Version string
	// ReadyTimeout 是单项依赖探测的超时上限，默认对齐 backend/api/health.py 的 3s。
	ReadyTimeout time.Duration
	// UpstreamURL 是尚未迁移到 Go 的路径的 Python 上游（14 §19 铁律 2「门面先于重写」）。
	// 默认 127.0.0.1:8000：dev 形态下 Go 是唯一入口，sessions/chat/documents/ws
	// 这些还没搬过来的面先转发给源码跑的 Python，搬一条就少转发一条。
	// 只在 go-api 有意义——go-worker 不面向浏览器。生产部署必须显式覆盖。
	UpstreamURL string

	// ── 认证面（P0-6）。默认值与 backend/core/config/auth.py 逐字同构：
	// 两侧读同一份 .env，同一个键在两个进程里必须得到同一个值，否则切换窗口内
	// Go 签的 token Python 验不过（或反过来）。

	// JWTSecretKey 是令牌签名密钥。**没有安全兜底值**：空密钥 python-jose 会静默接受，
	// 比可猜测的默认值更危险，所以缺失一律拒绝启动（见 ValidateAuth）。
	JWTSecretKey string
	// JWTAlgorithm 默认 HS256。Go 侧只接受这一个值：允许配置成别的等于打开算法混淆的口子。
	JWTAlgorithm string
	// JWTExpireMinutes 是 access token 有效期，默认 60。
	JWTExpireMinutes int
	// JWTRefreshExpireDays 是 refresh token 有效期，默认 30。
	JWTRefreshExpireDays int
	// AdminInviteCode 为空表示管理员注册通道关闭（与 resolve_role 的语义一致）。
	AdminInviteCode string
	// MinPasswordLength 默认 8；为 0 时关闭长度与字符类别两条校验（Python 同款开关）。
	MinPasswordLength int
	// PasswordPBKDF2Rounds 是新写入哈希的迭代数，默认 310000。验证时以哈希串里带的为准。
	PasswordPBKDF2Rounds int
}

// leakedInviteCodes 是已经公开过的默认邀请码。两个都要拒：旧项目名的弱默认值在既有部署里
// 可能已经写进 .env，只删旧值等于把"已经暴露过的口令"重新变成可用口令（AGENTS.md §7）。
var leakedInviteCodes = map[string]struct{}{
	"paperrag-admin-2026":      {},
	"researchpilot-admin-2026": {},
}

// jwtSecretPlaceholder 是 .env.example 里的占位值，照着抄就是等于没有密钥。
const jwtSecretPlaceholder = "replace-with-strong-random-secret"

// ValidateAuth 是认证面的 fail-fast，对齐 backend/core/config/__init__.py:validate_runtime_security。
// 分两档，与 Python 一致：
//   - JWT_SECRET_KEY 缺失在**所有**环境下都拒绝启动；
//   - 占位密钥与泄露过的邀请码只在生产环境拒绝启动，开发环境放行（Python 那边是告警）。
//
// 只有面向浏览器的 go-api 需要调用它：go-worker 不签发也不校验令牌。
func (c Config) ValidateAuth() error {
	if c.JWTSecretKey == "" {
		return fmt.Errorf("JWT_SECRET_KEY 未配置，拒绝启动。生成一个强随机值后重试: " +
			`python -c "import secrets; print(secrets.token_urlsafe(32))"`)
	}
	if !c.IsProduction() {
		return nil
	}
	if c.JWTSecretKey == jwtSecretPlaceholder {
		return fmt.Errorf("生产环境不安全配置：JWT_SECRET_KEY 仍是 .env.example 的占位值")
	}
	if _, ok := leakedInviteCodes[c.AdminInviteCode]; ok {
		return fmt.Errorf("生产环境不安全配置：ADMIN_INVITE_CODE 仍是已泄露的默认值")
	}
	return nil
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
		RedisURL:     envString("REDIS_URL", "redis://127.0.0.1:6379/0"),
		Version:      envString("VERSION", "dev"),
		ReadyTimeout: envDuration("READY_TIMEOUT", 3*time.Second),
		UpstreamURL:  envString("PYTHON_UPSTREAM", "http://127.0.0.1:8000"),

		JWTSecretKey:         os.Getenv("JWT_SECRET_KEY"),
		JWTAlgorithm:         envString("JWT_ALGORITHM", "HS256"),
		JWTExpireMinutes:     envInt("JWT_EXPIRE_MINUTES", 60),
		JWTRefreshExpireDays: envInt("JWT_REFRESH_EXPIRE_DAYS", 30),
		AdminInviteCode:      os.Getenv("ADMIN_INVITE_CODE"),
		MinPasswordLength:    envInt("MIN_PASSWORD_LENGTH", 8),
		PasswordPBKDF2Rounds: envInt("PASSWORD_PBKDF2_ROUNDS", 310000),
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

// envInt 读整型配置。非法值退回 fallback 而不是报错——fallback 一律取 Python 侧的默认值，
// 所以两个方向都安全：MIN_PASSWORD_LENGTH 退回 8（不是 0，不会静默关掉密码校验），
// PASSWORD_PBKDF2_ROUNDS 退回 310000（不会静默降低迭代数）。
// ⚠️ 与 Python 有一处已知分歧：`int(os.getenv(...))` 遇到非数字会抛 ValueError 拒绝启动，
// 这里选择退回默认值。分歧只在"值写错成非数字"时出现，且退回的是更严的那个默认值。
func envInt(key string, fallback int) int {
	raw := os.Getenv(key)
	if raw == "" {
		return fallback
	}
	n, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return n
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
