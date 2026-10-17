"""在新建隔离库验证存储重构；原开发库只用于读取连接配置，不读写业务数据。"""

import argparse
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify_http(environment: dict, temporary: str, credentials: dict) -> int:
    """在同一个隔离库启动两个真实源码进程，仅验认证/会话，不调用 LLM 或 Milvus。"""
    import httpx

    ports = []
    while len(ports) < 2:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            if port not in ports:
                ports.append(port)
    go_url, python_url = (f"http://127.0.0.1:{port}" for port in ports)
    prefix = "quality_http_" + uuid4().hex
    environment.update({
        "APP_ENV": "development", "PORT": str(ports[0]), "PYTHON_UPSTREAM": python_url,
        "CHAIN_GO_API_URL": go_url, "CHAIN_AI_CORE_URL": python_url,
        "REDIS_KEY_PREFIX": prefix, "CHAIN_REDIS_PREFIX": prefix,
        "JWT_SECRET_KEY": secrets.token_urlsafe(32),
        "ADMIN_INVITE_CODE": secrets.token_urlsafe(32),
        "USE_REDIS_JOB_MANAGER": "true",
        "TRUST_PROXY_HEADERS": "false", "TRUSTED_PROXY_CIDRS": "", "RATE_LIMIT": "",
        "LLM_API_KEY": "unused-by-auth-verification", "LLM_MODEL": "unused-by-auth-verification",
    })
    environment["CHAIN_ADMIN_INVITE_CODE"] = environment["ADMIN_INVITE_CODE"]
    binary = Path(temporary) / ("api.exe" if os.name == "nt" else "api")
    subprocess.run(["go", "build", "-o", str(binary), "./cmd/api"], cwd=ROOT / "server", check=True)
    children, logs = [], []
    try:
        commands = [[str(binary)], [sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(ports[1]), "--no-proxy-headers"]]
        for index, command in enumerate(commands):
            log = (Path(temporary) / f"http-{index}.log").open("w", encoding="utf-8")
            logs.append(log)
            role, password = credentials["go" if index == 0 else "python"]
            child_environment = {**environment, "DATABASE_URL": make_url(environment["DATABASE_URL"]).set(username=role, password=password).render_as_string(hide_password=False)}
            children.append(subprocess.Popen(
                command, cwd=ROOT, env=child_environment, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ))
        deadline = time.monotonic() + 45
        with httpx.Client(timeout=1) as client:
            for child, url in zip(children, (go_url + "/api/v1/health", python_url + "/health"), strict=True):
                while True:
                    if child.poll() is not None:
                        raise RuntimeError("隔离 HTTP 服务启动失败，请检查数据库迁移与必填配置")
                    try:
                        ready = client.get(url).status_code == 200
                    except httpx.RequestError:
                        ready = False
                    if ready:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("隔离 HTTP 服务启动超时")
                    time.sleep(0.2)
        return subprocess.run([
            sys.executable, "-m", "pytest", "-q", "--tb=short", "-m", "chain",
            "tests/chain/test_go_auth_cross_validation.py", "tests/chain/test_go_read_sessions.py",
        ], cwd=ROOT, env=environment).returncode
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for log in logs:
            log.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-container", default="researchpilot-postgres")
    parser.add_argument("--http", action="store_true", help="另启 Go/Python 真实入口，验证认证、限流与会话删除")
    args = parser.parse_args()
    environment = {**{k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}, **os.environ}
    url = make_url(environment.get("DATABASE_URL") or "postgresql://postgres:postgres@127.0.0.1:5432/langchain_app")
    name = "quality_" + uuid4().hex
    credentials = {app: (name + "_" + app, secrets.token_urlsafe(32)) for app in ("go", "python")}
    roles_created = False

    def sql(statement):
        subprocess.run(
            ["docker", "exec", "-i", args.postgres_container, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres"],
            input=statement, text=True, encoding="utf-8", check=True, capture_output=True,
        )

    sql(f"CREATE DATABASE {name};")
    try:
        with tempfile.TemporaryDirectory(prefix="researchpilot-storage-") as temporary:
            binary = Path(temporary) / ("migrate.exe" if os.name == "nt" else "migrate")
            subprocess.run(["go", "build", "-o", str(binary), "./cmd/migrate"], cwd=ROOT / "server", check=True)
            environment["DATABASE_URL"] = url.set(drivername="postgresql", database=name).render_as_string(hide_password=False)
            environment["REFACTOR_TEST_DATABASE_URL"] = url.set(drivername="postgresql+psycopg2", database=name).render_as_string(hide_password=False)
            environment["REFACTOR_TEST_REDIS_URL"] = environment.get("REDIS_URL", "redis://127.0.0.1:6379/0")
            environment["TEMP"] = environment["TMP"] = temporary
            environment["REFACTOR_MIGRATE_BINARY"] = str(binary)
            for _ in range(2):
                subprocess.run([str(binary), "-path", str(ROOT / "server/migrations"), "up"], env=environment, check=True)
            result = subprocess.run([
                sys.executable, "-m", "pytest", "-q", "--tb=short",
                "tests/integration/test_conversation_postgres.py",
                "tests/integration/test_execution_postgres.py",
                "tests/integration/test_document_job_state.py",
                "tests/integration/test_document_recovery.py",
            ], cwd=ROOT, env=environment).returncode
            if result == 0 and args.http:
                # 测试铺数仍用隔离库管理员；两个实际服务仅获得当前需要的表级权限。
                from scripts.configure_database_roles import configure_roles
                configure_roles(environment["DATABASE_URL"], credentials)
                roles_created = True
                return verify_http(environment, temporary, credentials)
            return result
    finally:
        # 名称仅由本函数生成，只删除刚创建的隔离库，不接受外部传入数据库名。
        sql(f"DROP DATABASE {name};")
        if roles_created:
            for role, _ in credentials.values():
                # 库删除后对象授权随之消失；角色只由本轮 UUID 创建。
                sql(f"DROP ROLE {role};")


if __name__ == "__main__":
    raise SystemExit(main())
