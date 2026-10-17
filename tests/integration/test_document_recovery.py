"""真实 PG/Redis/Milvus 的进程中断恢复；仅隔离外部模型权重，不替换索引核心。"""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import fitz
import pytest
import redis

from backend.core.exceptions import RetrievalError
from backend.rag import parent_chunk_store
from backend.rag.document_loader import DocumentLoader
from backend.rag.embedding import EmbeddingService
from backend.services import document_jobs
from backend.services.upload_jobs import RedisJobManager, UploadJobManager
from backend.vectordb.milvus_client import MilvusManager
from backend.vectordb.milvus_writer import MilvusWriter

ROOT = Path(__file__).resolve().parents[2]


def _pdf(path, version):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_textbox(fitz.Rect(40, 40, 550, 780), (f"ResearchPilot {version} recovery source with substantive document content. " * 25), fontsize=10)
        document.save(path)


@pytest.fixture
def storage(tmp_path, monkeypatch, isolated_pg_factory):
    uri = os.getenv("REFACTOR_TEST_MILVUS_URI")
    redis_url = os.getenv("REFACTOR_TEST_REDIS_URL")
    if not uri or not redis_url:
        pytest.skip("需要显式隔离 Milvus URI 和 Redis 验证进程恢复")
    if urlsplit(uri).hostname not in {"127.0.0.1", "localhost"}:
        pytest.fail("只允许本机隔离 Milvus 验证")
    name = "quality_" + uuid4().hex
    state = {"name": name, "root": tmp_path, "filename": name + ".pdf"}
    monkeypatch.setattr(document_jobs, "SessionLocal", isolated_pg_factory)
    monkeypatch.setattr(parent_chunk_store, "SessionLocal", isolated_pg_factory)
    monkeypatch.setattr(document_jobs, "_INGESTED_PATH", tmp_path / "ingested.json")
    monkeypatch.setattr(document_jobs, "get_document_loader", DocumentLoader)
    monkeypatch.setattr(document_jobs, "get_parent_chunk_store", parent_chunk_store.ParentChunkStore)
    monkeypatch.setattr(document_jobs, "get_milvus_manager", lambda: state["manager"])
    monkeypatch.setattr(document_jobs, "get_embedding_service", lambda: state["embedding"])
    monkeypatch.setattr(document_jobs, "get_milvus_writer", lambda: MilvusWriter(state["embedding"], state["manager"]))
    monkeypatch.setattr(document_jobs, "delete_job_manager", UploadJobManager())

    def restart():
        if state.get("manager") and state["manager"].client:
            state["manager"].client.close()
        manager = MilvusManager()
        manager.uri, manager.collection_name = uri, name
        manager.init_collection(dense_dim=2)
        embedding = EmbeddingService(state_path=tmp_path / "bm25.json")
        embedding._embedder = SimpleNamespace(embed_documents=lambda texts: [[0.1, 0.2] for _ in texts])
        jobs = RedisJobManager()
        jobs._prefix = name + ":jobs:"
        jobs._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        if state.get("jobs"):
            state["jobs"]._redis.close()
        state.update(manager=manager, embedding=embedding, jobs=jobs)
        monkeypatch.setattr(document_jobs, "upload_job_manager", jobs)

    state["restart"] = restart
    restart()
    try:
        yield state
    finally:
        parent_chunk_store.ParentChunkStore().delete_by_filename(state["filename"])
        state["manager"]._get_client().drop_collection(name)
        state["manager"].client.close()
        client = state["jobs"]._redis
        keys = list(client.scan_iter(match=name + ":jobs:*"))
        if keys:
            client.delete(*keys)
        client.close()


@pytest.mark.parametrize("failure_point", ["after_delete", "after_insert", "after_publish"])
def test_process_crash_restores_index_and_durable_job_without_duplicate_vectors(storage, failure_point):
    folder, filename = storage["root"], storage["filename"]
    original, pending = folder / filename, folder / "pending.pdf"
    _pdf(original, "old-version")
    document_jobs.index_document(str(original), filename)
    _pdf(pending, "new-version")
    context = {"operation": "upload", "source": str(pending), "destination": str(original), "hash": document_jobs._compute_file_hash(pending)}
    job = storage["jobs"].create_job(filename, context=context)
    child = folder / "crash.py"
    child.write_text('''
import os, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.rag import parent_chunk_store
from backend.rag.document_loader import DocumentLoader
from backend.rag.embedding import EmbeddingService
from backend.services import document_jobs
from backend.services.upload_jobs import RedisJobManager
from backend.vectordb.milvus_client import MilvusManager
from backend.vectordb.milvus_writer import MilvusWriter
import redis

root, name, uri, job_id, point = sys.argv[1:]
factory = sessionmaker(create_engine(os.environ["REFACTOR_TEST_DATABASE_URL"]))
document_jobs.SessionLocal = parent_chunk_store.SessionLocal = factory
document_jobs._INGESTED_PATH = Path(root) / "ingested.json"
manager = MilvusManager()
manager.uri, manager.collection_name = uri, name
with patch("backend.rag.embedding._create_dense_embedder", return_value=SimpleNamespace(embed_documents=lambda texts: [[0.1, 0.2] for _ in texts])):
    embedding = EmbeddingService(state_path=Path(root) / "bm25.json")
jobs = RedisJobManager()
jobs._prefix = name + ":jobs:"
jobs._redis = redis.Redis.from_url(os.environ["REFACTOR_TEST_REDIS_URL"], decode_responses=True)
document_jobs.upload_job_manager = jobs
document_jobs.get_document_loader = DocumentLoader
document_jobs.get_parent_chunk_store = parent_chunk_store.ParentChunkStore
document_jobs.get_milvus_manager = lambda: manager
document_jobs.get_embedding_service = lambda: embedding
document_jobs.get_milvus_writer = lambda: MilvusWriter(embedding, manager)
if point == "after_insert":
    insert = manager.insert
    def crash_insert(batch):
        insert(batch)
        os._exit(17)
    manager.insert = crash_insert
elif point == "after_delete":
    remove = document_jobs._remove_existing_index
    def crash_delete(filename):
        remove(filename)
        os._exit(17)
    document_jobs._remove_existing_index = crash_delete
else:
    update = document_jobs._update_ingested_record
    def crash_publish(filename, record):
        if record is not None and "pending" not in record:
            os._exit(17)
        return update(filename, record)
    document_jobs._update_ingested_record = crash_publish
job = jobs.get_job(job_id)
document_jobs._process_upload_job(job_id, job["context"]["source"], job["filename"])
raise RuntimeError("故障点未执行")
''', encoding="utf-8")
    environment = {**os.environ, "PYTHONPATH": str(ROOT)}
    result = subprocess.run([sys.executable, str(child), str(folder), storage["name"], storage["manager"].uri, job["job_id"], failure_point],
                            cwd=ROOT, env=environment, capture_output=True, timeout=120)
    assert result.returncode == 17, result.stderr.decode("utf-8", errors="replace")[-2000:]
    assert "pending" in document_jobs._load_ingested_state()[filename]
    with pytest.raises(RetrievalError, match="未完成"):
        with document_jobs.read_document_index():
            pytest.fail("不得读取部分索引")
    storage["restart"]()
    assert document_jobs.recover_pending_documents() == 1
    assert document_jobs.recover_document_jobs() == 1
    assert document_jobs.recover_pending_documents() == document_jobs.recover_document_jobs() == 0
    assert storage["jobs"].get_job(job["job_id"])["status"] == "completed"
    rows = storage["manager"].query_all(filter_expr=document_jobs._safe_milvus_filter(filename), output_fields=["text", "chunk_id", "parent_chunk_id"])
    assert rows and len(rows) == len({row["chunk_id"] for row in rows})
    assert all("new-version" in row["text"] for row in rows)
    assert storage["embedding"]._total_docs == len(rows)
    parent_ids = list({row["parent_chunk_id"] for row in rows})
    assert len(parent_chunk_store.ParentChunkStore().get_documents_by_ids(parent_ids)) == len(parent_ids)
    assert "pending" not in document_jobs._load_ingested_state()[filename]


def test_another_live_process_job_lock_prevents_recovery_stealing_work(storage):
    source = storage["root"] / "pending.pdf"
    _pdf(source, "new-version")
    context = {"operation": "upload", "source": str(source), "destination": str(storage["root"] / storage["filename"]), "hash": document_jobs._compute_file_hash(source)}
    job = storage["jobs"].create_job(storage["filename"], context=context)
    with document_jobs._write_lock("document-job:" + job["job_id"]):
        assert document_jobs.recover_document_jobs() == 0
        assert storage["jobs"].get_job(job["job_id"])["status"] == "pending"
    assert document_jobs.recover_document_jobs() == 1
    assert storage["jobs"].get_job(job["job_id"])["status"] == "completed"
