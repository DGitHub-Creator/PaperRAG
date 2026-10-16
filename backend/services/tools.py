"""Agent 检索工具：文本给模型，artifact 给执行图；请求上下文只保存输入和事件队列。"""

import asyncio
import contextvars

from langchain_core.tools import tool

from backend.core.logging_config import get_logger

logger = get_logger(__name__)
_rag_step_queue_var: contextvars.ContextVar = contextvars.ContextVar("rag_step_queue", default=None)
_rag_step_loop_var: contextvars.ContextVar = contextvars.ContextVar("rag_step_loop", default=None)
_conversation_history_var: contextvars.ContextVar[str] = contextvars.ContextVar("conversation_history", default="")


def set_conversation_history(history: str) -> None:
    _conversation_history_var.set(history or "")


def get_conversation_history() -> str:
    return _conversation_history_var.get()


def set_rag_step_queue(queue) -> None:
    _rag_step_queue_var.set(queue)
    try:
        loop = asyncio.get_running_loop() if queue is not None else None
    except RuntimeError:
        loop = None
    _rag_step_loop_var.set(loop)


def emit_rag_step(icon: str, label: str, detail: str = "") -> None:
    queue, loop = _rag_step_queue_var.get(), _rag_step_loop_var.get()
    if queue is None or loop is None:
        return

    def deliver():
        try:
            queue.put_nowait({"icon": icon, "label": label, "detail": detail})
        except asyncio.QueueFull:
            logger.warning("检索步骤队列已满，丢弃本条进度事件")

    try:
        loop.call_soon_threadsafe(deliver)
    except RuntimeError:
        logger.debug("客户端已断开，停止推送检索步骤")


@tool("search_knowledge_base", response_format="content_and_artifact")
def search_knowledge_base(query: str) -> tuple[str, dict]:
    """在知识库中搜索信息，使用混合检索（密集向量 + BM25 稀疏向量）。

    本工具被 LangChain Agent 调用，执行完整的 RAG 检索流水线：
    查询扩展 -> 混合检索 -> 重排序 -> 自动合并 -> 上下文扩展。

    调用限制：每轮对话最多调用一次，防止 Agent 陷入无限检索循环。

    Args:
        query: 用户的问题或搜索查询字符串。

    Returns:
        格式化后的检索结果字符串，每个分块带 ``[Source N]`` 标签
        （含来源文档、页码和文本内容），供模型在答案中引用。
        若未检索到相关文档，返回提示信息。
    """
    logger.info("知识库检索开始: query='%s'", query[:100])

    # 运行 RAG 流水线（延迟导入，避免与 rag_pipeline 的 import 产生循环依赖）
    from backend.rag.workflow import run_rag_graph  # noqa: C0415
    rag_result = run_rag_graph(
        query,
        conversation_history=get_conversation_history(),
    )

    docs = rag_result.get("docs", []) if isinstance(rag_result, dict) else []
    rag_trace = rag_result.get("rag_trace", {}) if isinstance(rag_result, dict) else {}

    if not docs:
        return "No relevant documents found in the knowledge base.", {"rag_trace": rag_trace, "source_map": {}}

    # 格式化检索结果（含 Source 编号，供 Agent 引用）
    formatted = []
    source_map = {}
    for i, result in enumerate(docs, 1):
        source = result.get("filename", "Unknown")
        page = result.get("page_number", "N/A")
        chunk_id = result.get("chunk_id", "")
        text = result.get("text", "")
        formatted.append(f"[Source {i}] {source} (Page {page}):\n{text}")
        source_map[f"Source {i}"] = {
            "filename": source,
            "page": page,
            "chunk_id": chunk_id,
        }

    # 保存 source_map 到 RAG 上下文，供引用校验与前端展示使用
    rag_trace = dict(rag_trace or {})
    rag_trace["source_map"] = source_map
    logger.info("知识库检索完成: query='%s', 命中 %d 条", query[:100], len(docs))
    return "Retrieved Chunks:\n" + "\n\n---\n\n".join(formatted), {"rag_trace": rag_trace, "source_map": source_map}
