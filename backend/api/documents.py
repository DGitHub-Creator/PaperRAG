"""文档管理路由 —— 上传、删除、列表、增量导入端点。"""

import hashlib
import json
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from backend.core.auth import require_admin
from backend.core.config import DATA_DIR, INGESTED_STATE_PATH, MAX_UPLOAD_SIZE_MB, UPLOAD_DIR
from backend.core.dependencies import (
    get_embedding_service,
    get_milvus_manager,
    get_parent_chunk_store,
)
from backend.core.logging_config import get_logger
from backend.core.models import User
from backend.schemas.schemas import (
    DocumentDeleteJobResponse,
    DocumentDeleteResponse,
    DocumentDeleteStartResponse,
    DocumentInfo,
    DocumentListResponse,
    DocumentUploadJobResponse,
    DocumentUploadResponse,
    DocumentUploadStartResponse,
    IncrementalIngestRequest,
    IncrementalIngestResponse,
)
from backend.services.upload_jobs import (
    DELETE_STEPS,
    INGEST_STEPS,
    delete_job_manager,
    upload_job_manager,
)

logger = get_logger(__name__)

COMPUTED_DATA_DIR = DATA_DIR
COMPUTED_UPLOAD_DIR = UPLOAD_DIR

_loader = None


def _get_loader():
    global _loader
    if _loader is None:
        from backend.rag.document_loader import DocumentLoader
        _loader = DocumentLoader()
    return _loader


router = APIRouter()


def _get_milvus_writer():
    from backend.vectordb.milvus_writer import MilvusWriter
    return MilvusWriter(
        embedding_service=get_embedding_service(),
        milvus_manager=get_milvus_manager(),
    )


def _remove_bm25_stats_for_filename(filename: str) -> None:
    rows = get_milvus_manager().query_all(
        filter_expr=f'filename == "{filename}"',
        output_fields=["text"],
    )
    texts = [r.get("text") or "" for r in rows]
    get_embedding_service().increment_remove_documents(texts)
    logger.debug("BM25 统计已扣减: filename=%s, chunks=%d", filename, len(texts))


_INGESTED_PATH = INGESTED_STATE_PATH


def _load_ingested_state() -> dict:
    if _INGESTED_PATH.exists():
        try:
            return json.loads(_INGESTED_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("摄入状态文件读取失败: %s", e)
    return {}


def _save_ingested_state(state: dict) -> None:
    _INGESTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INGESTED_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.debug("摄入状态已保存: %d 个文件", len(state))


def _remove_ingested_record(filename: str) -> None:
    state = _load_ingested_state()
    if filename in state:
        del state[filename]
        _save_ingested_state(state)
        logger.debug("摄入状态记录已移除: %s", filename)


def _compute_file_hash(file_path: Path) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _is_supported_document(filename: str) -> bool:
    file_lower = filename.lower()
    return (
        file_lower.endswith(".pdf")
        or file_lower.endswith((".docx", ".doc"))
        or file_lower.endswith((".xlsx", ".xls"))
    )


def _normalize_document_filename(filename: str) -> str:
    safe_name = Path(filename or "").name.strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="filename must not be empty")
    if safe_name != filename or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="filename must not contain path segments")
    if not _is_supported_document(safe_name):
        raise HTTPException(status_code=400, detail="unsupported document type")
    return safe_name


async def _save_upload_file(file: UploadFile, file_path: Path) -> None:
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def _process_upload_job(job_id: str, file_path: str, filename: str) -> None:
    failed_step = "cleanup"
    try:
        upload_job_manager.complete_step(job_id, "upload", "文件已保存到服务器")

        failed_step = "cleanup"
        upload_job_manager.update_step(job_id, "cleanup", 10, "running", "正在清理同名旧文档")
        get_milvus_manager().init_collection()
        delete_expr = f'filename == "{filename}"'
        try:
            _remove_bm25_stats_for_filename(filename)
        except Exception:
            pass
        try:
            get_milvus_manager().delete(delete_expr)
        except Exception:
            pass
        try:
            get_parent_chunk_store().delete_by_filename(filename)
        except Exception:
            pass
        upload_job_manager.complete_step(job_id, "cleanup", "旧版本清理完成")

        failed_step = "parse"
        upload_job_manager.update_step(job_id, "parse", 5, "running", "正在解析文档并执行三级分块")
        new_docs = _get_loader().load_document(file_path, filename)
        if not new_docs:
            raise ValueError("文档处理失败，未能提取内容")

        parent_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]
        leaf_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) == 3]
        if not leaf_docs:
            raise ValueError("文档处理失败，未生成可检索叶子分块")
        upload_job_manager.complete_step(
            job_id,
            "parse",
            f"解析完成：父级分块 {len(parent_docs)} 个，叶子分块 {len(leaf_docs)} 个",
        )

        failed_step = "parent_store"
        upload_job_manager.update_step(job_id, "parent_store", 20, "running", "正在写入父级分块")
        get_parent_chunk_store().upsert_documents(parent_docs)
        upload_job_manager.complete_step(
            job_id, "parent_store", f"父级分块已入库：{len(parent_docs)} 个"
        )

        failed_step = "vector_store"
        total_leaf = len(leaf_docs)
        upload_job_manager.update_step(
            job_id,
            "vector_store",
            0,
            "running",
            f"正在向量化入库：0 / {total_leaf}",
            total_chunks=total_leaf,
            processed_chunks=0,
        )

        def _on_vector_progress(processed: int, total: int) -> None:
            percent = round(processed * 100 / total) if total else 100
            upload_job_manager.update_step(
                job_id,
                "vector_store",
                percent,
                "running",
                f"正在向量化入库：{processed} / {total}",
                total_chunks=total,
                processed_chunks=processed,
            )

        _get_milvus_writer().write_documents(leaf_docs, progress_callback=_on_vector_progress)
        upload_job_manager.complete_step(
            job_id, "vector_store", f"向量化入库完成：{total_leaf} 个叶子分块"
        )
        upload_job_manager.complete_job(job_id, f"成功上传并处理 {filename}")

    except Exception as e:
        logger.exception(
            "上传任务失败: job_id=%s, filename=%s, step=%s", job_id, filename, failed_step
        )
        upload_job_manager.fail_job(job_id, failed_step, str(e))


def _process_delete_job(job_id: str, filename: str) -> None:
    failed_step = "prepare"
    try:
        failed_step = "prepare"
        delete_job_manager.update_step(job_id, "prepare", 20, "running", "正在初始化 Milvus 集合")
        get_milvus_manager().init_collection()
        delete_expr = f'filename == "{filename}"'
        delete_job_manager.complete_step(job_id, "prepare", "删除任务已创建")

        failed_step = "bm25"
        delete_job_manager.update_step(job_id, "bm25", 20, "running", "正在同步 BM25 统计")
        _remove_bm25_stats_for_filename(filename)
        delete_job_manager.complete_step(job_id, "bm25", "BM25 统计已同步")

        failed_step = "milvus"
        delete_job_manager.update_step(job_id, "milvus", 30, "running", "正在删除 Milvus 向量数据")
        result = get_milvus_manager().delete(delete_expr)
        deleted_count = result.get("delete_count", 0) if isinstance(result, dict) else 0
        delete_job_manager.complete_step(job_id, "milvus", f"向量数据已删除：{deleted_count} 条")

        failed_step = "parent_store"
        delete_job_manager.update_step(
            job_id, "parent_store", 30, "running", "正在删除 PostgreSQL 父级分块"
        )
        get_parent_chunk_store().delete_by_filename(filename)
        delete_job_manager.complete_step(job_id, "parent_store", "父级分块已删除")

        delete_job_manager.complete_job(job_id, f"已删除 {filename}，向量数据 {deleted_count} 条")

    except Exception as e:
        logger.exception(
            "删除任务失败: job_id=%s, filename=%s, step=%s", job_id, filename, failed_step
        )
        delete_job_manager.fail_job(job_id, failed_step, str(e))


def _process_ingest_job(
    job_id: str,
    to_process: list[tuple[Path, str]],
    to_delete: list[str],
    current_state: dict,
) -> None:
    failed_step = "scan"
    try:
        get_milvus_manager().init_collection()

        for name in to_delete:
            try:
                delete_expr = f'filename == "{name}"'
                _remove_bm25_stats_for_filename(name)
                get_milvus_manager().delete(delete_expr)
                get_parent_chunk_store().delete_by_filename(name)
            except Exception:
                pass

        total = len(to_process)
        upload_job_manager.complete_step(
            job_id,
            "scan",
            f"扫描完成：{total} 个文件待处理，{len(to_delete)} 个已清理",
        )

        processed = 0
        all_leaf_docs = []
        all_parent_docs = []

        failed_step = "parse"
        for fp, reason in to_process:
            try:
                upload_job_manager.update_step(
                    job_id,
                    "parse",
                    int(processed / max(total, 1) * 100),
                    "running",
                    f"正在解析 ({processed + 1}/{total}): {fp.name} [{reason}]",
                )
                new_docs = _get_loader().load_document(str(fp), fp.name)
                if not new_docs:
                    continue
                parent_docs = [d for d in new_docs if int(d.get("chunk_level", 0) or 0) in (1, 2)]
                leaf_docs = [d for d in new_docs if int(d.get("chunk_level", 0) or 0) == 3]
                all_parent_docs.extend(parent_docs)
                all_leaf_docs.extend(leaf_docs)

                try:
                    delete_expr = f'filename == "{fp.name}"'
                    _remove_bm25_stats_for_filename(fp.name)
                    get_milvus_manager().delete(delete_expr)
                    get_parent_chunk_store().delete_by_filename(fp.name)
                except Exception:
                    pass
                processed += 1
            except Exception:
                processed += 1
                continue

        upload_job_manager.complete_step(
            job_id,
            "parse",
            f"解析完成：父块 {len(all_parent_docs)}，叶子块 {len(all_leaf_docs)}",
        )

        if all_parent_docs:
            failed_step = "parent_store"
            upload_job_manager.update_step(
                job_id, "parent_store", 10, "running", "正在写入父级分块"
            )
            get_parent_chunk_store().upsert_documents(all_parent_docs)
            upload_job_manager.complete_step(
                job_id, "parent_store", f"父块入库：{len(all_parent_docs)}"
            )

        if all_leaf_docs:
            failed_step = "vector_store"
            total_leaf = len(all_leaf_docs)
            upload_job_manager.update_step(
                job_id,
                "vector_store",
                0,
                "running",
                f"向量化入库：0 / {total_leaf}",
                total_chunks=total_leaf,
                processed_chunks=0,
            )

            def _progress(processed_count: int, total_count: int) -> None:
                pct = round(processed_count * 100 / total_count) if total_count else 100
                upload_job_manager.update_step(
                    job_id,
                    "vector_store",
                    pct,
                    "running",
                    f"向量化：{processed_count} / {total_count}",
                    total_chunks=total_count,
                    processed_chunks=processed_count,
                )

            _get_milvus_writer().write_documents(all_leaf_docs, progress_callback=_progress)
            upload_job_manager.complete_step(job_id, "vector_store", f"向量入库：{total_leaf}")

        new_state = {n: current_state[n] for n in current_state}
        _save_ingested_state(new_state)

        upload_job_manager.complete_step(
            job_id,
            "bm25",
            f"完成：{processed} 文件，{len(all_leaf_docs)} 叶子块",
        )
        upload_job_manager.complete_job(job_id, f"批量导入完成：{processed} 个文件")

    except Exception as e:
        logger.exception("批量导入任务失败: job_id=%s, step=%s", job_id, failed_step)
        upload_job_manager.fail_job(job_id, failed_step, str(e))


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(_: User = Depends(require_admin)):
    try:
        get_milvus_manager().init_collection()
        results = get_milvus_manager().query(
            output_fields=["filename", "file_type"],
            limit=10000,
        )
        file_stats = {}
        for item in results:
            filename = item.get("filename", "")
            file_type = item.get("file_type", "")
            if filename not in file_stats:
                file_stats[filename] = {
                    "filename": filename,
                    "file_type": file_type,
                    "chunk_count": 0,
                }
            file_stats[filename]["chunk_count"] += 1
        documents = [DocumentInfo(**stats) for stats in file_stats.values()]
        return DocumentListResponse(documents=documents)
    except Exception as e:
        logger.exception("获取文档列表失败")
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")


@router.post("/documents/upload/async", response_model=DocumentUploadStartResponse)
async def upload_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
):
    filename = _normalize_document_filename(file.filename or "")
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    if not _is_supported_document(filename):
        raise HTTPException(status_code=400, detail="仅支持 PDF、Word 和 Excel 文档")

    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size and file.size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制（最大 {MAX_UPLOAD_SIZE_MB}MB）",
        )

    os.makedirs(COMPUTED_UPLOAD_DIR, exist_ok=True)
    job = upload_job_manager.create_job(filename)
    file_path = COMPUTED_UPLOAD_DIR / filename

    try:
        upload_job_manager.update_step(
            job["job_id"], "upload", 1, "running", "正在保存文件到服务器"
        )
        await _save_upload_file(file, file_path)
        upload_job_manager.complete_step(job["job_id"], "upload", "文件已上传，等待后台处理")
    except Exception as e:
        upload_job_manager.fail_job(job["job_id"], "upload", f"文件保存失败: {e}")
        logger.exception("文件保存失败: filename=%s", filename)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")

    background_tasks.add_task(_process_upload_job, job["job_id"], str(file_path), filename)
    logger.info("异步上传任务已创建: job_id=%s, filename=%s", job["job_id"], filename)
    return DocumentUploadStartResponse(
        job_id=job["job_id"],
        filename=filename,
        message="文件已上传，正在后台解析和向量化入库",
    )


@router.get("/documents/upload/jobs/{job_id}", response_model=DocumentUploadJobResponse)
async def get_upload_job(job_id: str, _: User = Depends(require_admin)):
    job = upload_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="上传任务不存在或已过期")
    return DocumentUploadJobResponse(**job)


@router.get("/documents/upload/jobs", response_model=list[DocumentUploadJobResponse])
async def list_upload_jobs(_: User = Depends(require_admin)):
    jobs = upload_job_manager.list_jobs()
    jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return [DocumentUploadJobResponse(**job) for job in jobs]


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...), _: User = Depends(require_admin)):
    try:
        filename = _normalize_document_filename(file.filename or "")
        filename.lower()
        if not filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        if not _is_supported_document(filename):
            raise HTTPException(status_code=400, detail="仅支持 PDF、Word 和 Excel 文档")

        max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if file.size and file.size > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"文件大小超过限制（最大 {MAX_UPLOAD_SIZE_MB}MB）",
            )

        os.makedirs(COMPUTED_UPLOAD_DIR, exist_ok=True)
        get_milvus_manager().init_collection()

        delete_expr = f'filename == "{filename}"'
        try:
            _remove_bm25_stats_for_filename(filename)
        except Exception:
            pass
        try:
            get_milvus_manager().delete(delete_expr)
        except Exception:
            pass
        try:
            get_parent_chunk_store().delete_by_filename(filename)
        except Exception:
            pass

        file_path = COMPUTED_UPLOAD_DIR / filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        try:
            new_docs = _get_loader().load_document(str(file_path), filename)
        except Exception as doc_err:
            raise HTTPException(status_code=500, detail=f"文档处理失败: {doc_err}")

        if not new_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未能提取内容")

        parent_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]
        leaf_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) == 3]
        if not leaf_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未生成可检索叶子分块")

        get_parent_chunk_store().upsert_documents(parent_docs)
        _get_milvus_writer().write_documents(leaf_docs)

        logger.info(
            "同步上传完成: filename=%s, leaf=%d, parent=%d",
            filename,
            len(leaf_docs),
            len(parent_docs),
        )
        return DocumentUploadResponse(
            filename=filename,
            chunks_processed=len(leaf_docs),
            message=(
                f"成功上传并处理 {filename}，叶子分块 {len(leaf_docs)} 个，"
                f"父级分块 {len(parent_docs)} 个（存入 PostgreSQL）"
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("同步上传失败: filename=%s", file.filename or "")
        raise HTTPException(status_code=500, detail=f"文档上传失败: {str(e)}")


@router.delete("/documents/delete/async/{filename}", response_model=DocumentDeleteStartResponse)
async def delete_document_async(
    filename: str,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
):
    filename = _normalize_document_filename(filename)
    job = delete_job_manager.create_job(
        filename,
        steps=DELETE_STEPS,
        current_step="prepare",
        message="等待删除",
        completion_step="parent_store",
    )
    delete_job_manager.update_step(job["job_id"], "prepare", 1, "running", "删除任务已提交")
    background_tasks.add_task(_process_delete_job, job["job_id"], filename)
    logger.info("异步删除任务已创建: job_id=%s, filename=%s", job["job_id"], filename)
    return DocumentDeleteStartResponse(
        job_id=job["job_id"],
        filename=filename,
        message=f"正在删除 {filename}",
    )


@router.get("/documents/delete/jobs/{job_id}", response_model=DocumentDeleteJobResponse)
async def get_delete_job(job_id: str, _: User = Depends(require_admin)):
    job = delete_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="删除任务不存在或已过期")
    return DocumentDeleteJobResponse(**job)


@router.delete("/documents/{filename}", response_model=DocumentDeleteResponse)
async def delete_document(filename: str, _: User = Depends(require_admin)):
    try:
        filename = _normalize_document_filename(filename)
        get_milvus_manager().init_collection()

        delete_expr = f'filename == "{filename}"'
        _remove_bm25_stats_for_filename(filename)
        result = get_milvus_manager().delete(delete_expr)
        get_parent_chunk_store().delete_by_filename(filename)

        _remove_ingested_record(filename)

        logger.info("同步删除完成: filename=%s", filename)
        return DocumentDeleteResponse(
            filename=filename,
            chunks_deleted=result.get("delete_count", 0) if isinstance(result, dict) else 0,
            message=f"成功删除文档 {filename} 的向量数据（本地文件已保留）",
        )
    except Exception as e:
        logger.exception("同步删除失败: filename=%s", filename)
        raise HTTPException(status_code=500, detail=f"删除文档失败: {str(e)}")


@router.post("/documents/ingest", response_model=IncrementalIngestResponse)
async def incremental_ingest(
    request: IncrementalIngestRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
):
    target_dir = Path(request.directory) if request.directory else COMPUTED_UPLOAD_DIR
    if not target_dir.exists():
        raise HTTPException(status_code=400, detail=f"目录不存在: {target_dir}")

    pdf_files = sorted(target_dir.glob("*.pdf"))
    if not pdf_files:
        return IncrementalIngestResponse(
            job_id="",
            message="未找到 PDF 文件",
            files_total=0,
        )

    prev_state = {} if request.full_rebuild else _load_ingested_state()

    current: dict[str, dict] = {}
    for fp in pdf_files:
        current[fp.name] = {
            "hash": _compute_file_hash(fp),
            "path": str(fp.resolve()),
        }

    to_process: list[tuple[Path, str]] = []
    if request.full_rebuild:
        to_process = [(fp, "全量重建") for fp in pdf_files]
    else:
        for fp in pdf_files:
            name = fp.name
            if name not in prev_state:
                to_process.append((fp, "新增"))
            elif prev_state[name]["hash"] != current[name]["hash"]:
                to_process.append((fp, "修改"))

    skipped = len(pdf_files) - len(to_process)
    to_delete = [n for n in prev_state if n not in current]

    if not to_process and not to_delete:
        return IncrementalIngestResponse(
            job_id="",
            message="知识库已是最新",
            files_total=len(pdf_files),
            files_skipped=skipped,
        )

    job = upload_job_manager.create_job(
        f"批量导入 ({len(to_process)} 文件)",
        steps=INGEST_STEPS,
        current_step="scan",
        message=f"发现 {len(to_process)} 个待处理文件",
        completion_step="bm25",
    )

    background_tasks.add_task(
        _process_ingest_job,
        job["job_id"],
        to_process,
        to_delete,
        current,
    )

    logger.info(
        "增量导入任务已创建: job_id=%s, new=%d, modified=%d, skipped=%d, deleted=%d",
        job["job_id"],
        sum(1 for _, r in to_process if r == "新增"),
        sum(1 for _, r in to_process if r == "修改"),
        skipped,
        len(to_delete),
    )
    return IncrementalIngestResponse(
        job_id=job["job_id"],
        message=f"开始批量导入 {len(to_process)} 个文件",
        files_total=len(pdf_files),
        files_new=sum(1 for _, r in to_process if r == "新增"),
        files_modified=sum(1 for _, r in to_process if r == "修改"),
        files_skipped=skipped,
        files_deleted=len(to_delete),
    )
