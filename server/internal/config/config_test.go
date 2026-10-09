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
