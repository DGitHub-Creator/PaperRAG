// Command api 是 go-api：唯一面向浏览器的 HTTP/SSE/WS 入口（02 §2）。
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/auth"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/config"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/httpapi"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/observability"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/session"
)

func main() {
	cfg, err := config.Load("go-api", ":8080")
	if err != nil {
		slog.Error("config_invalid", "error", err)
		os.Exit(1)
	}
	// 认证面 fail-fast：JWT_SECRET_KEY 缺失时**拒绝启动**（所有环境）。
	// 空密钥 python-jose 是静默接受的，Go 若不拦就成了整条链路上最弱的一环。
	if err := cfg.ValidateAuth(); err != nil {
		slog.Error("auth_config_invalid", "error", err)
		os.Exit(1)
	}

	logger := observability.New(cfg.Service, !cfg.IsProduction())
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	pool, poolErr := newPool(ctx, cfg, logger)
	checks := databaseChecks(pool, poolErr, cfg)
	router := httpapi.NewRouter(httpapi.Deps{
		Logger:   logger,
		Version:  cfg.Version,
		Checks:   checks,
		Timeout:  cfg.ReadyTimeout,
		Upstream: upstreamProxy(cfg, logger),
	})
	authSvc := mountAuthRoutes(router, cfg, pool, poolErr, logger)
	mountSessionRoutes(router, authSvc, pool, poolErr, logger)
	logger.Info("upstream_configured", "url", cfg.UpstreamURL)

	server := &http.Server{
		Addr:              cfg.Addr,
		Handler:           router,
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

// mountAuthRoutes 挂认证与用户自助路由（P0-6 的三条 + 设置页的改密码/偏好）。
// 路径逐字取自 contracts/openapi.yaml。
//
// 挂在这里而不是 httpapi.NewRouter 里，是因为 auth 要用 httpapi 的信封写入器：
// 若 httpapi 反过来 import auth 就成了环（详见 httpapi.NewRouter 的注释）。
//
// 返回那个 *auth.Service 是给业务面复用身份解析的唯一途径——每条接管的路由都要先知道
// "这是谁"，而令牌校验只能有一份实现（各处各抄就会漂出不同的 401 语义，那是安全语义）。
func mountAuthRoutes(router *chi.Mux, cfg config.Config, pool *pgxpool.Pool, poolErr error, logger *slog.Logger) *auth.Service {
	svc := auth.NewService(
		userStore(pool, poolErr),
		auth.TokenConfig{
			Secret:            cfg.JWTSecretKey,
			ExpireMinutes:     cfg.JWTExpireMinutes,
			RefreshExpireDays: cfg.JWTRefreshExpireDays,
		},
		cfg.PasswordPBKDF2Rounds,
		cfg.AdminInviteCode,
		cfg.MinPasswordLength,
		logger,
	)
	// 偏好面单独注入：*db.Queries 同时满足 UserStore 与 PrefsStore，池不可用时给 nil，
	// 偏好路由随即回 500（而不是让 go-api 起不来——认证面本来就不依赖它）。
	if pool != nil {
		svc.Prefs = db.New(pool)
	}
	router.Post("/api/v1/auth/register", auth.RegisterHandler(svc))
	router.Post("/api/v1/auth/login", auth.LoginHandler(svc))
	router.Get("/api/v1/auth/me", auth.MeHandler(svc))
	router.Post("/api/v1/auth/password", auth.ChangePasswordHandler(svc))
	router.Get("/api/v1/me/preferences", auth.GetPreferencesHandler(svc))
	router.Put("/api/v1/me/preferences", auth.PutPreferencesHandler(svc))
	return svc
}

// mountSessionRoutes 挂会话面（P1-1 接管的第一条业务读接口：列表与删除）。
// 消息详情 `GET /sessions/{session_id}` 还没搬，见下方注释与台账 C34——
// 那条返回的 rag_trace 要过 Python 的 RagTrace 投影，不是"照着读一张表"能了事的。
//
// 显式路由优先于 NewRouter 里那条 `/api/*` 通配转发（chi 的 trie 按具体度匹配），
// 所以接管一条就少转发一条，不用动反代本身。
func mountSessionRoutes(router *chi.Mux, authSvc *auth.Service, pool *pgxpool.Pool, poolErr error, logger *slog.Logger) {
	svc := &session.Service{
		Auth:   authSvc,
		Store:  sessionStore(pool, poolErr),
		Logger: logger,
	}
	router.Get("/api/v1/sessions", session.ListHandler(svc))
	router.Delete("/api/v1/sessions/{session_id}", session.DeleteHandler(svc))
}

// sessionStore 与 userStore 同构：池不可用时给一个"一律报错"的实现，于是会话面回 500，
// 而不是因为路由没挂而回 404——后者会把人引向完全错误的排查方向。
func sessionStore(pool *pgxpool.Pool, poolErr error) session.Store {
	if pool == nil {
		return unavailableSessionStore{reason: fmt.Sprintf("数据库不可用: %v", poolErr)}
	}
	return db.New(pool)
}

type unavailableSessionStore struct{ reason string }

func (u unavailableSessionStore) ListSessionInfosForUser(context.Context, int32) ([]db.ListSessionInfosForUserRow, error) {
	return nil, errors.New(u.reason)
}

func (u unavailableSessionStore) DeleteSessionForUser(context.Context, db.DeleteSessionForUserParams) (int64, error) {
	return 0, errors.New(u.reason)
}

// upstreamProxy 建到 Python 上游的反向代理（14 §19 铁律 2）。地址非法或为空时返回 nil，
// 路由器随即退回"未命中给 JSON 404"——**不因为 Python 没起就拒绝启动 go-api**：
// 认证面本来就不依赖上游，让整条入口陪葬只会把一次配置写错升级成一次停机。
func upstreamProxy(cfg config.Config, logger *slog.Logger) http.Handler {
	if cfg.UpstreamURL == "" {
		return nil
	}
	u, err := url.Parse(cfg.UpstreamURL)
	if err != nil || u.Host == "" {
		logger.Warn("upstream_url_invalid", "url", cfg.UpstreamURL, "error", err)
		return nil
	}
	return httpapi.NewUpstreamProxy(u, logger)
}

// newPool 建连接池。失败不退出进程：/ready 会如实报 database 不可用（与 Python 侧
// 探针语义一致），开发环境没有库时 go-api 仍能起来看健康检查。
func newPool(ctx context.Context, cfg config.Config, logger *slog.Logger) (*pgxpool.Pool, error) {
	if cfg.DatabaseURL == "" {
		logger.Warn("database_url_missing", "hint", "/ready 会报 database 不可用，认证接口会回 500")
		return nil, errors.New("DATABASE_URL 未配置")
	}
	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		logger.Error("postgres_pool_init_failed", "error", err)
		return nil, err
	}
	return pool, nil
}

// userStore 返回认证切片用的 users 访问面。连接池不可用时给一个"一律报错"的实现，
// 于是认证接口回 500（与生产侧"库连不上 → unhandled_error_handler 回 500"同形状），
// 而不是 404——404 会让人以为路由没挂，那是完全不同的排查方向。
func userStore(pool *pgxpool.Pool, poolErr error) auth.UserStore {
	if pool == nil {
		return unavailableStore{reason: fmt.Sprintf("数据库不可用: %v", poolErr)}
	}
	return db.New(pool)
}

type unavailableStore struct{ reason string }

func (u unavailableStore) GetUserByUsername(context.Context, string) (db.User, error) {
	return db.User{}, errors.New(u.reason)
}

func (u unavailableStore) GetProfileByUsername(context.Context, string) (db.GetProfileByUsernameRow, error) {
	return db.GetProfileByUsernameRow{}, errors.New(u.reason)
}

func (u unavailableStore) InsertUser(context.Context, db.InsertUserParams) (db.InsertUserRow, error) {
	return db.InsertUserRow{}, errors.New(u.reason)
}

func (u unavailableStore) UpdateUserPasswordByUsername(context.Context, db.UpdateUserPasswordByUsernameParams) (db.UpdateUserPasswordByUsernameRow, error) {
	return db.UpdateUserPasswordByUsernameRow{}, errors.New(u.reason)
}

func databaseChecks(pool *pgxpool.Pool, poolErr error, cfg config.Config) []httpapi.Check {
	checks := []httpapi.Check{}
	if pool == nil {
		checks = append(checks, httpapi.NotConfiguredCheck("database", poolErr.Error()))
	} else {
		checks = append(checks, httpapi.PostgresCheck(pool))
	}
	// redis 这一格不是顺手加的：X1 的 expect 点名「/ready 的 PG/Redis 依赖探活通过」，
	// 而 Go 从前只注册 database——于是那一半**无物可判**，一个只会回答 database 的探针
	// 看着像全绿。同一条毛病在 C33（Go 没限流层）上是同一个形状：接管一条面就顺手丢掉
	// 原面上的一项能力，而且没有任何门禁会因此变红。
	checks = append(checks, httpapi.RedisCheck(cfg.RedisURL))
	return checks
}

func checkNames(checks []httpapi.Check) []string {
	names := make([]string, len(checks))
	for i, c := range checks {
		names[i] = c.Name
	}
	return names
}
