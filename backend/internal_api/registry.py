"""`task_type` 注册表：P0 只接 `PARSE_PAPER` 与 `INDEX_PAPER`（09 P0-7 输出行）。

注册表存在的意义是"没注册的类型必须显式失败"：Go 发一个 Python 不认识的任务，
必须是 `UNSUPPORTED_TASK_TYPE`（retryable=false），而不是走到某个看起来能跑的默认分支。
两种类型都复用现成能力（`document_loader` / `milvus_writer`），不重写解析或写入逻辑。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.config import UPLOAD_DIR
from backend.core.dependencies import get_document_loader
from backend.core.logging_config import get_logger
from backend.services.document_jobs import index_document

logger = get_logger(__name__)
from backend.internal_api.schemas import ExecuteRequest, Usage


class TaskError(Exception):
    """任务执行失败，带内部错误码；router 据此写 `errors[]` 并把行置 failed。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass
class Outcome:
    result: dict
    proposed_tasks: list[dict] = field(default_factory=list)
    evidence_candidates: list[dict] = field(default_factory=list)
    usage: Usage = field(default_factory=lambda: Usage(calls=0, tokens=0, cost=0))


@dataclass(frozen=True)
class TaskSpec:
    task_type: str
    handler: Callable[[ExecuteRequest], Outcome]


def _resolve_filename(payload: dict | None) -> str:
    """`inputs` 只传引用不传字节，所以这里只接受托管上传目录里的文件名。

    取 `Path(...).name` 不是多余的防御：文件名来自调用方，`../` 会让解析器读到目录外的文件。
    """
    if not payload or not isinstance(payload.get("filename"), str) or not payload["filename"].strip():
        raise TaskError("INVALID_PAYLOAD", "payload.filename 必填（PARSE_PAPER/INDEX_PAPER 以文件名为引用）")
    name = payload["filename"]
    if Path(name).name != name or any(char in name for char in ("/", "\\", ":", "\x00")):
        raise TaskError("INVALID_PAYLOAD", "filename 不得包含路径段")
    return name


def _load(path: Path, filename: str) -> list[dict]:
    loader = get_document_loader()
    try:
        documents = loader.load_document(str(path), filename)
        if not documents:
            raise ValueError("未提取到文档内容")
        return documents
    except Exception as exc:  # 解析失败统一归 PARSE_FAILED：同一份文件重试必然同样失败
        logger.exception("内部文档解析失败: filename=%s", filename)
        raise TaskError("PARSE_FAILED", "文档解析失败") from exc


def parse_paper(req: ExecuteRequest) -> Outcome:
    filename = _resolve_filename(req.payload)
    path = UPLOAD_DIR / filename
    if not path.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        raise TaskError("INVALID_PAYLOAD", "filename 不得引用上传目录外的文件")
    if not path.is_file():
        raise TaskError("PARSE_FAILED", f"待解析文件不存在：{filename}")
    documents = _load(path, filename)
    return Outcome(result={"filename": filename, "chunk_count": len(documents), "parsed": True})


def index_paper(req: ExecuteRequest) -> Outcome:
    filename = _resolve_filename(req.payload)
    path = UPLOAD_DIR / filename
    if not path.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        raise TaskError("INVALID_PAYLOAD", "filename 不得引用上传目录外的文件")
    if not path.is_file():
        raise TaskError("PARSE_FAILED", f"待索引文件不存在：{filename}")
    try:
        counts = index_document(str(path), filename)
    except ValueError as exc:
        raise TaskError("PARSE_FAILED", "文档内容无法索引") from exc
    except Exception as exc:
        logger.exception("内部文档索引失败: filename=%s", filename)
        raise TaskError("INDEX_UNAVAILABLE", "文档索引依赖暂不可用") from exc
    return Outcome(result={"filename": filename, "indexed_chunks": counts["leaf_count"], "indexed": True})



REGISTRY: dict[str, TaskSpec] = {
    "PARSE_PAPER": TaskSpec("PARSE_PAPER", parse_paper),
    "INDEX_PAPER": TaskSpec("INDEX_PAPER", index_paper),
}


def registered_task_types() -> list[str]:
    return sorted(REGISTRY)
