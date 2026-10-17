"""文档变更的唯一执行路径：先解析校验，再替换索引，成功后更新摄入指纹。"""

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from backend.core.config import DOCUMENT_LOCK_TIMEOUT_SECONDS, INGESTED_STATE_PATH, UPLOAD_DIR
from backend.core.database import SessionLocal, advisory_lock
from backend.core.dependencies import get_document_loader, get_embedding_service, get_milvus_manager, get_milvus_writer, get_parent_chunk_store
from backend.core.logging_config import get_logger
from backend.services.upload_jobs import TERMINAL, delete_job_manager, upload_job_manager

logger = get_logger(__name__)
_INGESTED_PATH = INGESTED_STATE_PATH


def validate_document_filename(filename: str) -> str:
    """所有入口共用文件名规则，兼容 Windows 与 POSIX，不接受路径或设备名。"""
    if not filename or not filename.strip():
        raise ValueError("filename must not be empty")
    if filename != filename.strip() or Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError("filename must not contain path segments")
    if any(char in filename for char in '/\\:<>"|?*') or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in filename):
        raise ValueError("filename contains invalid characters")
    if filename.endswith(".") or len(filename.encode("utf-8")) > 255:
        raise ValueError("filename is too long or ends in a dot")
    stem = filename.split(".", 1)[0].rstrip().upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or (stem[:3] in {"COM", "LPT"} and stem[3:] in "123456789¹²³" and len(stem) == 4):
        raise ValueError("filename must not be a reserved device name")
    return filename


def _write_lock(resource: str, *, shared: bool = False, blocking: bool = True):
    return advisory_lock(resource, session_factory=SessionLocal, shared=shared, blocking=blocking, timeout_seconds=DOCUMENT_LOCK_TIMEOUT_SECONDS)


def _load_ingested_state() -> dict:
    if not _INGESTED_PATH.exists():
        return {}
    state = json.loads(_INGESTED_PATH.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or any(not isinstance(row, dict) or not {"hash", "path"} <= row.keys() for row in state.values()):
        raise ValueError("摄入状态损坏，拒绝据此决定删除或跳过文件")
    for record in state.values():
        if "pending" not in record:
            continue
        pending = record["pending"]
        if not isinstance(pending, dict) or pending.get("operation") not in {"index", "delete"}:
            raise ValueError("索引恢复状态损坏，拒绝继续写入")
        if pending["operation"] == "index" and any(not isinstance(pending.get(key), str) or not pending[key] for key in ("source", "destination", "hash")):
            raise ValueError("索引恢复缺少原文或指纹，拒绝继续写入")
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
    digest = hashlib.sha256()
    with file_path.open("rb") as file:
        while chunk := file.read(8192):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_milvus_filter(filename: str) -> str:
    return f"filename == {json.dumps(filename, ensure_ascii=False)}"


def _remove_existing_index(filename: str) -> int:
    manager = get_milvus_manager()
    expression = _safe_milvus_filter(filename)
    result = manager.delete(expression)
    get_parent_chunk_store().delete_by_filename(filename)
    # 保留词表维度，按实际存留的叶子重建统计，修复不确定写入结果造成的漂移。
    surviving = manager.query_all(filter_expr="chunk_level == 3", output_fields=["text"])
    get_embedding_service().replace_documents([row.get("text") or "" for row in surviving])
    return result.get("delete_count", 0) if isinstance(result, dict) else 0


@contextmanager
def read_document_index():
    """只读取一次完整替换后的索引；失败的操作必须先恢复。"""
    from backend.core.exceptions import RetrievalError

    with _write_lock("document-index", shared=True):
        if any(row.get("pending") for row in _load_ingested_state().values()):
            raise RetrievalError("文档索引存在未完成操作，请重试处理或重启服务恢复")
        yield


def _mark_pending(filename: str, operation: dict) -> None:
    previous = _load_ingested_state().get(filename, {"hash": "", "path": operation.get("destination", "")})
    _update_ingested_record(filename, {**previous, "pending": operation})


def _index_document_locked(file_path: str, filename: str, *, destination: Path | None = None, on_step=None, expected_hash: str | None = None) -> dict:
    def step(key, message):
        if on_step is not None:
            on_step(key, message)

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
    get_milvus_manager().init_collection()
    # 在任何旧数据删除之前，先原子落盘可重放的操作意图。
    _mark_pending(filename, {"operation": "index", "source": str(source.resolve()), "destination": str(final_path.resolve()), "hash": before})
    step("cleanup", "正在替换旧索引")
    _remove_existing_index(filename)
    step("parent_store", "正在写入父级分块")
    get_parent_chunk_store().upsert_documents(parents)
    step("vector_store", "正在写入向量")
    get_milvus_writer().write_documents(leaves)
    if destination is not None:
        os.replace(source, destination)
    _update_ingested_record(filename, {"hash": before, "path": str(final_path.resolve())})
    return {"leaf_count": len(leaves), "parent_count": len(parents)}


def index_document(file_path: str, filename: str, *, destination: Path | None = None, on_step=None, expected_hash: str | None = None) -> dict:
    filename = validate_document_filename(filename)
    with _write_lock("document-index"):
        return _index_document_locked(file_path, filename, destination=destination, on_step=on_step, expected_hash=expected_hash)


def _remove_document_locked(filename: str) -> int:
    get_milvus_manager().init_collection()
    _mark_pending(filename, {"operation": "delete"})
    count = _remove_existing_index(filename)
    _update_ingested_record(filename, None)
    return count


def remove_document(filename: str) -> int:
    filename = validate_document_filename(filename)
    with _write_lock("document-index"):
        return _remove_document_locked(filename)


def recover_pending_documents() -> int:
    """启动时修复局部索引操作；没有 pending 时不加载模型或连接 Milvus。"""
    if not any(row.get("pending") for row in _load_ingested_state().values()):
        return 0
    recovered = 0
    with _write_lock("document-index"):
        # 获锁后重新读，不能重放另一个进程已经完成或替换的操作。
        for filename, row in _load_ingested_state().items():
            pending = row.get("pending")
            if not pending:
                continue
            validate_document_filename(filename)
            if pending.get("operation") == "delete":
                _remove_document_locked(filename)
            elif pending.get("operation") == "index":
                source, destination = Path(pending["source"]), Path(pending["destination"])
                if not source.is_file():
                    source = destination
                if not source.is_file() or _compute_file_hash(source) != pending["hash"]:
                    raise RuntimeError("待恢复索引的原文缺失或已改变，保留 pending 标记，拒绝启动")
                _index_document_locked(str(source), filename, destination=destination if source != destination else None, expected_hash=pending["hash"])
            else:
                raise ValueError("未知的索引恢复操作，拒绝修改数据")
            recovered += 1
    return recovered


def _process_upload_job(job_id: str, file_path: str, filename: str) -> None:
    with _write_lock("document-job:" + job_id, blocking=False) as acquired:
        if not acquired:
            return
        job = upload_job_manager.get_job(job_id)
        if job is None or job["status"] in TERMINAL:
            return
        failed_step = "parse"

        def on_step(key, message):
            nonlocal failed_step
            failed_step = key
            upload_job_manager.update_step(job_id, key, 0, "running", message)

        try:
            upload_job_manager.complete_step(job_id, "upload", "文件已保存到暂存目录")
            context = job.get("context") or {}
            source = Path(file_path)
            destination = Path(context.get("destination") or UPLOAD_DIR / filename)
            expected_hash = context.get("hash")
            if not source.is_file() and expected_hash and destination.is_file() and _compute_file_hash(destination) == expected_hash:
                source = destination
            result = index_document(str(source), filename, destination=destination if source != destination else None, on_step=on_step, expected_hash=expected_hash)
            for key in ("parse", "cleanup", "parent_store", "vector_store"):
                upload_job_manager.complete_step(job_id, key, "已完成")
            upload_job_manager.complete_job(job_id, f"处理完成：{result['leaf_count']} 个叶子分块")
        except Exception:
            logger.exception("上传失败: job_id=%s, filename=%s, step=%s", job_id, filename, failed_step)
            upload_job_manager.fail_job(job_id, failed_step, f"文档处理失败（步骤：{failed_step}）")


def _process_delete_job(job_id: str, filename: str) -> None:
    with _write_lock("document-job:" + job_id, blocking=False) as acquired:
        if not acquired:
            return
        job = delete_job_manager.get_job(job_id)
        if job is None or job["status"] in TERMINAL:
            return
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
    with _write_lock("document-job:" + job_id, blocking=False) as acquired:
        if not acquired:
            return
        job = upload_job_manager.get_job(job_id)
        if job is None or job["status"] in TERMINAL:
            return
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


def recover_document_jobs() -> int:
    """只在启动时重放本执行面的未完成文档操作，不创建全局任务或周期调度。"""
    recovered = 0
    for manager in (upload_job_manager, delete_job_manager):
        for job in manager.list_jobs():
            if job["status"] in TERMINAL:
                continue
            context = job.get("context") or {}
            operation = context.get("operation")
            if operation == "upload":
                _process_upload_job(job["job_id"], context["source"], job["filename"])
            elif operation == "delete":
                _process_delete_job(job["job_id"], job["filename"])
            elif operation == "ingest":
                current = context["current"]
                files = [(Path(path), reason) for path, reason in context["files"]]
                _process_ingest_job(job["job_id"], files, context["deleted"], current)
            else:
                # 老记录没有重放输入，只能明确失败，不能伪造成功或猜测重试参数。
                manager.fail_job(job["job_id"], job["current_step"], "任务缺少可恢复输入，请重新提交")
                continue
            if (manager.get_job(job["job_id"]) or {}).get("status") in TERMINAL:
                recovered += 1
    return recovered
