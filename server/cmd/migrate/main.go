// Command migrate 把 Go 侧的 schema 迁移应用到库上（`server/migrations/`）。
//
// 它存在的理由是台账 C18 / 决策 D8：**那三份 `.up.sql` 从前只有读者、没有执行器**
// （离线读者只有 `audit_schema.py` 与 sqlc），于是 X6 的「`schema_migrations` 版本与设计一致」
// 这一问今天无机检，`000002_ai_executions` 也从没在任何长期库上落过。
//
// D8 定案（2026-10-15）：**迁移是显式运维动作，不进任何服务的启动路径**。
// 两个理由，都写在 `08 §2` 的原则上：
//   - go-api 将来是多副本，启动内自动迁移会让多个进程同时抢同一批 DDL；
//   - 接进启动路径等于给公开入口进程加上 DDL 权限，而它日常只需要读写自己那三张表。
//
// 所以这里是一个**手动命令**（`dev.py migrate-go`），而不是 go-api 的启动步骤。
// 也因此它绝不碰 alembic 那条线：alembic 的版本表是 `alembic_version`，这里是
// `schema_migrations`，两张表互不知晓——同一份 DDL 由谁先落地决定了另一条会不会以
// "对象已存在"失败，本仓库的迁移一律带 `IF NOT EXISTS` 正是为了这个共存局面（§3 基线非破坏）。
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/postgres"
	_ "github.com/golang-migrate/migrate/v4/source/file"
)

func main() {
	path := flag.String("path", "migrations", "迁移文件目录（相对当前工作目录）")
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr,
			"用法: migrate [-path migrations] up | down [N] | version | force <V>\n"+
				"  up        应用所有未落地的迁移\n"+
				"  down [N]  回退 N 步（省略时 1 步）；本仓库的 .down.sql 会 DROP 表，动它之前先想清楚\n"+
				"  version   打印 schema_migrations 里的当前版本\n"+
				"  force V   清掉 dirty 标记并把版本设为 V（只在迁移中途被强杀后用）\n"+
				"连接串取环境变量 DATABASE_URL。\n")
		flag.PrintDefaults()
	}
	flag.Parse()
	args := flag.Args()
	if len(args) == 0 {
		flag.Usage()
		os.Exit(2)
	}

	dsn, err := databaseURL()
	if err != nil {
		fmt.Fprintf(os.Stderr, "migrate: %v\n", err)
		os.Exit(2)
	}
	// file source 要绝对路径：相对 `migrations` 会被解析成 `file://migrations`，
	// 而 `//` 之后是主机名，于是报的是"找不到主机 migrations"这种看不出根因的错。
	abs, err := filepath.Abs(*path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "migrate: 迁移目录不可用: %v\n", err)
		os.Exit(1)
	}

	m, err := migrate.New("file://"+filepath.ToSlash(abs), dsn)
	if err != nil {
		fmt.Fprintf(os.Stderr, "migrate: 初始化失败: %v\n", err)
		os.Exit(1)
	}
	defer func() {
		// Close 返回 (source 侧, 数据库侧) 两个错。两边都只可能是"已经关过"这类
		// 收尾噪声，不能让它盖住真正的迁移结果，所以只打印不改变退出码。
		srcErr, dbErr := m.Close()
		if srcErr != nil {
			fmt.Fprintf(os.Stderr, "migrate: 关闭 source: %v\n", srcErr)
		}
		if dbErr != nil {
			fmt.Fprintf(os.Stderr, "migrate: 关闭数据库连接: %v\n", dbErr)
		}
	}()

	if err := run(m, args); err != nil {
		fmt.Fprintf(os.Stderr, "migrate: %v\n", err)
		os.Exit(1)
	}
}

// run 把子命令映射到 migrate 的方法，并把「已到底」和「dirty」两种状态分开报——
// 它们都返回 error，但只有后者是问题，幂等重跑必须 exit 0（X6 的判据就是"连跑两次都 rc 0"）。
func run(m *migrate.Migrate, args []string) error {
	switch args[0] {
	case "up":
		if err := m.Up(); err != nil && err != migrate.ErrNoChange {
			return describe(err)
		}
		fmt.Println("up: 迁移已全部落地")
		return nil
	case "down":
		n, err := step(args)
		if err != nil {
			return err
		}
		if err := m.Steps(-n); err != nil && err != migrate.ErrNoChange {
			return describe(err)
		}
		fmt.Printf("down: 已回退 %d 步\n", n)
		return nil
	case "version":
		v, dirty, err := m.Version()
		if err == migrate.ErrNilVersion {
			fmt.Println("version: 库里还没有任何 Go 侧迁移记录（schema_migrations 为空）")
			return nil
		}
		if err != nil {
			return describe(err)
		}
		if dirty {
			fmt.Printf("version: %d **dirty**——上次迁移中途失败，修完用 `force %d` 复位\n", v, v)
			return fmt.Errorf("数据库处于 dirty 状态")
		}
		fmt.Printf("version: %d clean\n", v)
		return nil
	case "force":
		if len(args) < 2 {
			return fmt.Errorf("force 需要一个版本号")
		}
		var v uint
		if _, err := fmt.Sscanf(args[1], "%d", &v); err != nil {
			return fmt.Errorf("force 的版本号不认识: %s", args[1])
		}
		if err := m.Force(int(v)); err != nil {
			return describe(err)
		}
		fmt.Printf("force: 版本已设为 %d 并清除 dirty\n", v)
		return nil
	default:
		return fmt.Errorf("未知子命令 %q（up / down / version / force）", args[0])
	}
}

// describe 把 migrate 的内部错误翻成可执行的下一步。dirty 那条尤其要说清动作，
// 因为它的原文是 "Dirty database version 2. Fix and force version."——
// 读到这句的人不会知道"Fix"指的是修 DDL 还是修库。
func describe(err error) error {
	if strings.HasPrefix(err.Error(), "Dirty database version") {
		return fmt.Errorf("%v\n  上一步迁移中途失败且已回滚，库停在半程（schema_migrations.dirty=true）："+
			"先修那条 DDL，再重跑 up；要把 dirty 清掉就 force 到上一个 clean 版本", err)
	}
	if strings.Contains(err.Error(), "database is locked") {
		return fmt.Errorf("迁移被别的执行器占住（同一时间只该有一个 migrate 在跑）: %w", err)
	}
	return err
}

func step(args []string) (int, error) {
	if len(args) < 2 {
		return 1, nil
	}
	var n int
	if _, err := fmt.Sscanf(args[1], "%d", &n); err != nil {
		return 0, fmt.Errorf("down 的步数不认识: %s", args[1])
	}
	if n < 0 {
		return 0, fmt.Errorf("down 的步数不能是负数: %d", n)
	}
	return n, nil
}

// databaseURL 读 DATABASE_URL，并把 Python 侧的写法归一成 Go 驱动认得的。
// 这一层必须存在而不是指望调用方：`.env` 里的 DATABASE_URL 是
// `postgresql+psycopg2://`（SQLAlchemy 的方案串），直接交给 lib/pq 会以
// "unknown scheme" 失败，而报出来的错完全看不出是方案名的问题。
// `dev.py go-serve` 对 go-api 做的是同一件事，两处口径一致。
func databaseURL() (string, error) {
	raw := os.Getenv("DATABASE_URL")
	if raw == "" {
		return "", fmt.Errorf("DATABASE_URL 未设置。dev 形态下走 `dev.py migrate-go`（它会注入 .env），" +
			"或直接导出一个 postgres:// 连接串")
	}
	raw = strings.Replace(raw, "postgresql+psycopg2://", "postgres://", 1)
	raw = strings.Replace(raw, "postgresql://", "postgres://", 1)
	if !strings.HasPrefix(raw, "postgres://") {
		return "", fmt.Errorf("DATABASE_URL 方案不认识: %s（要 postgres://…）", raw)
	}
	// Go 侧连的是本地 compose 发布的 PG，没有服务端证书；Python 那边同一个库也不走 TLS。
	// 缺 sslmode 时 lib/pq 的默认值是 require，会以"x509: certificate signed by unknown authority"
	// 失败——所以没显式写就补 disable，而不是让人去猜为什么连不上。
	if !strings.Contains(raw, "sslmode=") {
		if strings.Contains(raw, "?") {
			raw += "&sslmode=disable"
		} else {
			raw += "?sslmode=disable"
		}
	}
	return raw, nil
}
