"""
工具模块 —— Agent 工具函数定义与 RAG 状态管理。

本模块为 LangChain Agent 提供可调用的工具函数，并管理跨工具的请求级状态：

  1. search_knowledge_base: 调用 RAG 流水线执行混合检索（密集 + 稀疏向量），
     返回带 ``[Source N]`` 标签的检索块供模型引用。

状态管理使用 contextvars 替代模块级全局变量，确保：
  - asyncio 多任务间隔离（每个请求有独立上下文）
  - 跨线程安全（contextvars 自动传播到线程池）
  - 无需 global 关键字，类型检查更友好
"""

import asyncio
import contextvars

from langchain_core.tools import tool

from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# ── contextvars 上下文变量（替代进程级全局变量） ────────────────────

_rag_context_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "_rag_context_var", default=None
)
"""最近一次 RAG 检索的上下文（包含 rag_trace/source_map），按请求隔离。"""

_knowledge_calls_var: contextvars.ContextVar[int] = contextvars.ContextVar(
    "_knowledge_calls_var", default=0
)
"""当前轮次中 search_knowledge_base 工具的调用次数，按请求隔离。"""

_rag_step_queue_var: contextvars.ContextVar = contextvars.ContextVar(
    "_rag_step_queue_var", default=None
)
"""RAG 步骤队列（asyncio.Queue 或其代理），按请求隔离。"""

_rag_step_loop_var: contextvars.ContextVar = contextvars.ContextVar(
    "_rag_step_loop_var", default=None
)
"""当前 asyncio 事件循环引用，按请求隔离。"""

_conversation_history_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_conversation_history_var", default=""
)
"""当前轮次的历史对话摘要（最近 2 轮 Q&A），供 RAG 检索做上下文感知。"""


def set_conversation_history(history: str) -> None:
    """设置当前轮次的历史对话摘要。

    Agent 入口（run_agent / run_agent_stream）在每轮对话开始前调用，
    search_knowledge_base 检索时读取，用于多轮上下文感知检索。

    Args:
        history: 历史对话摘要文本（如 "用户: ... AI: ..."），可为空字符串。
    """
    _conversation_history_var.set(history or "")


def get_conversation_history() -> str:
    """获取当前轮次的历史对话摘要。"""
    return _conversation_history_var.get()


def _set_last_rag_context(context: dict) -> None:
    """设置最近一次 RAG 检索上下文（当前请求上下文内）。

    Args:
        context: 包含 rag_trace/source_map 等字段的上下文字典。
    """
    _rag_context_var.set(context)


def get_last_rag_context(clear: bool = True) -> dict | None:
    """获取最近一次 RAG 检索上下文，默认读取后清空。

    设计为读取即清空，防止跨请求污染。

    Args:
        clear: 是否在读取后清空（默认 True）。

    Returns:
        RAG 上下文字典，无则返回 None。
    """
    context = _rag_context_var.get()
    if clear:
        _rag_context_var.set(None)
    return context


def reset_tool_call_guards() -> None:
    """每轮对话开始时重置工具调用计数。

    当前请求上下文中重置计数器，
    确保 search_knowledge_base 的限制在新一轮对话中重新计数。
    """
    _knowledge_calls_var.set(0)


def set_rag_step_queue(queue) -> None:
    """设置 RAG 步骤队列，并捕获当前事件循环以便跨线程调度。

    在流式对话开始前，Agent 模块调用本函数注入 asyncio.Queue（或代理对象）。
    emit_rag_step 随后通过 call_soon_threadsafe 将步骤推入该队列。

    Args:
        queue: asyncio.Queue 实例或实现了 put_nowait 的代理对象。
               传 None 表示清除队列引用（停止推送）。
    """
    _rag_step_queue_var.set(queue)
    if queue:
        try:
            _rag_step_loop_var.set(asyncio.get_running_loop())
        except RuntimeError:
            _rag_step_loop_var.set(asyncio.get_event_loop())
    else:
        _rag_step_loop_var.set(None)


def emit_rag_step(icon: str, label: str, detail: str = "") -> None:
    """向流式输出队列发送一个 RAG 检索步骤事件。

    本函数可在任意线程中调用（同步工具运行在线程池时），
    通过 call_soon_threadsafe 将步骤推入主事件循环中的输出队列。

    Args:
        icon: 步骤图标标识（如 "search", "filter", "merge"）。
        label: 步骤简短描述（如 "混合检索", "重排序"）。
        detail: 步骤详细信息（如 "召回 30 条候选"）。
    """
    queue = _rag_step_queue_var.get()
    loop = _rag_step_loop_var.get()
    if queue is not None and loop is not None:
        step = {"icon": icon, "label": label, "detail": detail}
        try:
            if not loop.is_closed():
                loop.call_soon_threadsafe(queue.put_nowait, step)
        except Exception:
            logger.debug("emit_rag_step 推送失败", exc_info=True)


# ── Agent 工具函数 ──────────────────────────────────────────────────


@tool("search_knowledge_base")
def search_knowledge_base(query: str) -> str:
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
    # 每轮最多调用一次的限制守卫（基于 contextvars，请求隔离）
    calls = _knowledge_calls_var.get()
    if calls >= 1:
        return (
            "TOOL_CALL_LIMIT_REACHED: search_knowledge_base has already been called once in this turn. "
            "Use the existing retrieval result and provide the final answer directly."
        )
    _knowledge_calls_var.set(calls + 1)

    logger.info("知识库检索开始: query='%s'", query[:100])

    # 运行 RAG 流水线（延迟导入，避免与 rag_pipeline 的 import 产生循环依赖）
    from backend.rag.rag_pipeline import run_rag_graph  # noqa: C0415
    rag_result = run_rag_graph(
        query,
        conversation_history=get_conversation_history(),
    )

    docs = rag_result.get("docs", []) if isinstance(rag_result, dict) else []
    rag_trace = rag_result.get("rag_trace", {}) if isinstance(rag_result, dict) else {}

    if not docs:
        logger.info("知识库检索无结果: query='%s'", query[:100])
        if rag_trace:
            _set_last_rag_context({"rag_trace": rag_trace, "source_map": {}})
        return "No relevant documents found in the knowledge base."

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
    _set_last_rag_context({
        "rag_trace": rag_trace,
        "source_map": source_map,
    })

    logger.info("知识库检索完成: query='%s', 命中 %d 条", query[:100], len(docs))
    return "Retrieved Chunks:\n" + "\n\n---\n\n".join(formatted)
