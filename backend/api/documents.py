"""文档管理路由 —— 上传、删除、列表、增量导入端点。"""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from backend.core.auth import require_admin
from backend.core.config import DATA_DIR, MAX_UPLOAD_SIZE_MB, UPLOAD_DIR
from backend.core.dependencies import (
    get_milvus_manager,
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

from backend.services.document_jobs import (
    _compute_file_hash, _load_ingested_state, _process_delete_job, _process_ingest_job, _process_upload_job,
    index_document, remove_document,
)

logger = get_logger(__name__)

COMPUTED_DATA_DIR = DATA_DIR
COMPUTED_UPLOAD_DIR = UPLOAD_DIR


router = APIRouter()


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
    if safe_name != filename or safe_name in {".", ".."} or any(char in safe_name for char in ("/", "\\", ":", "\x00")):
        raise HTTPException(status_code=400, detail="filename must not contain path segments")
    if not _is_supported_document(safe_name):
        raise HTTPException(status_code=400, detail="unsupported document type")
    return safe_name


async def _save_upload_file(file: UploadFile, file_path: Path) -> None:
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(status_code=413, detail=f"文件大小超过限制（最大 {MAX_UPLOAD_SIZE_MB}MB）")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=file_path.parent, delete=False) as output:
            temporary = Path(output.name)
            total = 0
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail=f"文件大小超过限制（最大 {MAX_UPLOAD_SIZE_MB}MB）")
                await run_in_threadpool(output.write, chunk)
            await run_in_threadpool(output.flush)
            await run_in_threadpool(os.fsync, output.fileno())
        await run_in_threadpool(os.replace, temporary, file_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _staging_path(filename: str) -> Path:
    return COMPUTED_UPLOAD_DIR / ".pending" / (uuid4().hex + Path(filename).suffix)



@router.get("/documents", response_model=DocumentListResponse)
def list_documents(_: User = Depends(require_admin)):
    try:
        get_milvus_manager().init_collection()
        results = get_milvus_manager().query_all(output_fields=["filename", "file_type"])
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
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/documents/upload/async", response_model=DocumentUploadStartResponse)
async def upload_document_async(background_tasks: BackgroundTasks, file: UploadFile = File(...), _: User = Depends(require_admin)):
    filename = _normalize_document_filename(file.filename or "")
    job = upload_job_manager.create_job(filename)
    file_path = _staging_path(filename)
    try:
        upload_job_manager.update_step(job["job_id"], "upload", 1, "running", "正在保存文件")
        await _save_upload_file(file, file_path)
        upload_job_manager.complete_step(job["job_id"], "upload", "文件已暂存，等待解析")
    except HTTPException:
        upload_job_manager.fail_job(job["job_id"], "upload", "文件大小超过限制")
        raise
    except Exception as exc:
        upload_job_manager.fail_job(job["job_id"], "upload", "文件保存失败，请查看服务日志")
        logger.exception("文件保存失败: filename=%s", filename)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    background_tasks.add_task(_process_upload_job, job["job_id"], str(file_path), filename)
    return DocumentUploadStartResponse(job_id=job["job_id"], filename=filename, message="文件已暂存，正在后台处理")



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
    filename = _normalize_document_filename(file.filename or "")
    staged = _staging_path(filename)
    try:
        await _save_upload_file(file, staged)
        counts = await run_in_threadpool(index_document, str(staged), filename, destination=COMPUTED_UPLOAD_DIR / filename)
        return DocumentUploadResponse(
            filename=filename, chunks_processed=counts["leaf_count"],
            message=f"成功处理 {filename}：叶子分块 {counts['leaf_count']} 个，父级分块 {counts['parent_count']} 个",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("同步上传失败，暂存原文保留: filename=%s", filename)
        raise HTTPException(status_code=500, detail="Internal server error") from exc



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
def delete_document(filename: str, _: User = Depends(require_admin)):
    filename = _normalize_document_filename(filename)
    try:
        count = remove_document(filename)
        return DocumentDeleteResponse(filename=filename, chunks_deleted=count, message=f"成功删除文档 {filename} 的索引，本地原文已保留")
    except Exception as exc:
        logger.exception("同步删除失败: filename=%s", filename)
        raise HTTPException(status_code=500, detail="Internal server error") from exc



@router.post("/documents/ingest", response_model=IncrementalIngestResponse)
def incremental_ingest(
    request: IncrementalIngestRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
):
    target_dir = Path(request.directory) if request.directory else COMPUTED_UPLOAD_DIR
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"目录不存在: {target_dir}")

    target_dir = target_dir.resolve()
    pdf_files = sorted(path for path in target_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf")
    prev_state = {
        name: row for name, row in _load_ingested_state().items()
        if Path(row["path"]).resolve().parent == target_dir
    }

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
