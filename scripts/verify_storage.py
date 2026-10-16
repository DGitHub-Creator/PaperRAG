"""在新建隔离库验证存储重构；原开发库只用于读取连接配置，不读写业务数据。"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-container", default="researchpilot-postgres")
    args = parser.parse_args()
    environment = {**{k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}, **os.environ}
    url = make_url(environment.get("DATABASE_URL") or "postgresql://postgres:postgres@127.0.0.1:5432/langchain_app")
    name = "quality_" + uuid4().hex

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
            for _ in range(2):
                subprocess.run([str(binary), "-path", str(ROOT / "server/migrations"), "up"], env=environment, check=True)
            return subprocess.run([
                sys.executable, "-m", "pytest", "-q", "--tb=short",
                "tests/integration/test_conversation_postgres.py",
                "tests/integration/test_execution_postgres.py",
                "tests/integration/test_document_job_state.py",
            ], cwd=ROOT, env=environment).returncode
    finally:
        # 名称仅由本函数生成，只删除刚创建的隔离库，不接受外部传入数据库名。
        sql(f"DROP DATABASE {name};")


if __name__ == "__main__":
    raise SystemExit(main())
