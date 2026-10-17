"""仅在调用方创建的隔离 PostgreSQL 库运行，不使用开发业务库。"""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from backend.core.models import ChatMessage, ChatSession, User
from backend.services import conversation_storage


def test_fresh_go_migrated_database_starts_python_without_legacy_ddl(monkeypatch, isolated_pg_factory):
    from backend.core import database

    engine = isolated_pg_factory.kw["bind"]
    monkeypatch.setattr(database, "engine", engine)
    with engine.connect() as connection:
        before = connection.execute(text("SELECT version_num FROM alembic_version")).all()
    database.init_db()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).all() == before == []


@pytest.fixture
def storage_db(monkeypatch, isolated_pg_factory):
    factory = isolated_pg_factory
    monkeypatch.setattr(conversation_storage, "SessionLocal", factory)
    username = "refactor_" + uuid4().hex[:16]
    with factory.begin() as db:
        user = User(username=username, password_hash="unusable-test-hash", role="user")
        db.add(user)
        db.flush()
        user_id = user.id
    try:
        yield conversation_storage.ConversationStorage(), factory, username, user_id
    finally:
        with factory.begin() as db:
            db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


def test_concurrent_turns_preserve_every_message_and_old_citation(storage_db):
    storage, _, username, _ = storage_db
    trace = {"tool_used": True, "tool_name": "search_knowledge_base", "source_map": {"Source 1": {"chunk_id": "original"}}}
    storage.append_turn(username, "same-session", "old-question", "old-answer", trace)
    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [workers.submit(storage.append_turn, username, "same-session", f"q-{i}", f"a-{i}") for i in range(10)]
        for future in futures:
            future.result()
    messages = storage.get_session_messages(username, "same-session")
    assert len(messages) == 22
    assert messages[1]["rag_trace"] == trace
    for i in range(2, 22, 2):
        assert messages[i]["type"] == "human"
        assert messages[i + 1]["type"] == "ai"
        assert messages[i]["content"][2:] == messages[i + 1]["content"][2:]
    assert storage.list_session_infos(username)[0]["message_count"] == 22


def test_external_delete_is_visible_on_next_read_and_user_isolation_holds(storage_db):
    storage, factory, username, user_id = storage_db
    storage.append_turn(username, "same-session", "question", "answer")
    assert len(storage.load(username, "same-session")) == 2
    assert storage.get_session_messages("someone-else", "same-session") == []
    assert storage.delete_session("someone-else", "same-session") is False
    # 与 Go DeleteSessionForUser 相同的主键范围，绕过 Python 模拟另一个写入方。
    with factory.begin() as db:
        db.execute(text("DELETE FROM chat_sessions WHERE user_id = :uid AND session_id = :sid"), {"uid": user_id, "sid": "same-session"})
    assert storage.load(username, "same-session") == []
    assert storage.list_session_infos(username) == []


def test_failed_turn_rolls_back_both_messages_and_preserves_existing_history(storage_db):
    from sqlalchemy.exc import IntegrityError

    storage, factory, username, _ = storage_db
    storage.append_turn(username, "session", "old", "answer")
    with pytest.raises(IntegrityError):
        storage.append_turn(username, "session", "new", None)
    assert [row["content"] for row in storage.get_session_messages(username, "session")] == ["old", "answer"]
    with factory() as db:
        assert len(db.execute(select(ChatSession)).scalars().all()) >= 1
        assert len(db.execute(select(ChatMessage)).scalars().all()) >= 2


def test_parent_chunks_never_publish_rolled_back_or_deleted_content(monkeypatch, isolated_pg_factory):
    from backend.rag import parent_chunk_store

    monkeypatch.setattr(parent_chunk_store, "SessionLocal", isolated_pg_factory)
    store = parent_chunk_store.ParentChunkStore()
    key = "quality_" + uuid4().hex
    filename = key + ".pdf"
    original = {"chunk_id": key, "text": "committed", "filename": filename}
    try:
        store.upsert_documents([original])
        # A second row fails after the first UPDATE; the entire transaction must roll back.
        with pytest.raises(ValueError, match="chunk_id"):
            store.upsert_documents([{**original, "text": "uncommitted"}, {"text": "invalid"}])
        other_process = parent_chunk_store.ParentChunkStore()
        assert [row["text"] for row in other_process.get_documents_by_ids([key, key])] == ["committed", "committed"]
        with isolated_pg_factory.begin() as db:
            db.execute(text("DELETE FROM parent_chunks WHERE chunk_id = :key"), {"key": key})
        assert store.get_documents_by_ids([key]) == []
    finally:
        store.delete_by_filename(filename)


def test_concurrent_parent_upsert_has_no_select_insert_race(monkeypatch, isolated_pg_factory):
    from backend.rag import parent_chunk_store

    monkeypatch.setattr(parent_chunk_store, "SessionLocal", isolated_pg_factory)
    store = parent_chunk_store.ParentChunkStore()
    key = "quality_" + uuid4().hex
    filename = key + ".pdf"
    try:
        with ThreadPoolExecutor(max_workers=4) as workers:
            futures = [workers.submit(store.upsert_documents, [{"chunk_id": key, "filename": filename, "text": str(i)}]) for i in range(8)]
            assert [future.result() for future in futures] == [1] * 8
        assert len(store.get_documents_by_ids([key])) == 1
    finally:
        store.delete_by_filename(filename)


def test_index_migration_preserves_rows_and_recovers_after_duplicate_failure(isolated_pg_factory):
    import os
    import subprocess
    from pathlib import Path

    binary = os.getenv("REFACTOR_MIGRATE_BINARY")
    if not binary:
        pytest.skip("需要隔离验证器提供真实迁移执行器")
    root = Path(__file__).resolve().parents[2]
    environment = {**os.environ, "DATABASE_URL": os.environ["REFACTOR_TEST_DATABASE_URL"].replace("postgresql+psycopg2:", "postgresql:")}

    def migrate(*arguments, check=True):
        return subprocess.run([binary, "-path", str(root / "server/migrations"), *arguments], env=environment, check=check, capture_output=True)

    engine = isolated_pg_factory.kw["bind"]
    username = "migration_" + uuid4().hex
    with engine.begin() as connection:
        uid = connection.execute(text("INSERT INTO users (username, password_hash) VALUES (:name, 'test-only') RETURNING id"), {"name": username}).scalar_one()
        wid = connection.execute(text("INSERT INTO workspaces (name, owner_id) VALUES ('quality migration', :uid) RETURNING id"), {"uid": uid}).scalar_one()
    try:
        migrate("down", "2")
        with engine.begin() as connection:
            ids = [connection.execute(text("INSERT INTO workspace_members (workspace_id, user_id) VALUES (:wid, :uid) RETURNING id"), {"wid": wid, "uid": uid}).scalar_one() for _ in range(2)]
        failed = migrate("up", check=False)
        assert failed.returncode != 0
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM workspace_members WHERE workspace_id=:wid"), {"wid": wid}).scalar_one() == 2
            assert connection.execute(text("SELECT to_regclass('public.ix_users_id')")).scalar_one() is not None
            assert connection.execute(text("SELECT to_regclass('public.uq_workspace_member')")).scalar_one() is None
        # Only remove the duplicate created by this test after confirming DDL rollback.
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM workspace_members WHERE id=:id"), {"id": ids[1]})
        migrate("force", "3")
        migrate("up")
        migrate("up")
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql((root / "server/migrations/000004_index_constraints.up.sql").read_text(encoding="utf-8"))
            assert connection.execute(text("SELECT to_regclass('public.ix_users_id')")).scalar_one() is None
            assert connection.execute(text("SELECT count(*) FROM workspace_members WHERE workspace_id=:wid"), {"wid": wid}).scalar_one() == 1
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM workspaces WHERE id=:id"), {"id": wid})
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": uid})


def test_structural_pdf_parent_is_persisted_and_can_actually_merge(monkeypatch, isolated_pg_factory):
    from backend.rag import parent_chunk_store, rag_utils
    from backend.rag.document_loader import DocumentLoader

    monkeypatch.setattr(parent_chunk_store, "SessionLocal", isolated_pg_factory)
    store = parent_chunk_store.ParentChunkStore()
    monkeypatch.setattr(rag_utils, "get_parent_chunk_store", lambda: store)
    filename = "quality_" + uuid4().hex + ".pdf"
    content = "# Method\n\n" + "A relevant theorem with proof and research context. " * 120
    docs = DocumentLoader()._split_structural(content, filename)
    parents = [doc for doc in docs if doc["chunk_level"] in (1, 2)]
    leaves = [doc for doc in docs if doc["chunk_level"] == 3]
    assert len(parents) == 1 and len(leaves) >= 2
    assert {leaf["parent_chunk_id"] for leaf in leaves} == {parents[0]["chunk_id"]}
    try:
        store.upsert_documents(parents)
        merged, count = rag_utils._merge_to_parent_level([{**leaf, "score": 0.9} for leaf in leaves], threshold=2)
        assert count > 0
        assert len(merged) == 1
        assert merged[0]["text"] == parents[0]["text"]
    finally:
        store.delete_by_filename(filename)


def test_runtime_roles_allow_current_paths_and_reject_ddl_or_other_domain_writes(monkeypatch, isolated_pg_factory):
    import secrets
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.exc import ProgrammingError
    from sqlalchemy.orm import sessionmaker

    from backend.internal_api.postgres_executions import PostgresExecutionStore
    from backend.internal_api.schemas import ExecuteRequest
    from backend.rag import parent_chunk_store
    from scripts.configure_database_roles import configure_roles

    administrator = isolated_pg_factory.kw["bind"]
    prefix = "quality_" + uuid4().hex
    credentials = {app: (prefix + "_" + app, secrets.token_urlsafe(32)) for app in ("go", "python")}
    engines = {}
    username, filename = prefix + "_user", prefix + ".pdf"
    try:
        for _ in range(2):
            configure_roles(administrator.url.render_as_string(hide_password=False), credentials)
        for app, (role, password) in credentials.items():
            engines[app] = create_engine(administrator.url.set(username=role, password=password))
            with engines[app].connect() as connection:
                assert connection.execute(text("SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls FROM pg_roles WHERE rolname=current_user")).one() == (False,) * 4
                with pytest.raises(ProgrammingError):
                    connection.execute(text(f"CREATE TABLE public.{prefix}_forbidden (id integer)"))
            forbidden = "parent_chunks" if app == "go" else "user_preferences"
            with engines[app].connect() as connection, pytest.raises(ProgrammingError):
                connection.execute(text(f"DELETE FROM {forbidden} WHERE false"))
        with engines["go"].begin() as connection:
            connection.execute(text("INSERT INTO users (username, password_hash) VALUES (:name, 'test-only')"), {"name": username})
        factory = sessionmaker(engines["python"])
        monkeypatch.setattr(conversation_storage, "SessionLocal", factory)
        storage = conversation_storage.ConversationStorage()
        storage.append_turn(username, "roles", "question", "answer")
        assert len(storage.get_session_messages(username, "roles")) == 2
        monkeypatch.setattr(parent_chunk_store, "SessionLocal", factory)
        parents = parent_chunk_store.ParentChunkStore()
        assert parents.upsert_documents([{"chunk_id": prefix, "filename": filename, "text": "full parent"}]) == 1
        assert parents.get_documents_by_ids([prefix])[0]["text"] == "full parent"
        executions = PostgresExecutionStore(factory)
        req = ExecuteRequest(
            task_id=prefix, task_type="PARSE_PAPER", idempotency_key=f"{prefix}:PARSE_PAPER:{prefix}",
            deadline=datetime.now(UTC) + timedelta(minutes=2), payload={"filename": filename},
        )
        row, _ = executions.submit(req)
        assert executions.cancel(row.execution_id).status == "cancelled"
    finally:
        for engine in engines.values():
            engine.dispose()
        with administrator.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE username=:name"), {"name": username})
            connection.execute(text("DELETE FROM parent_chunks WHERE filename=:name"), {"name": filename})
            connection.execute(text("DELETE FROM ai_executions WHERE task_id=:id"), {"id": prefix})
            for role, _ in credentials.values():
                if connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname=:name"), {"name": role}).scalar():
                    # 名称只由本测试 UUID 构造，清理其授权；角色不拥有任何业务对象。
                    connection.exec_driver_sql(f"DROP OWNED BY {role}")
                    connection.exec_driver_sql(f"DROP ROLE {role}")
