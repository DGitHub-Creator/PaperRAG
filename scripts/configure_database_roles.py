"""显式配置当前 Go/Python 运行角色；迁移账号独立，权限仅覆盖实际调用。"""

import os
import re
from contextlib import closing

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url


PERMISSIONS = {
    "go": {
        "users": "SELECT, INSERT, UPDATE",
        "user_preferences": "SELECT, INSERT, UPDATE",
        "chat_sessions": "SELECT, DELETE",
        "chat_messages": "SELECT",
    },
    "python": {
        # 旧认证/聊天尚未由 Go 全部接管，保留当前真实写入，不能按目标 ACL 提前撤销。
        "users": "SELECT, INSERT, UPDATE",
        "chat_sessions": "SELECT, INSERT, UPDATE, DELETE",
        "chat_messages": "SELECT, INSERT, DELETE",
        "parent_chunks": "SELECT, INSERT, UPDATE, DELETE",
        "ai_executions": "SELECT, INSERT, UPDATE",
        "workspaces": "SELECT",
        "workspace_members": "SELECT",
        "schema_migrations": "SELECT",
    },
}
SEQUENCES = {"go": ("users_id_seq",), "python": ("users_id_seq", "chat_sessions_id_seq", "chat_messages_id_seq")}


def configure_roles(database_url: str, credentials: dict[str, tuple[str, str]]) -> None:
    """一笔事务创建/更新自有角色；拒绝接管已有外部角色，不修改业务数据或 PUBLIC 权限。"""
    if set(credentials) != set(PERMISSIONS) or len({name for name, _ in credentials.values()}) != 2:
        raise ValueError("必须提供两个不同的 Go/Python 运行角色")
    for name, password in credentials.values():
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name) or name.startswith("pg_"):
            raise ValueError("运行角色名必须为合法的小写 PostgreSQL 标识符")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", password) or password.startswith("replace-with-"):
            raise ValueError("运行角色密码须为至少 32 字符的 URL 安全随机值")
    url = make_url(database_url)
    # psycopg2 接收原生 URL，不接收 SQLAlchemy 方言后缀。
    dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    with closing(psycopg2.connect(dsn)) as connection, connection, connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), current_user")
        database, administrator = cursor.fetchone()
        cursor.execute("SELECT version, dirty FROM public.schema_migrations")
        if cursor.fetchone() != (5, False):
            raise ValueError("请先完成当前第 5 版数据库迁移再配置运行角色")
        marker = "ResearchPilot runtime role for database " + database
        for application, (name, password) in credentials.items():
            if name == administrator:
                raise ValueError("运行角色不得复用迁移管理员")
            cursor.execute("SELECT oid, shobj_description(oid, 'pg_authid') FROM pg_roles WHERE rolname = %s", (name,))
            existing = cursor.fetchone()
            if existing:
                if existing[1] != marker:
                    raise ValueError("同名角色不属于本数据库，拒绝修改其权限或密码")
                cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_auth_members WHERE member=%s OR roleid=%s)", (existing[0], existing[0]))
                if cursor.fetchone()[0]:
                    raise ValueError("运行角色存在额外成员关系，须先人工核查")
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_class WHERE relowner=%s "
                    "UNION ALL SELECT 1 FROM pg_namespace WHERE nspowner=%s "
                    "UNION ALL SELECT 1 FROM pg_database WHERE datdba=%s)",
                    (existing[0], existing[0], existing[0]),
                )
                if cursor.fetchone()[0]:
                    raise ValueError("运行角色拥有数据库对象，拒绝将对象所有者伪装成受限角色")
            else:
                cursor.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(name)))
            cursor.execute(sql.SQL("ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %s").format(sql.Identifier(name)), (password,))
            cursor.execute(sql.SQL("COMMENT ON ROLE {} IS %s").format(sql.Identifier(name)), (marker,))
            cursor.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", (name,))
            if cursor.fetchone()[0]:
                raise ValueError("运行角色仍可创建 public 对象，请先核查对象所有权与 PUBLIC 授权")
            cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), sql.Identifier(name)))
            cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(name)))
            cursor.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(sql.Identifier(name)))
            cursor.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}").format(sql.Identifier(name)))
            for table, privileges in PERMISSIONS[application].items():
                cursor.execute(sql.SQL("GRANT {} ON TABLE public.{} TO {}").format(sql.SQL(privileges), sql.Identifier(table), sql.Identifier(name)))
            for sequence in SEQUENCES[application]:
                cursor.execute(sql.SQL("GRANT USAGE ON SEQUENCE public.{} TO {}").format(sql.Identifier(sequence), sql.Identifier(name)))
            # PUBLIC 的间接授权不能被上面的 REVOKE 收回；若扩大了当前权限，整笔拒绝。
            cursor.execute(
                "SELECT c.relname, p.privilege FROM pg_class c "
                "CROSS JOIN (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'), "
                "('TRUNCATE'), ('REFERENCES'), ('TRIGGER')) AS p(privilege) "
                "WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p','v','m','f') "
                "AND has_table_privilege(%s, c.oid, p.privilege)", (name,),
            )
            for table, privilege in cursor.fetchall():
                if privilege not in PERMISSIONS[application].get(table, "").split(", "):
                    raise ValueError("运行角色仍有额外表权限，请先核查 PUBLIC 授权")


def main() -> int:
    try:
        configure_roles(os.environ["DATABASE_URL"], {
            "go": (os.getenv("GO_DB_USER", "researchpilot_go"), os.environ["GO_DB_PASSWORD"]),
            "python": (os.getenv("PYTHON_DB_USER", "researchpilot_python"), os.environ["PYTHON_DB_PASSWORD"]),
        })
    except (KeyError, ValueError, psycopg2.Error) as exc:
        # 驱动错误可能含连接串/SQL 中的凭据；只输出异常类型，不回显其原文。
        print(f"运行角色配置失败（{type(exc).__name__}）；核查管理员连接、迁移版本、角色归属和密码配置")
        return 1
    print("Go/Python 运行角色已按当前读写路径配置；业务数据未修改")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
