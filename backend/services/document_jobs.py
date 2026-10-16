"""文档变更的唯一执行路径：先解析校验，再替换索引，成功后更新摄入指纹。"""

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy import text

from backend.core.config import DOCUMENT_LOCK_TIMEOUT_SECONDS, INGESTED_STATE_PATH, UPLOAD_DIR
from backend.core.database import SessionLocal
from backend.core.dependencies import get_document_loader, get_embedding_service, get_milvus_manager, get_milvus_writer, get_parent_chunk_store
from backend.core.logging_config import get_logger
from backend.services.upload_jobs import delete_job_manager, upload_job_manager

logger = get_logger(__name__)
_INGESTED_PATH = INGESTED_STATE_PATH


@contextmanager
def _write_lock(resource: str):
    # PostgreSQL 事务锁覆盖多个 Python 进程，断连/异常时由数据库释放，不留下锁文件。
    key = int.from_bytes(hashlib.blake2b(resource.encode(), digest_size=8).digest(), signed=True)
    if DOCUMENT_LOCK_TIMEOUT_SECONDS <= 0:
        raise ValueError("文档锁超时必须为正数")
    with SessionLocal() as db, db.begin():
        db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": f"{DOCUMENT_LOCK_TIMEOUT_SECONDS}s"})
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        yield


def _load_ingested_state() -> dict:
    if not _INGESTED_PATH.exists():
        return {}
    state = json.loads(_INGESTED_PATH.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or any(not isinstance(row, dict) or not {"hash", "path"} <= row.keys() for row in state.values()):
        raise ValueError("摄入状态损坏，拒绝据此决定删除或跳过文件")
    return state


def _update_ingested_record(filename: str, record: dict | None) -> None:
    with _write_lock("ingested-state:" + str(_INGESTED_PATH.resolve())):
        state = _load_ingested_state()
        if record is None:
            state.pop(filename, None)
        else:
            state[filename] = record
        _INGESTED_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=_INGESTED_PATH.parent, delete=False) as file:
                temporary = Path(file.name)
                json.dump(state, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, _INGESTED_PATH)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _compute_file_hash(file_path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with file_path.open("rb") as file:
        while chunk := file.read(8192):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_milvus_filter(filename: str) -> str:
    return f"filename == {json.dumps(filename, ensure_ascii=False)}"


def _remove_existing_index(filename: str) -> int:
    manager = get_milvus_manager()
    expression = _safe_milvus_filter(filename)
    rows = manager.query_all(filter_expr=expression, output_fields=["text"])
    result = manager.delete(expression)
    get_parent_chunk_store().delete_by_filename(filename)
    # 删除失败时不先扣词频；BM25 始终按实际移除的旧文本更新。
    get_embedding_service().increment_remove_documents([row.get("text") or "" for row in rows])
    return result.get("delete_count", 0) if isinstance(result, dict) else 0


def index_document(file_path: str, filename: str, *, destination: Path | None = None, on_step=None, expected_hash: str | None = None) -> dict:
    def step(key, message):
        if on_step is not None:
            on_step(key, message)

    with _write_lock("document:" + filename):
        step("parse", "正在解析文档")
        source = Path(file_path)
        before = _compute_file_hash(source)
        if expected_hash is not None and before != expected_hash:
            raise ValueError("扫描后文件已改变，请重新提交摄入")
        try:
            docs = get_document_loader().load_document(str(source), filename)
        except Exception as exc:
            raise ValueError("文档解析失败，保留旧索引") from exc
        parents = [row for row in docs if int(row.get("chunk_level", 0) or 0) in (1, 2)]
        leaves = [row for row in docs if int(row.get("chunk_level", 0) or 0) == 3]
        if not leaves:
            raise ValueError("未生成可检索叶子分块，保留旧索引")
        if _compute_file_hash(source) != before:
            raise ValueError("解析期间文件已改变，保留旧索引")
        final_path = destination or source
        for row in docs:
            row["file_path"] = str(final_path.resolve())
        step("cleanup", "正在替换旧索引")
        get_milvus_manager().init_collection()
        _remove_existing_index(filename)
        step("parent_store", "正在写入父级分块")
        get_parent_chunk_store().upsert_documents(parents)
        step("vector_store", "正在写入向量")
        get_milvus_writer().write_documents(leaves)
        if destination is not None:
            os.replace(source, destination)
        _update_ingested_record(filename, {"hash": before, "path": str(final_path.resolve())})
        return {"leaf_count": len(leaves), "parent_count": len(parents)}


def remove_document(filename: str) -> int:
    with _write_lock("document:" + filename):
        get_milvus_manager().init_collection()
        count = _remove_existing_index(filename)
        _update_ingested_record(filename, None)
        return count


def _process_upload_job(job_id: str, file_path: str, filename: str) -> None:
    failed_step = "parse"

    def on_step(key, message):
        nonlocal failed_step
        failed_step = key
        upload_job_manager.update_step(job_id, key, 0, "running", message)

    try:
        upload_job_manager.complete_step(job_id, "upload", "文件已保存到暂存目录")
        result = index_document(file_path, filename, destination=UPLOAD_DIR / filename, on_step=on_step)
        for key in ("parse", "cleanup", "parent_store", "vector_store"):
            upload_job_manager.complete_step(job_id, key, "已完成")
        upload_job_manager.complete_job(job_id, f"处理完成：{result['leaf_count']} 个叶子分块")
    except Exception:
        logger.exception("上传失败: job_id=%s, filename=%s, step=%s", job_id, filename, failed_step)
        upload_job_manager.fail_job(job_id, failed_step, f"文档处理失败（步骤：{failed_step}）")


def _process_delete_job(job_id: str, filename: str) -> None:
    try:
        delete_job_manager.update_step(job_id, "prepare", 0, "running", "正在删除文档索引")
        count = remove_document(filename)
        for key in ("prepare", "bm25", "milvus", "parent_store"):
            delete_job_manager.complete_step(job_id, key, "已完成")
        delete_job_manager.complete_job(job_id, f"已删除 {count} 条向量，本地原文保留")
    except Exception:
        logger.exception("删除失败: job_id=%s, filename=%s", job_id, filename)
        delete_job_manager.fail_job(job_id, "prepare", "文档删除失败，请查看服务日志")


def _process_ingest_job(job_id: str, to_process: list[tuple[Path, str]], to_delete: list[str], current_state: dict) -> None:
    failed_step = "scan"

    def on_step(key, message):
        nonlocal failed_step
        failed_step = "bm25" if key == "cleanup" else key
        upload_job_manager.update_step(job_id, failed_step, 0, "running", message)

    try:
        for name in to_delete:
            remove_document(name)
        upload_job_manager.complete_step(job_id, "scan", "扫描清理完成")
        for file_path, _ in to_process:
            index_document(str(file_path), file_path.name, on_step=on_step, expected_hash=current_state[file_path.name]["hash"])
        for key in ("parse", "parent_store", "vector_store", "bm25"):
            upload_job_manager.complete_step(job_id, key, "已完成或无数据需处理")
        upload_job_manager.complete_job(job_id, f"批量导入完成：{len(to_process)} 个文件")
    except Exception:
        logger.exception("导入失败: job_id=%s, step=%s", job_id, failed_step)
        upload_job_manager.fail_job(job_id, failed_step, f"批量导入失败（步骤：{failed_step}），成功文件的指纹已保留")
