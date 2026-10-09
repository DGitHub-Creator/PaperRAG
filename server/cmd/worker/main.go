// Command worker 是 go-worker 进程。P0 只提供健康检查与待命循环：
// Frontier 队列、goroutine pool 与 fencing 属 P3（02 §1），在这里落地前先不假装能调度。
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/DGitHub-Creator/PaperRAG/server/internal/config"
	"github.com/DGitHub-Creator/PaperRAG/server/internal/httpapi"
	"github.com/DGitHub-Creator/PaperRAG/server/internal/observability"
)

func main() {
	// 只绑回环：go-worker 不面向浏览器，容器间也不该被外部打到（02 §2）。
	cfg, err := config.Load("go-worker", "127.0.0.1:8081")
	if err != nil {
		slog.Error("config_invalid", "error", err)
		os.Exit(1)
	}
	logger := observability.New(cfg.Service, !cfg.IsProduction())
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	deps := httpapi.Deps{Logger: logger, Version: cfg.Version, Checks: databaseChecks(ctx, cfg, logger), Timeout: cfg.ReadyTimeout}
	r := chi.NewRouter()
	r.Use(httpapi.Trace, httpapi.RequestLogger(logger), httpapi.Recover(logger))
	r.Get("/health", httpapi.HealthHandler(deps))
	r.Get("/ready", httpapi.ReadyHandler(deps))

	server := &http.Server{Addr: cfg.Addr, Handler: r, ReadHeaderTimeout: 10 * time.Second}
	shutdownDone := make(chan struct{})
	go func() {
		defer close(shutdownDone)
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			logger.Error("shutdown_failed", "error", err)
		}
	}()

	logger.Info("worker_idle", "addr", cfg.Addr, "env", cfg.Env, "reason", "调度器属 P3，本进程当前只提供探针")
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		logger.Error("serve_failed", "error", err)
		os.Exit(1)
	}
	<-shutdownDone
	logger.Info("shutdown_complete")
}

func databaseChecks(ctx context.Context, cfg config.Config, logger *slog.Logger) []httpapi.Check {
	if cfg.DatabaseURL == "" {
		return []httpapi.Check{httpapi.NotConfiguredCheck("database", "DATABASE_URL 未配置")}
	}
	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		logger.Error("postgres_pool_init_failed", "error", err)
		return []httpapi.Check{httpapi.NotConfiguredCheck("database", "连接池创建失败")}
	}
	return []httpapi.Check{httpapi.PostgresCheck(pool)}
}
