#!/usr/bin/env python3
"""统一开发命令入口（P0-0）。

只用标准库，因此可在 `uv sync` 之前运行；跨平台依赖 Windows/Linux/macOS 都有的
`docker compose`，避免 README 里出现只适用于某个 shell 的启动命令。

    uv run python scripts/dev.py doctor              # 起栈前自检：docker/.env/端口/uv
    uv run python scripts/dev.py infra               # 只起中间件（源码跑后端的推荐路径，不构建镜像）
    uv run python scripts/dev.py serve               # 本机源码跑 Python 上游（uvicorn --reload）
    uv run python scripts/dev.py go-serve            # 本机源码跑 go-api（唯一公开入口，反代未迁移面）
    uv run python scripts/dev.py seed-admin          # 幂等创建管理员（读 .env 的 ADMIN_USERNAME/PASSWORD）
    uv run python scripts/dev.py up                  # compose up -d 并等 healthy（全栈容器，含 backend 镜像）
    uv run python scripts/dev.py ps
    uv run python scripts/dev.py logs -f backend
    uv run python scripts/dev.py migrate             # 容器内 alembic upgrade head
    uv run python scripts/dev.py test -m unit        # 分层跑测试
    uv run python scripts/dev.py test -- -k auth -v  # 透传 pytest 自己的选项
    uv run python scripts/dev.py gen                  # 重生成 Go 数据访问层（sqlc）
    uv run python scripts/dev.py gen --check          # 生成物漂移门禁
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
COMPOSE_FILE = ROOT / "docker-compose.yml"
SERVER_DIR = ROOT / "server"

# sqlc 版本钉死：生成物入库（决策 K2）后，两个人用不同版本重生成会得到不同代码，
# `git diff --exit-code` 门禁就会以"别人的改动"为名把 CI 弄红，而且没人看得出原因。
SQLC_VERSION = "v1.30.0"

# compose 里被 depends_on 或健康检查依赖的服务容器名（与 docker-compose.yml 的 container_name 一致）
HEALTH_CONTAINERS = ["researchpilot-postgres", "researchpilot-redis", "milvus-standalone", "researchpilot-backend"]

# 服务名 → 容器名。只请求部分服务时要按"这次真正起的"等健康：否则
# `dev.py up postgres` 会一直等一个根本没被创建的 backend 容器，直到超时失败。
SERVICE_CONTAINERS = {
    "postgres": "researchpilot-postgres",
    "redis": "researchpilot-redis",
    "etcd": "milvus-etcd",
    "minio": "milvus-minio",
    "standalone": "milvus-standalone",
    "attu": "milvus-attu",
    "backend": "researchpilot-backend",
}

#: 源码跑后端时需要的中间件（不含 backend —— 它由 `dev.py serve` 在本机跑）
INFRA_SERVICES = ["postgres", "redis", "etcd", "minio", "standalone", "attu"]
HOST_PORTS = {5432: "postgres", 6379: "redis", 19530: "milvus", 8000: "backend"}
SECRET_PLACEHOLDERS = ("replace-with-strong-random-secret", "dev-only-insecure-jwt-secret")


def run(
    cmd: list[str],
    *,
    check: bool = False,
    capture: bool = False,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=capture, env=env)
    if capture:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
    if check and proc.returncode != 0:
        raise SystemExit(f"命令失败 (rc={proc.returncode}): {' '.join(cmd)}")
    return proc.returncode


def compose(*args: str, capture: bool = False) -> int:
    return run(compose_cmd() + list(args), capture=capture)


_compose_cmd: list[str] | None = None


def compose_cmd() -> list[str]:
    global _compose_cmd
    if _compose_cmd is None:
        if _exec_ok(["docker", "compose", "version"]):
            _compose_cmd = ["docker", "compose"]
        elif shutil.which("docker-compose"):
            _compose_cmd = ["docker-compose"]
        else:
            raise SystemExit("未找到 docker compose。请安装 Docker Desktop，或把 docker 加入 PATH 后重试。")
    return _compose_cmd


def _exec_ok(cmd: list[str]) -> bool:
    if not shutil.which(cmd[0]):
        return False
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def process_env() -> dict[str, str]:
    """当前环境 + `.env` 的合并，供**不由 Python 自我加载 .env 的子进程**使用。

    Python 侧的配置模块自己调 `load_dotenv()`（`backend/core/config/__init__.py:22`），
    所以 `serve` 不必注入；但 Go 进程不会读 `.env`，`go run ./cmd/api` 若拿不到
    DATABASE_URL / JWT_SECRET_KEY 就会在 fail-fast 处直接退出。这里把 `.env` 显式并入
    subprocess 的环境，规则是**已存在的真实环境变量优先**（同 dotenv 的 override=False）。
    """
    env = dict(os.environ)
    for key, value in read_env_file(ENV_FILE).items():
        env.setdefault(key, value)
    # 同一份 .env 要喂两个运行时，而两边的连接串语法不同：Python 的 SQLAlchemy 用
    # `postgresql+psycopg2://`，Go 的 pgx 只认 `postgres://` / `postgresql://`。
    # 在**交给 Go 的那一份**上剥掉方言后缀，.env 本身保持 Python 侧的原样。
    if env.get("DATABASE_URL"):
        env["DATABASE_URL"] = database_url_for_go(env["DATABASE_URL"])
    return env


def database_url_for_go(url: str) -> str:
    """剥掉 SQLAlchemy 的方言后缀（`postgresql+psycopg2` → `postgresql`），pgx 才解析得了。"""
    scheme, sep, rest = url.partition("://")
    if sep and "+" in scheme:
        scheme = scheme.split("+", 1)[0]
    return f"{scheme}{sep}{rest}"


def read_env_file(path: Path) -> dict[str, str]:
    """解析 .env 的 `KEY=VALUE`，忽略注释与空行。只用于自检与子进程注入。"""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def cmd_doctor(_: argparse.Namespace) -> int:
    problems: list[str] = []
    hints: list[str] = []

    if not COMPOSE_FILE.exists():
        problems.append(f"缺少 {COMPOSE_FILE.name}")

    if shutil.which("docker"):
        if _exec_ok(["docker", "info"]):
            print("[ok] docker daemon 可用")
        else:
            problems.append("docker CLI 在 PATH 里，但 daemon 没在跑（Docker Desktop 未启动？）")

    # compose 静态校验不需要 daemon：插值、字段拼写、端口形状在这里就能判。
    # 分开报的目的是让"compose 写错了"和"环境没起来"成为两个不同的失败原因，
    # 否则 daemon 没起时 up 只丢一句连不上，人要猜是哪种。
    if COMPOSE_FILE.exists() and (_exec_ok(["docker", "compose", "version"]) or shutil.which("docker-compose")):
        proc = subprocess.run(compose_cmd() + ["config", "--quiet"], cwd=str(ROOT), capture_output=True, text=True)
        detail = (proc.stderr or proc.stdout).strip()
        if proc.returncode == 0:
            print("[ok] docker-compose.yml 静态校验通过（compose config，不依赖 daemon）")
        else:
            problems.append(f"docker-compose.yml 静态校验失败：{detail.splitlines()[0] if detail else '无输出'}")
    else:
        problems.append("未找到 docker CLI → 安装 Docker Desktop 后重跑 doctor")

    if ENV_FILE.exists():
        env = read_env_file(ENV_FILE)
        secret = env.get("JWT_SECRET_KEY", "")
        if not secret:
            problems.append(".env 里 JWT_SECRET_KEY 为空 → 应用会拒绝启动（335aeb7e 起 fail-fast）")
            hints.append('生成：uv run python -c "import secrets;print(secrets.token_urlsafe(32))" 写入 .env 的 JWT_SECRET_KEY=')
        elif secret in SECRET_PLACEHOLDERS:
            problems.append("JWT_SECRET_KEY 仍是占位值，等同没配")
        else:
            print("[ok] JWT_SECRET_KEY 已配置")
        if env.get("LLM_API_KEY") or env.get("ARK_API_KEY"):
            print("[ok] LLM 密钥已配置")
        else:
            hints.append("未配 LLM 密钥：上传→问答链路只能验到解析与入库，回答质量类用例跳过")
    else:
        problems.append("缺少 .env → cp .env.example .env 并填入 JWT_SECRET_KEY")

    if not shutil.which("uv"):
        hints.append("未找到 uv → 依赖安装会退回 pip，版本可复现性下降")

    if shutil.which("docker"):
        for port, service in HOST_PORTS.items():
            if not port_free(port):
                hints.append(f"宿主端口 {port} 已被占用（{service} 映射到它），compose 起不来前先确认是谁在用")

    for line in problems:
        print(f"[问题] {line}")
    for line in hints:
        print(f"[提示] {line}")
    if problems:
        print(f"\ndoctor: {len(problems)} 项阻塞，先解决再 up。")
        return 1
    print("\ndoctor: 通过。")
    return 0


def container_health(name: str) -> str:
    proc = subprocess.run(
        ["docker", "inspect", "--format", "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}", name],
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "missing"


def cmd_up(args: argparse.Namespace) -> int:
    rc = compose("up", "-d", *(args.svc or []))
    if rc != 0:
        return rc
    if args.no_wait:
        return 0
    # 只等这次真正请求的服务；不传 svc 时才是全套 HEALTH_CONTAINERS。
    if args.svc:
        targets = [SERVICE_CONTAINERS[s] for s in args.svc if s in SERVICE_CONTAINERS]
    else:
        targets = list(HEALTH_CONTAINERS)
    deadline = time.monotonic() + args.timeout
    pending = list(targets)
    while pending and time.monotonic() < deadline:
        pending = [name for name in pending if container_health(name) not in ("healthy", "none")]
        if pending:
            print("等待健康: " + ", ".join(pending), flush=True)
            time.sleep(5)
    if pending:
        print(f"超时仍有容器未 healthy: {', '.join(pending)}")
        print("排查：docker compose logs <service>")
        return 1
    print("全部容器 healthy。")
    return 0


def cmd_infra(args: argparse.Namespace) -> int:
    """只起中间件，后端在本机源码跑（见 `serve`）。

    这条路径不构建 backend 镜像（含 torch 的 16.5 GB 镜像），改代码也不用重建；
    config 层默认值已经指向 127.0.0.1（DATABASE_URL / REDIS_URL / MILVUS_HOST），
    因此除 `.env` 的必填项外无需额外环境变量。
    """
    ns = argparse.Namespace(svc=list(INFRA_SERVICES), no_wait=args.no_wait, timeout=args.timeout)
    return cmd_up(ns)


def cmd_serve(args: argparse.Namespace) -> int:
    """在本机（当前解释器）跑后端，等价于 uvicorn backend.app:app。

    前置：中间件已就绪（`dev.py infra`）、依赖已装（`uv sync --extra test`）。
    """
    cmd = [
        sys.executable, "-m", "uvicorn", "backend.app:app",
        "--host", args.host, "--port", str(args.port),
    ]
    if not args.no_reload:
        cmd.append("--reload")
    return run(cmd)


def cmd_go_serve(_: argparse.Namespace) -> int:
    """在本机源码跑 go-api —— 唯一公开入口（02 §2）。

    前置：中间件已就绪（`dev.py infra`）、Python 上游已在跑（`dev.py serve`）。
    go-api 接管 health/ready/auth，其余 /api 反代到 PYTHON_UPSTREAM（默认 127.0.0.1:8000）。
    `.env` 由本函数注入进子进程环境（Go 不自我加载 .env）。
    """
    return run(["go", "run", "./cmd/api"], cwd=SERVER_DIR, env=process_env())


def cmd_seed_admin(_: argparse.Namespace) -> int:
    """幂等创建/校正一个管理员账号（Go 侧 `cmd/seed`，直连 PostgreSQL）。

    凭证只从环境变量来（`.env` 里的 ADMIN_USERNAME / ADMIN_PASSWORD / ADMIN_ROLE），
    命令行参数里不留任何口令——它会进 shell 历史与 `ps` 输出。
    """
    return run(["go", "run", "./cmd/seed"], cwd=SERVER_DIR, env=process_env())


def cmd_down(args: argparse.Namespace) -> int:
    cmd = ["down"]
    if args.volumes:
        cmd.append("-v")
    return compose(*cmd)


def cmd_ps(_: argparse.Namespace) -> int:
    return compose("ps")


def cmd_logs(args: argparse.Namespace) -> int:
    cmd = ["logs"]
    if args.follow:
        cmd.append("-f")
    cmd += ["--tail", str(args.tail)] + args.svc
    return compose(*cmd)


def cmd_migrate(args: argparse.Namespace) -> int:
    """应用启动时已自动 upgrade head；这里给「只改库、不重启服务」的场景留一个显式入口。"""
    return compose("exec", "-T", args.service, "python", "-m", "alembic", "upgrade", "head")


def cmd_test(args: argparse.Namespace) -> int:
    cmd = [sys.executable, "-m", "pytest"]
    if args.marker:
        cmd += ["-m", args.marker]
    cmd += args.pytest_args or ["-q"]
    return run(cmd)


def sqlc_binary() -> str | None:
    """找本机 sqlc：PATH 优先，其次 `go install` 的默认落点 GOBIN/~/go/bin。"""
    found = shutil.which("sqlc")
    if found:
        return found
    gobin = os.environ.get("GOBIN") or str(Path.home() / "go" / "bin")
    name = "sqlc.exe" if os.name == "nt" else "sqlc"
    candidate = Path(gobin) / name
    return str(candidate) if candidate.exists() else None


def _sqlc_schema_sources() -> list[str] | None:
    """从 `server/sqlc.yaml` 取 sql 段的 schema 源列表。

    dev.py 只用标准库（要在 `uv sync` 之前就能跑），所以这里按行解析而不是引 YAML 库。
    解析不出来返回 None，由调用方判成配置异常并拒绝生成——**不能"当作没配"**，
    因为这个函数的唯一用途就是确认每张基线表都进了 sqlc 的视野。
    """
    path = SERVER_DIR / "sqlc.yaml"
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s*schema:\s*$", line):
            indent = len(line) - len(line.lstrip())
            out = []
            for nxt in lines[i + 1 :]:
                if not nxt.strip() or len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                m = re.match(r"^\s*-\s+[\"']?(?P<v>.*?)[\"']?\s*$", nxt)
                if m:
                    out.append(m.group("v"))
            return out
    return None


def check_sqlc_schema_sources() -> list[str]:
    """sqlc 必须看得见 migrations/ 里每一个 up 文件，且不能把整个目录当 schema。

    后者是真陷阱：sqlc 按文件名排序读目录，`000001_baseline.down.sql` 排在 `.up.sql` 前面，
    于是它先 DROP 再 CREATE——生成物看着正常，实际是按"回退后的库"生成的。
    """
    errors: list[str] = []
    sources = _sqlc_schema_sources()
    if sources is None:
        return ["server/sqlc.yaml 里解析不到 sql.schema 列表——覆盖检查无法进行，拒绝生成"]

    for src in sources:
        p = SERVER_DIR / src
        if p.is_dir() and any(p.glob("*.down.sql")):
            errors.append(
                f"sql.schema 指向目录 {src}，里面有 .down.sql。"
                "sqlc 会按文件名顺序把 down 当 schema 执行（先 DROP 再 CREATE），"
                "生成物等于按回退后的库产出——请逐个列出 *.up.sql"
            )
        if not p.exists():
            errors.append(f"sql.schema 列了不存在的源：{src}")

    ups = sorted(p.name for p in (SERVER_DIR / "migrations").glob("*.up.sql"))
    listed = {Path(src).name for src in sources}
    for missing in [u for u in ups if u not in listed]:
        errors.append(
            f"migrations/{missing} 没有出现在 sqlc.yaml 的 schema 列表里："
            "新迁移建了表但 Go 看不见，重生成不会报错，只会静默少一张表。"
            "把它加进 schema 列表再 gen。"
        )
    return errors


def check_sqlc_orphan_outputs() -> list[str]:
    """删掉的查询会在生成物里留下孤儿：sqlc 只写不删 `X.sql.go`，`git diff` 也看不出问题。

    本机实测过一次——临时探针查询删掉后，`_probe.sql.go` 与它带出来的 struct 都还在树里，
    那就是一个没人调用、但每次 gen 都会重新出现在视野里的 Go 类型。
    """
    errors: list[str] = []
    out_dir = SERVER_DIR / "internal" / "db"
    for gen in sorted(out_dir.glob("*.sql.go")):
        stem = gen.name[: -len(".sql.go")]
        if not (SERVER_DIR / "sql" / "queries" / f"{stem}.sql").exists():
            errors.append(
                f"internal/db/{gen.name} 没有对应的 sql/queries/{stem}.sql："
                "sqlc 不会自己删输出，手工删掉它再 gen"
            )
    return errors


def cmd_gen(args: argparse.Namespace) -> int:
    """重新生成 Go 数据访问层（P0-3 / K2）。

    生成物进版本库，一致性由 `--check` 保证：改完 .sql 忘记 gen，这条就会红。
    找不到本机 sqlc 时退回 `go run …@固定版本`，慢一次但结果与别人一致。
    """
    problems = check_sqlc_schema_sources() + check_sqlc_orphan_outputs()
    if problems:
        print("[gen] 生成前置检查不通过：")
        for e in problems:
            print(f"      - {e}")
        return 1

    binary = sqlc_binary()
    if binary:
        proc = subprocess.run([binary, "version"], capture_output=True, text=True)
        got = (proc.stdout or "").strip()
        if SQLC_VERSION.lstrip("v") not in got:
            print(f"[gen] sqlc 版本不匹配：本机 {got or '未知'}，仓库钉的是 {SQLC_VERSION}")
            print("      跨版本重生成会产出结构不同的代码，diff 门禁会失去意义。")
            print(f"      对齐：go install github.com/sqlc-dev/sqlc/cmd/sqlc@{SQLC_VERSION}")
            return 1
        cmd = [binary, "generate"]
    else:
        print(f"[gen] 未找到本机 sqlc，退回 go run …@{SQLC_VERSION}（首次会下载依赖）")
        cmd = ["go", "run", f"github.com/sqlc-dev/sqlc/cmd/sqlc@{SQLC_VERSION}", "generate"]

    if run(cmd, cwd=SERVER_DIR) != 0:
        return 1
    if not args.check:
        print("[gen] 已生成 server/internal/db/")
        return 0

    rc = run(["git", "diff", "--exit-code", "--", "server/internal/db", "server/sqlc.yaml"])
    if rc != 0:
        print("[gen] 生成物与提交不一致：改了 .sql 就要把重生成结果一起提交（K2 的门禁）")
        return rc
    print("[gen] 生成物无漂移。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dev.py", description="ResearchPilot 开发环境统一入口（只用标准库）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="起栈前自检：docker/.env/端口/uv").set_defaults(func=cmd_doctor)

    up = sub.add_parser("up", help="compose up -d 并等待健康（全栈容器）")
    up.add_argument("svc", nargs="*", help="只起指定服务")
    up.add_argument("--timeout", type=int, default=300, help="等待 healthy 的秒数")
    up.add_argument("--no-wait", action="store_true", help="只起不等")
    up.set_defaults(func=cmd_up)

    infra = sub.add_parser("infra", help="只起中间件（源码跑后端；不构建 backend 镜像）")
    infra.add_argument("--timeout", type=int, default=300, help="等待 healthy 的秒数")
    infra.add_argument("--no-wait", action="store_true", help="只起不等")
    infra.set_defaults(func=cmd_infra)

    serve = sub.add_parser("serve", help="本机源码跑后端（uvicorn）；前置：infra 已就绪")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--no-reload", action="store_true", help="关掉热重载")
    serve.set_defaults(func=cmd_serve)

    go_serve = sub.add_parser("go-serve", help="本机源码跑 go-api（唯一公开入口）；前置：infra + serve")
    go_serve.set_defaults(func=cmd_go_serve)

    seed_admin = sub.add_parser("seed-admin", help="幂等创建管理员账号（凭证读 ADMIN_* 环境变量）")
    seed_admin.set_defaults(func=cmd_seed_admin)

    down = sub.add_parser("down", help="停止栈")
    down.add_argument("--volumes", action="store_true", help="连数据卷一起删（会清空 PG/Milvus 数据）")
    down.set_defaults(func=cmd_down)

    sub.add_parser("ps", help="容器状态").set_defaults(func=cmd_ps)

    logs = sub.add_parser("logs", help="看日志")
    logs.add_argument("-f", "--follow", action="store_true")
    logs.add_argument("--tail", type=int, default=200)
    logs.add_argument("svc", nargs="*", default=[])
    logs.set_defaults(func=cmd_logs)

    migrate = sub.add_parser("migrate", help="在容器内跑 alembic upgrade head")
    migrate.add_argument("--service", default="backend")
    migrate.set_defaults(func=cmd_migrate)

    test = sub.add_parser("test", help="本地测试（-m 选层；要传 pytest 自己的选项用 `-- ` 分隔）")
    test.add_argument("-m", "--marker", default=None, help="只跑某一层：unit / integration / chain / e2e / slow")
    test.add_argument("pytest_args", nargs="*", default=[], help="透传给 pytest，如 `test -- -k auth -v`")
    test.set_defaults(func=cmd_test)

    gen = sub.add_parser("gen", help="重生成 Go 数据访问层（sqlc）；--check 兼作生成物漂移门禁")
    gen.add_argument("--check", action="store_true", help="生成后要求 git diff 为空")
    gen.set_defaults(func=cmd_gen)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
