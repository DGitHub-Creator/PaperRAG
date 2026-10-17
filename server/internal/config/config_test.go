package config

import (
	"testing"
	"time"
)

func TestLoadDefaults(t *testing.T) {
	t.Setenv("APP_ENV", "")
	t.Setenv("PORT", "")
	t.Setenv("DATABASE_URL", "")
	t.Setenv("READY_TIMEOUT", "")

	cfg, err := Load("go-api", ":8080")
	if err != nil {
		t.Fatalf("开发环境缺 DATABASE_URL 不该报错（由 /ready 报未就绪）: %v", err)
	}
	if cfg.Env != "development" || cfg.Addr != ":8080" || cfg.Version != "dev" {
		t.Fatalf("默认值不对: %+v", cfg)
	}
	if cfg.ReadyTimeout != 3*time.Second {
		t.Fatalf("READY_TIMEOUT 默认应对齐 backend/api/health.py 的 3s，得到 %s", cfg.ReadyTimeout)
	}
	if cfg.IsProduction() {
		t.Error("默认不该是生产环境")
	}
}

func TestPortOverride(t *testing.T) {
	t.Setenv("PORT", "9090")
	cfg, err := Load("go-api", ":8080")
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Addr != ":9090" {
		t.Fatalf("PORT 应覆盖默认地址，得到 %s", cfg.Addr)
	}
}

// 与 A0-3 的 JWT 密钥 fail-fast 同一条律：生产环境必需配置缺失就拒绝启动，不带着空配置上线。
func TestProductionRequiresDatabaseURL(t *testing.T) {
	t.Setenv("APP_ENV", "production")
	t.Setenv("DATABASE_URL", "")
	if _, err := Load("go-api", ":8080"); err == nil {
		t.Fatal("生产环境缺 DATABASE_URL 应拒绝启动")
	}

	t.Setenv("DATABASE_URL", "postgres://user:pass@postgres:5432/langchain_app")
	cfg, err := Load("go-api", ":8080")
	if err != nil {
		t.Fatalf("配齐后应通过: %v", err)
	}
	if !cfg.IsProduction() {
		t.Error("APP_ENV=production 应识别为生产")
	}
}

func TestReadyTimeoutAcceptsSecondsAndDuration(t *testing.T) {
	for raw, want := range map[string]time.Duration{"5": 5 * time.Second, "5s": 5 * time.Second, "2500ms": 2500 * time.Millisecond} {
		t.Setenv("READY_TIMEOUT", raw)
		cfg, err := Load("go-api", ":8080")
		if err != nil {
			t.Fatal(err)
		}
		if cfg.ReadyTimeout != want {
			t.Errorf("READY_TIMEOUT=%q 期望 %s，得到 %s", raw, want, cfg.ReadyTimeout)
		}
	}
	t.Setenv("READY_TIMEOUT", "not-a-number")
	cfg, _ := Load("go-api", ":8080")
	if cfg.ReadyTimeout != 3*time.Second {
		t.Errorf("非法值应退回默认 3s，得到 %s", cfg.ReadyTimeout)
	}
}

// ── 认证面配置（P0-6）─────────────────────────────────────────────────

// clearAuthEnv 把认证相关的键全部清空，避免读到本机 .env / shell 里遗留的值。
func clearAuthEnv(t *testing.T) {
	t.Helper()
	for _, key := range []string{
		"JWT_SECRET_KEY", "JWT_ALGORITHM", "JWT_EXPIRE_MINUTES", "JWT_REFRESH_EXPIRE_DAYS",
		"ADMIN_INVITE_CODE", "MIN_PASSWORD_LENGTH", "PASSWORD_PBKDF2_ROUNDS",
	} {
		t.Setenv(key, "")
	}
}

// 默认值必须与 backend/core/config/auth.py 逐字同构：两侧读同一份 .env，
// 同一个键在两个进程里得到不同的值，就意味着 Go 签的令牌 Python 验不过（或反过来）。
func TestLoadAuthDefaultsMatchPython(t *testing.T) {
	clearAuthEnv(t)
	t.Setenv("APP_ENV", "")

	cfg, err := Load("go-api", ":8080")
	if err != nil {
		t.Fatalf("开发环境缺认证配置不该在 Load 阶段报错（fail-fast 在 ValidateAuth）: %v", err)
	}
	if cfg.JWTSecretKey != "" {
		t.Errorf("JWT_SECRET_KEY 没有安全兜底值，应为空，实得 %q", cfg.JWTSecretKey)
	}
	if cfg.JWTAlgorithm != "HS256" {
		t.Errorf("JWT_ALGORITHM 默认应是 HS256，实得 %q", cfg.JWTAlgorithm)
	}
	if cfg.JWTExpireMinutes != 60 {
		t.Errorf("JWT_EXPIRE_MINUTES 默认应是 60，实得 %d", cfg.JWTExpireMinutes)
	}
	if cfg.JWTRefreshExpireDays != 30 {
		t.Errorf("JWT_REFRESH_EXPIRE_DAYS 默认应是 30，实得 %d", cfg.JWTRefreshExpireDays)
	}
	if cfg.MinPasswordLength != 8 {
		t.Errorf("MIN_PASSWORD_LENGTH 默认应是 8，实得 %d", cfg.MinPasswordLength)
	}
	if cfg.PasswordPBKDF2Rounds != 310000 {
		t.Errorf("PASSWORD_PBKDF2_ROUNDS 默认应是 310000（生产真实迭代数），实得 %d", cfg.PasswordPBKDF2Rounds)
	}
	if cfg.AdminInviteCode != "" {
		t.Errorf("ADMIN_INVITE_CODE 默认应为空（管理员注册通道关闭），实得 %q", cfg.AdminInviteCode)
	}
}

func TestLoadAuthOverrides(t *testing.T) {
	clearAuthEnv(t)
	t.Setenv("JWT_SECRET_KEY", "a-real-secret")
	t.Setenv("JWT_ALGORITHM", "HS512")
	t.Setenv("JWT_EXPIRE_MINUTES", "15")
	t.Setenv("JWT_REFRESH_EXPIRE_DAYS", "7")
	t.Setenv("ADMIN_INVITE_CODE", "correct-horse")
	t.Setenv("MIN_PASSWORD_LENGTH", "12")
	t.Setenv("PASSWORD_PBKDF2_ROUNDS", "600000")

	cfg, err := Load("go-api", ":8080")
	if err != nil {
		t.Fatal(err)
	}
	if cfg.JWTSecretKey != "a-real-secret" || cfg.JWTAlgorithm != "HS512" ||
		cfg.JWTExpireMinutes != 15 || cfg.JWTRefreshExpireDays != 7 ||
		cfg.AdminInviteCode != "correct-horse" || cfg.MinPasswordLength != 12 ||
		cfg.PasswordPBKDF2Rounds != 600000 {
		t.Errorf("环境变量没被读进来: %+v", cfg)
	}
}

// 非法整数值退回 Python 侧的默认值而不是报错。两个方向都安全：
// MIN_PASSWORD_LENGTH 退回 8（不是 0，不会静默关掉密码校验），
// PASSWORD_PBKDF2_ROUNDS 退回 310000（不会静默降低迭代数）。
func TestLoadAuthInvalidIntsFallBackToSafeDefaults(t *testing.T) {
	clearAuthEnv(t)
	t.Setenv("MIN_PASSWORD_LENGTH", "abc")
	t.Setenv("PASSWORD_PBKDF2_ROUNDS", "")
	t.Setenv("JWT_EXPIRE_MINUTES", "12.5")

	cfg, err := Load("go-api", ":8080")
	if err != nil {
		t.Fatal(err)
	}
	if cfg.MinPasswordLength != 8 {
		t.Errorf("非法值应退回 8（不是 0），实得 %d", cfg.MinPasswordLength)
	}
	if cfg.PasswordPBKDF2Rounds != 310000 {
		t.Errorf("应退回 310000，实得 %d", cfg.PasswordPBKDF2Rounds)
	}
	if cfg.JWTExpireMinutes != 60 {
		t.Errorf("非整数应退回 60，实得 %d", cfg.JWTExpireMinutes)
	}
}

// JWT_SECRET_KEY 缺失在**所有**环境下都拒绝启动，对齐
// backend/core/config/__init__.py:validate_runtime_security：
// 缺失签名密钥没有安全兜底，所以没有开发环境豁免。
func TestValidateAuthRequiresSecretInEveryEnvironment(t *testing.T) {
	for _, env := range []string{"development", "production"} {
		t.Run(env, func(t *testing.T) {
			cfg := Config{Env: env, JWTSecretKey: ""}
			if err := cfg.ValidateAuth(); err == nil {
				t.Errorf("%s 下缺 JWT_SECRET_KEY 应拒绝启动", env)
			}
		})
	}
}

// 占位密钥与泄露过的邀请码：生产拒绝启动，开发放行（生产侧那边是告警）。
// 两个泄露值都要拒——旧项目名的弱默认值可能已经写进既有部署的 .env，
// 只删旧值等于把"已经暴露过的口令"重新变成可用口令（AGENTS.md §7）。
func TestValidateAuthRejectsUnsafeValuesOnlyInProduction(t *testing.T) {
	unsafe := []struct {
		name string
		cfg  Config
	}{
		{"占位密钥", Config{JWTSecretKey: "replace-with-strong-random-secret"}},
		{"生产模板密钥", Config{JWTSecretKey: "replace-with-a-long-random-production-secret"}},
		{"生产模板邀请码", Config{JWTSecretKey: "s", AdminInviteCode: "replace-with-a-private-admin-invite-code"}},
		{"旧项目名的泄露邀请码", Config{JWTSecretKey: "s", AdminInviteCode: "paperrag-admin-2026"}},
		{"新项目名的泄露邀请码", Config{JWTSecretKey: "s", AdminInviteCode: "researchpilot-admin-2026"}},
	}
	for _, c := range unsafe {
		t.Run(c.name+"/production", func(t *testing.T) {
			cfg := c.cfg
			cfg.Env = "production"
			if err := cfg.ValidateAuth(); err == nil {
				t.Error("生产环境应拒绝启动")
			}
		})
		t.Run(c.name+"/development", func(t *testing.T) {
			cfg := c.cfg
			cfg.Env = "development"
			if err := cfg.ValidateAuth(); err != nil {
				t.Errorf("开发环境应放行（生产侧那边是告警而不是拒绝）: %v", err)
			}
		})
	}
}

func TestValidateAuthAcceptsSafeProductionConfig(t *testing.T) {
	cfg := Config{Env: "production", JWTSecretKey: "a-strong-random-secret", AdminInviteCode: "correct-horse"}
	if err := cfg.ValidateAuth(); err != nil {
		t.Errorf("配齐后应通过: %v", err)
	}
	// 邀请码为空在生产环境是允许的：那表示管理员注册通道关闭，不是不安全
	cfg = Config{Env: "production", JWTSecretKey: "a-strong-random-secret"}
	if err := cfg.ValidateAuth(); err != nil {
		t.Errorf("未配置邀请码（通道关闭）不该拒绝启动: %v", err)
	}
}
