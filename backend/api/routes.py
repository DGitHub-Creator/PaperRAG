"""
API 路由模块 —— 所有 HTTP 端点定义。

本模块是 PaperRAG 的 Web API 层，提供以下端点分组：

  认证相关:
    POST /auth/register      - 用户注册
    POST /auth/login         - 用户登录
    GET  /auth/me            - 获取当前用户信息

  会话管理:
    GET    /sessions                    - 列出用户的所有会话
    GET    /sessions/{session_id}       - 获取指定会话的消息
    DELETE /sessions/{session_id}       - 删除指定会话

  对话:
    POST /chat              - 同步对话（非流式）
    POST /chat/stream       - 流式对话（SSE）

  文档管理:
    GET    /documents                       - 列出已入库文档
    POST   /documents/upload               - 同步文档上传（旧版）
    POST   /documents/upload/async         - 异步文档上传（含进度跟踪）
    GET    /documents/upload/jobs/{job_id} - 查询上传任务进度
    GET    /documents/upload/jobs          - 列出所有上传任务
    DELETE /documents/{filename}           - 同步删除文档（旧版）
    DELETE /documents/delete/async/{filename} - 异步删除文档（含进度跟踪）
    GET    /documents/delete/jobs/{job_id} - 查询删除任务进度

  增量导入:
    POST /documents/ingest  - 增量导入（扫描目录，仅处理变更）

  缓存管理:
    POST /cache/clear       - 清空语义缓存和 Redis 缓存

所有管理员端点需要 require_admin 依赖注入。
"""

import hashlib
import json
import os
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
)

from backend.core.auth import require_admin
from backend.core.config import (
    DATA_DIR,
    INGESTED_STATE_PATH,
    UPLOAD_DIR,
)
from backend.core.dependencies import (
    get_embedding_service,
    get_milvus_manager,
    get_parent_chunk_store,
)
from backend.core.logging_config import get_logger
from backend.core.models import User
from backend.core.stats import get_stats, reset_stats
from backend.rag.document_loader import DocumentLoader
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
from backend.services.cache import cache as redis_cache
from backend.services.upload_jobs import (
    DELETE_STEPS,
    INGEST_STEPS,
    delete_job_manager,
    upload_job_manager,
)

logger = get_logger(__name__)

# ── 路径与组件初始化 ─────────────────────────────────────────────────

COMPUTED_DATA_DIR = DATA_DIR  # 从 backend.core.config 导入
COMPUTED_UPLOAD_DIR = UPLOAD_DIR  # 从 backend.core.config 导入

loader = DocumentLoader()
"""文档加载器实例：负责解析 PDF / Word / Excel 并生成三级分块。"""

router = APIRouter()
"""FastAPI 路由器实例（prefix 由 app.py 统一配置）。"""


def _get_milvus_writer():
    from backend.vectordb.milvus_writer import MilvusWriter

    return MilvusWriter(
        embedding_service=get_embedding_service(),
        milvus_manager=get_milvus_manager(),
    )


# ═══════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════


def _remove_bm25_stats_for_filename(filename: str) -> None:
    """删除 Milvus 中该文件对应 chunk 前，先从持久化 BM25 统计中扣减。

    步骤：
      1. 查询 Milvus 中该文件的所有分块文本。
      2. 调用 embedding_service.increment_remove_documents 批量扣减 BM25 统计。

    这确保删除文档后，BM25 的 N / df / 长度和等统计量与 Milvus 中实际数据一致。

    Args:
        filename: 要清理 BM25 统计的文件名。
    """
    rows = get_milvus_manager().query_all(
        filter_expr=f'filename == "{filename}"',
        output_fields=["text"],
    )
    texts = [r.get("text") or "" for r in rows]
    get_embedding_service().increment_remove_documents(texts)
    logger.debug("BM25 统计已扣减: filename=%s, chunks=%d", filename, len(texts))


# ── 增量摄入状态追踪 ──────────────────────────────────────────────────

# 摄入状态文件路径（记录已处理文件的哈希值）
_INGESTED_PATH = INGESTED_STATE_PATH  # 从 backend.core.config 导入


def _load_ingested_state() -> dict:
    """从磁盘加载增量摄入状态。

    状态文件格式为 JSON，key 为文件名，value 为 {"hash": md5, "path": 绝对路径}。

    Returns:
        摄入状态字典。文件不存在或损坏时返回空字典。
    """
    if _INGESTED_PATH.exists():
        try:
            return json.loads(_INGESTED_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("摄入状态文件读取失败: %s", e)
    return {}


def _save_ingested_state(state: dict) -> None:
    """将增量摄入状态写入磁盘（原子写入）。

    Args:
        state: 摄入状态字典 {filename: {"hash": str, "path": str}}。
    """
    _INGESTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INGESTED_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.debug("摄入状态已保存: %d 个文件", len(state))


def _remove_ingested_record(filename: str) -> None:
    """从摄入状态中移除指定文件的记录。

    用于文档被手动删除时，确保后续增量导入能将该文件视为"新增"。

    Args:
        filename: 要移除记录的文件名。
    """
    state = _load_ingested_state()
    if filename in state:
        del state[filename]
        _save_ingested_state(state)
        logger.debug("摄入状态记录已移除: %s", filename)


def _compute_file_hash(file_path: Path) -> str:
    """计算文件的 MD5 哈希值，用于增量导入的差分检测。

    以 8192 字节为块大小流式读取，避免大文件一次性读入内存。

    Args:
        file_path: 文件路径。

    Returns:
        文件内容的 MD5 十六进制字符串。
    """
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


# ═══════════════════════════════════════════════════════════════════
# 认证端点
# ═══════════════════════════════════════════════════════════════════


# 会话端点
# ═══════════════════════════════════════════════════════════════════


def _is_supported_document(filename: str) -> bool:
    """检查文件名后缀是否属于支持的文档格式。

    支持的格式：
      - PDF (.pdf)
      - Word (.docx, .doc)
      - Excel (.xlsx, .xls)

    Args:
        filename: 文件名（含扩展名）。

    Returns:
        True 表示支持该格式，False 表示不支持。
    """
    file_lower = filename.lower()
    return (
        file_lower.endswith(".pdf")
        or file_lower.endswith((".docx", ".doc"))
        or file_lower.endswith((".xlsx", ".xls"))
    )


def _normalize_document_filename(filename: str) -> str:
    """Return a safe basename for uploaded or deleted documents."""
    safe_name = Path(filename or "").name.strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="filename must not be empty")
    if safe_name != filename or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="filename must not contain path segments")
    if not _is_supported_document(safe_name):
        raise HTTPException(status_code=400, detail="unsupported document type")
    return safe_name


async def _save_upload_file(file: UploadFile, file_path: Path) -> None:
    """按块写入上传文件到磁盘，避免大文件一次性读入内存。

    以 1 MB 为块大小流式读取 UploadFile 并写入目标路径。

    Args:
        file: FastAPI UploadFile 对象。
        file_path: 目标文件路径（Path 对象）。
    """
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 MB 块
            if not chunk:
                break
            f.write(chunk)


# ═══════════════════════════════════════════════════════════════════
# 后台任务处理函数
# ═══════════════════════════════════════════════════════════════════


def _process_upload_job(job_id: str, file_path: str, filename: str) -> None:
    """后台执行文档上传的完整流水线（解析 -> 分块 -> 向量化入库）。

    处理步骤（对应 DEFAULT_STEPS）：
      1. upload: 标记文件已保存（由调用方完成）。
      2. cleanup: 清理同名旧文档（BM25 统计 + Milvus 向量 + PostgreSQL 父块）。
      3. parse: 使用 DocumentLoader 解析文档并生成三级分块。
      4. parent_store: 将 Level 1/2 分块写入 PostgreSQL。
      5. vector_store: 将 Level 3 叶子分块向量化后写入 Milvus（含进度回调）。

    每个步骤的进度通过 upload_job_manager 实时更新，前端可轮询获取。

    Args:
        job_id: 任务 ID（与前端轮询键对应）。
        file_path: 已落盘的文档文件绝对路径。
        filename: 文档文件名（用于 Milvus 过滤和进度显示）。
    """
    failed_step = "cleanup"
    try:
        # Step 1: upload（由调用方完成）
        upload_job_manager.complete_step(job_id, "upload", "文件已保存到服务器")

        # Step 2: cleanup —— 清理同名旧文档
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

        # Step 3: parse —— 解析文档并生成三级分块
        failed_step = "parse"
        upload_job_manager.update_step(job_id, "parse", 5, "running", "正在解析文档并执行三级分块")
        new_docs = loader.load_document(file_path, filename)
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

        # Step 4: parent_store —— 写入父级分块到 PostgreSQL
        failed_step = "parent_store"
        upload_job_manager.update_step(job_id, "parent_store", 20, "running", "正在写入父级分块")
        get_parent_chunk_store().upsert_documents(parent_docs)
        upload_job_manager.complete_step(
            job_id, "parent_store", f"父级分块已入库：{len(parent_docs)} 个"
        )

        # Step 5: vector_store —— 向量化叶子分块并写入 Milvus
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
            """向量化进度回调 —— 实时更新任务状态供前端轮询。"""
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
    """后台执行文档删除流水线。

    处理步骤（对应 DELETE_STEPS）：
      1. prepare: 初始化 Milvus 集合，构建删除过滤表达式。
      2. bm25: 同步 BM25 统计（从持久化状态中扣减）。
      3. milvus: 删除 Milvus 中的向量数据。
      4. parent_store: 删除 PostgreSQL 中的父级分块。

    Args:
        job_id: 任务 ID。
        filename: 要删除的文档文件名。
    """
    failed_step = "prepare"
    try:
        # Step 1: prepare
        failed_step = "prepare"
        delete_job_manager.update_step(job_id, "prepare", 20, "running", "正在初始化 Milvus 集合")
        get_milvus_manager().init_collection()
        delete_expr = f'filename == "{filename}"'
        delete_job_manager.complete_step(job_id, "prepare", "删除任务已创建")

        # Step 2: bm25
        failed_step = "bm25"
        delete_job_manager.update_step(job_id, "bm25", 20, "running", "正在同步 BM25 统计")
        _remove_bm25_stats_for_filename(filename)
        delete_job_manager.complete_step(job_id, "bm25", "BM25 统计已同步")

        # Step 3: milvus
        failed_step = "milvus"
        delete_job_manager.update_step(job_id, "milvus", 30, "running", "正在删除 Milvus 向量数据")
        result = get_milvus_manager().delete(delete_expr)
        deleted_count = result.get("delete_count", 0) if isinstance(result, dict) else 0
        delete_job_manager.complete_step(job_id, "milvus", f"向量数据已删除：{deleted_count} 条")

        # Step 4: parent_store
        failed_step = "parent_store"
        delete_job_manager.update_step(
            job_id, "parent_store", 30, "running", "正在删除 PostgreSQL 父级分块"
        )
        get_parent_chunk_store().delete_by_filename(filename)
        delete_job_manager.complete_step(job_id, "parent_store", "父级分块已删除")

        # 完成摘要
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
    """后台执行批量增量导入任务。

    处理步骤（对应 INGEST_STEPS）：
      1. scan: 扫描文件变更（由调用方完成），清理已删除文件。
      2. parse: 逐个解析待处理文件（含学术清洗 + 三级分块）。
      3. parent_store: 批量写入父级分块到 PostgreSQL。
      4. vector_store: 批量向量化叶子分块并写入 Milvus。
      5. bm25: 更新摄入状态文件（记录新文件哈希值）。

    Args:
        job_id: 任务 ID。
        to_process: 待处理文件列表，每项为 (Path对象, 变更原因字符串)。
        to_delete: 已从目录中移除的文件名列表。
        current_state: 当前文件状态字典 {filename: {"hash": str, "path": str}}。
    """
    failed_step = "scan"
    try:
        get_milvus_manager().init_collection()

        # Step 1: 清理已移除的文档
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

        # Step 2: 逐个解析文件
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
                new_docs = loader.load_document(str(fp), fp.name)
                if not new_docs:
                    continue
                parent_docs = [d for d in new_docs if int(d.get("chunk_level", 0) or 0) in (1, 2)]
                leaf_docs = [d for d in new_docs if int(d.get("chunk_level", 0) or 0) == 3]
                all_parent_docs.extend(parent_docs)
                all_leaf_docs.extend(leaf_docs)

                # 清理同名旧版本
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

        # Step 3: 写入父级分块
        if all_parent_docs:
            failed_step = "parent_store"
            upload_job_manager.update_step(
                job_id, "parent_store", 10, "running", "正在写入父级分块"
            )
            get_parent_chunk_store().upsert_documents(all_parent_docs)
            upload_job_manager.complete_step(
                job_id, "parent_store", f"父块入库：{len(all_parent_docs)}"
            )

        # Step 4: 向量化叶子分块
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
                """向量化进度回调 —— 实时更新批量导入任务状态。"""
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

        # Step 5: 更新摄入状态文件
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


# ═══════════════════════════════════════════════════════════════════
# 文档列表端点
# ═══════════════════════════════════════════════════════════════════


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(_: User = Depends(require_admin)):
    """获取已入库的文档列表（管理员权限）。

    从 Milvus 中查询所有 chunk，按 filename 聚合统计 chunk 数量，
    返回去重后的文档信息列表。

    Returns:
        DocumentListResponse: 包含 documents 列表。

    Raises:
        HTTPException 500: 查询失败时。
    """
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


# ═══════════════════════════════════════════════════════════════════
# 文档上传端点
# ═══════════════════════════════════════════════════════════════════


@router.post("/documents/upload/async", response_model=DocumentUploadStartResponse)
async def upload_document_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
):
    """异步文档上传端点 —— 文件落盘后立即返回，后台完成解析和向量化。

    流程：
      1. 校验文件名和格式。
      2. 创建上传任务（job_id），保存文件到磁盘。
      3. 将 _process_upload_job 添加到后台任务队列。
      4. 立即返回 job_id 供前端轮询进度。

    Args:
        background_tasks: FastAPI 后台任务管理器。
        file: 上传的文件（multipart/form-data）。
        _: 管理员权限验证（依赖注入）。

    Returns:
        DocumentUploadStartResponse: 包含 job_id, filename, message。

    Raises:
        HTTPException 400: 文件名为空或格式不支持。
        HTTPException 500: 文件保存失败。
    """
    filename = _normalize_document_filename(file.filename or "")
    if not filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    if not _is_supported_document(filename):
        raise HTTPException(status_code=400, detail="仅支持 PDF、Word 和 Excel 文档")

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
    """查询指定上传任务的进度。

    Args:
        job_id: 任务 ID。
        _: 管理员权限验证。

    Returns:
        DocumentUploadJobResponse: 任务当前状态快照。

    Raises:
        HTTPException 404: 任务不存在或已过期。
    """
    job = upload_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="上传任务不存在或已过期")
    return DocumentUploadJobResponse(**job)


@router.get("/documents/upload/jobs", response_model=list[DocumentUploadJobResponse])
async def list_upload_jobs(_: User = Depends(require_admin)):
    """列出所有上传任务，按创建时间降序。

    Args:
        _: 管理员权限验证。

    Returns:
        list[DocumentUploadJobResponse]: 任务列表。
    """
    jobs = upload_job_manager.list_jobs()
    jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return [DocumentUploadJobResponse(**job) for job in jobs]


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...), _: User = Depends(require_admin)):
    """同步文档上传端点（旧版兼容接口）。

    与异步版本不同，此端点等待全部处理完成后才返回。
    适用于小文件或不需要进度追踪的场景。

    Args:
        file: 上传的文件。
        _: 管理员权限验证。

    Returns:
        DocumentUploadResponse: 包含处理的叶子分块数和父级分块数。

    Raises:
        HTTPException 400: 文件名为空或格式不支持。
        HTTPException 500: 文档处理或向量化失败。
    """
    try:
        filename = _normalize_document_filename(file.filename or "")
        filename.lower()
        if not filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        if not _is_supported_document(filename):
            raise HTTPException(status_code=400, detail="仅支持 PDF、Word 和 Excel 文档")

        os.makedirs(COMPUTED_UPLOAD_DIR, exist_ok=True)
        get_milvus_manager().init_collection()

        # 清理同名旧文档
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

        # 保存文件到磁盘
        file_path = COMPUTED_UPLOAD_DIR / filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # 解析文档
        try:
            new_docs = loader.load_document(str(file_path), filename)
        except Exception as doc_err:
            raise HTTPException(status_code=500, detail=f"文档处理失败: {doc_err}")

        if not new_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未能提取内容")

        parent_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]
        leaf_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) == 3]
        if not leaf_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未生成可检索叶子分块")

        # 写入存储
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


# ═══════════════════════════════════════════════════════════════════
# 文档删除端点
# ═══════════════════════════════════════════════════════════════════


@router.delete("/documents/delete/async/{filename}", response_model=DocumentDeleteStartResponse)
async def delete_document_async(
    filename: str,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
):
    """异步文档删除端点 —— 立即返回 job_id，后台执行删除。

    删除内容：Milvus 向量 + BM25 统计扣减 + PostgreSQL 父级分块。

    Args:
        filename: 要删除的文件名。
        background_tasks: FastAPI 后台任务管理器。
        _: 管理员权限验证。

    Returns:
        DocumentDeleteStartResponse: 包含 job_id, filename, message。
    """
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
    """查询指定删除任务的进度。

    Args:
        job_id: 任务 ID。
        _: 管理员权限验证。

    Returns:
        DocumentDeleteJobResponse: 任务当前状态快照。

    Raises:
        HTTPException 404: 任务不存在或已过期。
    """
    job = delete_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="删除任务不存在或已过期")
    return DocumentDeleteJobResponse(**job)


@router.delete("/documents/{filename}", response_model=DocumentDeleteResponse)
async def delete_document(filename: str, _: User = Depends(require_admin)):
    """同步删除文档端点（旧版兼容接口）。

    立即执行删除操作：BM25 统计扣减 + Milvus 向量删除 + PostgreSQL 父块删除。
    同时清理增量摄入状态追踪记录。

    Args:
        filename: 要删除的文件名。
        _: 管理员权限验证。

    Returns:
        DocumentDeleteResponse: 包含 chunks_deleted 和操作消息。

    Raises:
        HTTPException 500: 删除操作失败。
    """
    try:
        filename = _normalize_document_filename(filename)
        get_milvus_manager().init_collection()

        delete_expr = f'filename == "{filename}"'
        _remove_bm25_stats_for_filename(filename)
        result = get_milvus_manager().delete(delete_expr)
        get_parent_chunk_store().delete_by_filename(filename)

        # 同步清理摄入状态追踪
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


# ═══════════════════════════════════════════════════════════════════
# 增量导入端点
# ═══════════════════════════════════════════════════════════════════


@router.post("/documents/ingest", response_model=IncrementalIngestResponse)
async def incremental_ingest(
    request: IncrementalIngestRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(require_admin),
):
    """增量导入端点 —— 扫描指定目录中的 PDF，仅处理新增或修改的文件。

    差分检测逻辑：
      1. 扫描目标目录中的所有 PDF 文件，计算 MD5 哈希。
      2. 与已保存的摄入状态比较，识别新增、修改、删除的文件。
      3. 跳过未变更的文件。
      4. 对于删除的文件（目录中不存在但状态中有记录），清理其向量数据。
      5. 将处理任务提交到后台执行。

    支持 full_rebuild=True 全量重建模式（忽略状态，处理所有文件）。

    Args:
        request: 增量导入请求体（directory, full_rebuild）。
        background_tasks: FastAPI 后台任务管理器。
        _: 管理员权限验证。

    Returns:
        IncrementalIngestResponse: 包含 job_id 和文件变更统计。

    Raises:
        HTTPException 400: 目标目录不存在。
    """
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

    # 差分检测：计算当前文件哈希值
    current: dict[str, dict] = {}
    for fp in pdf_files:
        current[fp.name] = {
            "hash": _compute_file_hash(fp),
            "path": str(fp.resolve()),
        }

    # 确定需要处理的文件
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

    # 创建后台批量导入任务
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


# ═══════════════════════════════════════════════════════════════════
# 缓存管理端点
# ═══════════════════════════════════════════════════════════════════


@router.post("/cache/clear")
async def clear_cache(_: User = Depends(require_admin)):
    """清空语义缓存和 Redis 缓存（管理员权限）。

    调用 SemanticCache.invalidate() 清空进程内两级缓存
    （精确匹配层 + 语义相似度层）。

    Returns:
        dict: 包含 message 和移除的缓存条目数。

    Raises:
        HTTPException 500: 清空操作失败。
    """
    try:
        semantic = redis_cache.get_semantic()
        n = semantic.invalidate()
        logger.info("缓存已手动清空: 移除 %d 条记录", n)
        return {"message": f"缓存已清空，移除 {n} 条记录"}
    except Exception as e:
        logger.exception("清空缓存失败")
        raise HTTPException(status_code=500, detail=f"清空缓存失败: {str(e)}")


# ═══════════════════════════════════════════════════════════════════
# 统计与运维端点
# ═══════════════════════════════════════════════════════════════════


@router.get("/stats/usage")
async def usage_stats(_: User = Depends(require_admin)):
    """获取 API 使用统计（管理员权限）。

    返回每个请求路径的访问次数和最后访问时间，
    按访问次数降序排列。

    Returns:
        list[dict]: 统计列表。
    """
    return get_stats()


@router.delete("/stats/usage")
async def reset_usage_stats(_: User = Depends(require_admin)):
    """重置 API 使用统计（管理员权限）。

    Returns:
        dict: 操作消息。
    """
    reset_stats()
    return {"message": "统计已重置"}
