#!/usr/bin/env python3
"""统一开发命令入口（P0-0）。

只用标准库，因此可在 `uv sync` 之前运行；跨平台依赖 Windows/Linux/macOS 都有的
`docker compose`，避免 README 里出现只适用于某个 shell 的启动命令。

    uv run python scripts/dev.py doctor              # 起栈前自检：docker/.env/端口/uv
    uv run python scripts/dev.py up                  # compose up -d 并等 healthy
    uv run python scripts/dev.py ps
    uv run python scripts/dev.py logs -f backend
    uv run python scripts/dev.py migrate             # 容器内 alembic upgrade head
    uv run python scripts/dev.py test -m unit        # 分层跑测试
    uv run python scripts/dev.py test -- -k auth -v  # 透传 pytest 自己的选项
"""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
COMPOSE_FILE = ROOT / "docker-compose.yml"

# compose 里被 depends_on 或健康检查依赖的服务容器名（与 docker-compose.yml 的 container_name 一致）
HEALTH_CONTAINERS = ["paperrag-postgres", "paperrag-redis", "milvus-standalone", "paperrag-backend"]
HOST_PORTS = {5432: "postgres", 6379: "redis", 19530: "milvus", 8000: "backend"}
SECRET_PLACEHOLDERS = ("replace-with-strong-random-secret", "dev-only-insecure-jwt-secret")


def run(cmd: list[str], *, check: bool = False, capture: bool = False, cwd: Path = ROOT) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=capture)
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


def read_env_file(path: Path) -> dict[str, str]:
    """解析 .env 的 `KEY=VALUE`，忽略注释与空行。只用于自检，不注入环境。"""
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
    else:
        problems.append("未找到 docker CLI → 安装 Docker Desktop 后重跑 doctor")

    if ENV_FILE.exists():
        env = read_env_file(ENV_FILE)
        secret = env.get("JWT_SECRET_KEY", "")
        if not secret:
            problems.append(".env 里 JWT_SECRET_KEY 为空 → 应用会拒绝启动（d8f1563 起 fail-fast）")
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
    deadline = time.monotonic() + args.timeout
    pending = list(HEALTH_CONTAINERS)
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dev.py", description="ResearchPilot 开发环境统一入口（只用标准库）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="起栈前自检：docker/.env/端口/uv").set_defaults(func=cmd_doctor)

    up = sub.add_parser("up", help="compose up -d 并等待健康")
    up.add_argument("svc", nargs="*", help="只起指定服务")
    up.add_argument("--timeout", type=int, default=300, help="等待 healthy 的秒数")
    up.add_argument("--no-wait", action="store_true", help="只起不等")
    up.set_defaults(func=cmd_up)

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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
