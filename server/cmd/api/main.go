// Command api 是 go-api：唯一面向浏览器的 HTTP/SSE/WS 入口（02 §2）。
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

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/DGitHub-Creator/PaperRAG/server/internal/config"
	"github.com/DGitHub-Creator/PaperRAG/server/internal/httpapi"
	"github.com/DGitHub-Creator/PaperRAG/server/internal/observability"
)

func main() {
	cfg, err := config.Load("go-api", ":8080")
	if err != nil {
		slog.Error("config_invalid", "error", err)
		os.Exit(1)
	}
	logger := observability.New(cfg.Service, !cfg.IsProduction())
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	checks := databaseChecks(ctx, cfg, logger)
	server := &http.Server{
		Addr:              cfg.Addr,
		Handler:           httpapi.NewRouter(httpapi.Deps{Logger: logger, Version: cfg.Version, Checks: checks, Timeout: cfg.ReadyTimeout}),
		ReadHeaderTimeout: 10 * time.Second,
	}

	shutdownDone := make(chan struct{})
	go func() {
		defer close(shutdownDone)
		<-ctx.Done()
		// 给在途请求 10s 收尾；超时直接退出，不给卡死的下游陪葬
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			logger.Error("shutdown_failed", "error", err)
		}
	}()

	logger.Info("listening", "addr", cfg.Addr, "env", cfg.Env, "checks", checkNames(checks))
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		logger.Error("serve_failed", "error", err)
		os.Exit(1)
	}
	<-shutdownDone
	logger.Info("shutdown_complete")
}

func databaseChecks(ctx context.Context, cfg config.Config, logger *slog.Logger) []httpapi.Check {
	if cfg.DatabaseURL == "" {
		logger.Warn("database_url_missing", "hint", "/ready 会报 database 不可用")
		return []httpapi.Check{httpapi.NotConfiguredCheck("database", "DATABASE_URL 未配置")}
	}
	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		logger.Error("postgres_pool_init_failed", "error", err)
		return []httpapi.Check{httpapi.NotConfiguredCheck("database", "连接池创建失败")}
	}
	return []httpapi.Check{httpapi.PostgresCheck(pool)}
}

func checkNames(checks []httpapi.Check) []string {
	names := make([]string, len(checks))
	for i, c := range checks {
		names[i] = c.Name
	}
	return names
}
