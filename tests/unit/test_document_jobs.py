from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.api.documents import _normalize_document_filename
from backend.services import document_jobs
from backend.vectordb.milvus_writer import MilvusWriter


@pytest.mark.parametrize("filename", ["../paper.pdf", "..\\paper.pdf", "file:stream.pdf", "paper\x00.pdf"])
def test_document_name_rejects_cross_platform_path_segments(filename):
    with pytest.raises(HTTPException) as caught:
        _normalize_document_filename(filename)
    assert caught.value.status_code == 400


def test_milvus_filename_is_a_json_string():
    import json

    filename = 'paper\\" or filename != "other.pdf'
    expression = document_jobs._safe_milvus_filter(filename)
    assert json.loads(expression.removeprefix("filename == ")) == filename


def test_failed_cleanup_marks_upload_failed(monkeypatch):
    jobs = MagicMock()
    monkeypatch.setattr(document_jobs, "upload_job_manager", jobs)

    def fail_index(*args, on_step, **kwargs):
        on_step("cleanup", "替换旧版本")
        raise RuntimeError("secret-dsn")

    monkeypatch.setattr(document_jobs, "index_document", fail_index)
    document_jobs._process_upload_job("job", "paper.pdf", "paper.pdf")
    jobs.fail_job.assert_called_once_with("job", "cleanup", "文档处理失败（步骤：cleanup）")
    jobs.complete_job.assert_not_called()


def test_vector_count_mismatch_does_not_silently_drop_documents():
    embeddings = MagicMock()
    embeddings.get_all_embeddings.return_value = ([[0.1]], [])
    manager = MagicMock()
    writer = MilvusWriter(embedding_service=embeddings, milvus_manager=manager)
    with pytest.raises(ValueError):
        writer.write_documents([{"text": "paper", "filename": "paper.pdf"}])
    manager.insert.assert_not_called()




@pytest.fixture
def document_io(tmp_path, monkeypatch):
    from contextlib import nullcontext
    monkeypatch.setattr(document_jobs, "_write_lock", lambda _: nullcontext())
    monkeypatch.setattr(document_jobs, "_INGESTED_PATH", tmp_path / "state.json")
    return tmp_path


def test_parse_failure_does_not_delete_previous_index(document_io, monkeypatch):
    path = document_io / "paper.pdf"
    path.write_bytes(b"original")
    loader = MagicMock()
    loader.load_document.return_value = []
    remove = MagicMock()
    monkeypatch.setattr(document_jobs, "get_document_loader", lambda: loader)
    monkeypatch.setattr(document_jobs, "_remove_existing_index", remove)
    with pytest.raises(ValueError, match="保留旧索引"):
        document_jobs.index_document(str(path), "paper.pdf")
    remove.assert_not_called()
    assert path.read_bytes() == b"original"
    assert document_jobs._load_ingested_state() == {}


def test_partial_ingest_records_only_successful_files(document_io, monkeypatch):
    from backend.services.upload_jobs import UploadJobManager, INGEST_STEPS
    jobs = UploadJobManager()
    job = jobs.create_job("batch", steps=INGEST_STEPS, current_step="scan", completion_step="bm25")
    monkeypatch.setattr(document_jobs, "upload_job_manager", jobs)
    def index(path, name, **kwargs):
        kwargs["on_step"]("parse", "解析")
        if name == "bad.pdf":
            raise RuntimeError("解析失败")
        document_jobs._update_ingested_record(name, {"hash": "good", "path": path})
    monkeypatch.setattr(document_jobs, "index_document", index)
    good, bad = document_io / "good.pdf", document_io / "bad.pdf"
    document_jobs._process_ingest_job(job["job_id"], [(good, "新增"), (bad, "新增")], [], {"good.pdf": {"hash": "good"}, "bad.pdf": {"hash": "bad"}})
    assert set(document_jobs._load_ingested_state()) == {"good.pdf"}
    assert jobs.get_job(job["job_id"])["status"] == "failed"


def test_failed_state_replace_preserves_original_file(document_io, monkeypatch):
    document_jobs._update_ingested_record("good.pdf", {"hash": "old", "path": "good.pdf"})
    monkeypatch.setattr(document_jobs.os, "replace", MagicMock(side_effect=OSError("磁盘错误")))
    with pytest.raises(OSError):
        document_jobs._update_ingested_record("good.pdf", {"hash": "new", "path": "good.pdf"})
    assert document_jobs._load_ingested_state()["good.pdf"]["hash"] == "old"
    assert list(document_io.iterdir()) == [document_io / "state.json"]


@pytest.mark.asyncio
async def test_actual_upload_size_is_checked_and_partial_file_is_removed(tmp_path, monkeypatch):
    from io import BytesIO
    from fastapi import UploadFile
    from backend.api import documents
    monkeypatch.setattr(documents, "MAX_UPLOAD_SIZE_MB", 1)
    target = tmp_path / "paper.pdf"
    target.write_bytes(b"old")
    upload = UploadFile(file=BytesIO(b"x" * (1024 * 1024 + 1)), size=1, filename="paper.pdf")
    with pytest.raises(HTTPException) as caught:
        await documents._save_upload_file(upload, target)
    assert caught.value.status_code == 413
    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]
