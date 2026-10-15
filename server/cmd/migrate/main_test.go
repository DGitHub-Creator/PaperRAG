package main

import "testing"

// 这个命令是"把 DDL 落到库上"的动作，它最容易失效的两处都在**到达数据库之前**：
// 连接串被方案名判死、迁移目录被当成主机名。所以这里的用例全部围绕这两件事，
// 而不是去连一个真库——真库那一半由 `dev.py migrate-go` 在 chain 层取证。

func TestDatabaseURLNormalizesSqlalchemySchemes(t *testing.T) {
	// .env 里的 DATABASE_URL 是 SQLAlchemy 写法。原样交给 lib/pq 报的是
	// "unknown scheme"，看不出根因，所以必须先归一。
	for _, in := range []string{
		"postgresql+psycopg2://postgres:pw@127.0.0.1:5432/langchain_app",
		"postgresql://postgres:pw@127.0.0.1:5432/langchain_app",
	} {
		t.Setenv("DATABASE_URL", in)
		got, err := databaseURL()
		if err != nil {
			t.Fatalf("%s: %v", in, err)
		}
		if got != "postgres://postgres:pw@127.0.0.1:5432/langchain_app?sslmode=disable" {
			t.Fatalf("归一结果不对: %s", got)
		}
	}
}

func TestDatabaseURLKeepsExplicitSSLMode(t *testing.T) {
	// 已经写了 sslmode 的就别再加一个：两个 sslmode 参数时 lib/pq 取哪个是不定的。
	t.Setenv("DATABASE_URL", "postgres://u:p@h:5432/db?sslmode=require")
	got, err := databaseURL()
	if err != nil {
		t.Fatal(err)
	}
	if got != "postgres://u:p@h:5432/db?sslmode=require" {
		t.Fatalf("不该动已有的 sslmode: %s", got)
	}
}

func TestDatabaseURLRejectsMissingAndUnrecognized(t *testing.T) {
	t.Setenv("DATABASE_URL", "")
	if _, err := databaseURL(); err == nil {
		t.Fatal("缺 DATABASE_URL 必须报错，不能拿空串去连库")
	}
	t.Setenv("DATABASE_URL", "mysql://u:p@h:3306/db")
	if _, err := databaseURL(); err == nil {
		t.Fatal("认不出的方案要拒绝，不能静默交给驱动")
	}
}

func TestStepDefaultsToOneAndRejectsNegative(t *testing.T) {
	if n, err := step([]string{"down"}); err != nil || n != 1 {
		t.Fatalf("省略步数该回退 1 步，得到 %d/%v", n, err)
	}
	if n, err := step([]string{"down", "3"}); err != nil || n != 3 {
		t.Fatalf("down 3 该是 3 步，得到 %d/%v", n, err)
	}
	if _, err := step([]string{"down", "-2"}); err == nil {
		t.Fatal("负数步数要拒绝——它会让 Steps(-n) 变成前进，语义完全反过来")
	}
	if _, err := step([]string{"down", "abc"}); err == nil {
		t.Fatal("认不出的步数要拒绝")
	}
}
