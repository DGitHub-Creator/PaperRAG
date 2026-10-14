// Command seed 幂等地保证一个管理员账号存在。
//
// 它不是一个 HTTP 接口——注册接口造 admin 需要 ADMIN_INVITE_CODE，而"我自己的机器上得有个
// 能进后台的账号"这件事不该被邀请码流程卡住。所以走进程内直连：复用与注册完全相同的
// 哈希实现（auth.HashPassword）与同一张 users 表，只是绕过了"谁来提交邀请码"这一问。
//
// 幂等规则：不存在就建；存在就把角色摆正；**默认不覆盖口令**，要重置必须显式给
// ADMIN_RESET_PASSWORD=1——否则这个命令会变成"跑一次就把现网管理员的口令换成 .env 里那个"的
// 脚枪。所有口令都只从环境变量来，不进命令行参数（命令行会留在 shell 历史与 ps 输出里）。
package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/auth"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/config"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "seed 失败: "+err.Error())
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.Load("seed", "127.0.0.1:0")
	if err != nil {
		return err
	}
	if cfg.DatabaseURL == "" {
		return errors.New("DATABASE_URL 未配置（seed 需要直连 PostgreSQL）")
	}

	username := envOr("ADMIN_USERNAME", "admin")
	role := envOr("ADMIN_ROLE", "admin")
	password := os.Getenv("ADMIN_PASSWORD")
	resetPassword := os.Getenv("ADMIN_RESET_PASSWORD") == "1"

	if username == "" {
		return errors.New("ADMIN_USERNAME 不能为空")
	}
	if password == "" {
		return errors.New("ADMIN_PASSWORD 未配置：拒绝创建一个没有口令的管理员账号")
	}
	if cfg.MinPasswordLength > 0 && utf8.RuneCountInString(password) < cfg.MinPasswordLength {
		return fmt.Errorf("ADMIN_PASSWORD 不足 %d 个字符", cfg.MinPasswordLength)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		return fmt.Errorf("连不上数据库: %w", err)
	}

	queries := db.New(pool)
	existing, err := queries.GetUserByUsername(ctx, username)

	if errors.Is(err, pgx.ErrNoRows) {
		hash, herr := auth.HashPassword(password, cfg.PasswordPBKDF2Rounds)
		if herr != nil {
			return herr
		}
		// created_at 显式给 UTC：与 auth.Service.Register 同一处理由（05 §4 的时间列语义）。
		row, ierr := queries.InsertUser(ctx, db.InsertUserParams{
			Username:     username,
			PasswordHash: hash,
			Role:         role,
			CreatedAt:    pgtype.Timestamp{Time: time.Now().UTC(), Valid: true},
		})
		if ierr != nil {
			return fmt.Errorf("创建账号失败: %w", ierr)
		}
		fmt.Printf("已创建账号：username=%s role=%s\n", row.Username, row.Role)
		return nil
	}
	if err != nil {
		return fmt.Errorf("查询用户失败: %w", err)
	}

	if existing.Role != role {
		row, uerr := queries.UpdateUserRoleByUsername(ctx, db.UpdateUserRoleByUsernameParams{
			Username: username,
			Role:     role,
		})
		if uerr != nil {
			return fmt.Errorf("更新角色失败: %w", uerr)
		}
		fmt.Printf("已更新角色：username=%s %s -> %s\n", row.Username, existing.Role, row.Role)
	} else {
		fmt.Printf("账号已存在且角色正确：username=%s role=%s\n", existing.Username, existing.Role)
	}

	if !resetPassword {
		fmt.Println("口令未改动（要重置请设 ADMIN_RESET_PASSWORD=1）")
		return nil
	}
	hash, herr := auth.HashPassword(password, cfg.PasswordPBKDF2Rounds)
	if herr != nil {
		return herr
	}
	if _, perr := queries.UpdateUserPasswordByUsername(ctx, db.UpdateUserPasswordByUsernameParams{
		Username:     username,
		PasswordHash: hash,
	}); perr != nil {
		return fmt.Errorf("重置口令失败: %w", perr)
	}
	fmt.Println("已按 ADMIN_RESET_PASSWORD=1 重置口令")
	return nil
}

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
