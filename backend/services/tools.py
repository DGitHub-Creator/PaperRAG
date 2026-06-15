"""
工具模块 —— Agent 工具函数定义与 RAG 状态管理。

本模块为 LangChain Agent 提供可调用的工具函数，并管理跨工具的全局状态：

  1. get_current_weather: 调用高德地图天气 API 获取实时天气 / 天气预报。
  2. search_knowledge_base: 调用 RAG 流水线执行混合检索（密集 + 稀疏向量）。

全局状态管理：
  - _LAST_RAG_CONTEXT: 存储最近一次 RAG 检索的上下文（含 rag_trace）。
  - _KNOWLEDGE_TOOL_CALLS_THIS_TURN: 限制每轮对话中知识库工具调用次数。
  - _RAG_STEP_QUEUE / _RAG_STEP_LOOP: 用于流式对话时跨线程推送 RAG 步骤。

跨线程安全设计：
  emit_rag_step 通过 call_soon_threadsafe 将 RAG 步骤推入 asyncio.Queue，
  使得运行在线程池中的同步工具也能向主事件循环中的流式输出管道推送事件。
"""

import asyncio
from typing import Optional

import requests
from langchain_core.tools import tool

from backend.core.config import AMAP_WEATHER_API, AMAP_API_KEY
from backend.core.logging_config import get_logger
from backend.rag.rag_pipeline import run_rag_graph

logger = get_logger(__name__)

# ── 全局状态变量（进程级单例） ───────────────────────────────────────

_LAST_RAG_CONTEXT: Optional[dict] = None
"""最近一次 RAG 检索的上下文（包含 rag_trace 等追踪信息）。"""

_KNOWLEDGE_TOOL_CALLS_THIS_TURN: int = 0
"""当前轮次中 search_knowledge_base 工具的调用次数，用于限流。"""

_RAG_STEP_QUEUE = None
"""RAG 步骤队列（asyncio.Queue 或其代理），由 agent 模块在流式对话前设置。"""

_RAG_STEP_LOOP = None
"""当前 asyncio 事件循环引用，用于跨线程安全调度。"""


def _set_last_rag_context(context: dict) -> None:
    """设置最近一次 RAG 检索上下文（内部函数）。

    Args:
        context: 包含 rag_trace 等字段的上下文字典。
    """
    global _LAST_RAG_CONTEXT
    _LAST_RAG_CONTEXT = context


def get_last_rag_context(clear: bool = True) -> Optional[dict]:
    """获取最近一次 RAG 检索上下文，默认读取后清空。

    设计为读取即清空，防止跨请求污染。

    Args:
        clear: 是否在读取后清空（默认 True）。

    Returns:
        RAG 上下文字典，无则返回 None。
    """
    global _LAST_RAG_CONTEXT
    context = _LAST_RAG_CONTEXT
    if clear:
        _LAST_RAG_CONTEXT = None
    return context


def reset_tool_call_guards() -> None:
    """每轮对话开始时重置工具调用计数。

    应由 Agent 主循环在每次用户请求前调用，
    确保 search_knowledge_base 的限制在新一轮对话中重新计数。
    """
    global _KNOWLEDGE_TOOL_CALLS_THIS_TURN
    _KNOWLEDGE_TOOL_CALLS_THIS_TURN = 0


def set_rag_step_queue(queue) -> None:
    """设置 RAG 步骤队列，并捕获当前事件循环以便跨线程调度。

    在流式对话开始前，Agent 模块调用本函数注入 asyncio.Queue（或代理对象）。
    emit_rag_step 随后通过 call_soon_threadsafe 将步骤推入该队列。

    Args:
        queue: asyncio.Queue 实例或实现了 put_nowait 的代理对象。
               传 None 表示清除队列引用（停止推送）。
    """
    global _RAG_STEP_QUEUE, _RAG_STEP_LOOP
    _RAG_STEP_QUEUE = queue
    if queue:
        try:
            _RAG_STEP_LOOP = asyncio.get_running_loop()
        except RuntimeError:
            # 不在事件循环中运行时的 fallback
            _RAG_STEP_LOOP = asyncio.get_event_loop()
    else:
        _RAG_STEP_LOOP = None


def emit_rag_step(icon: str, label: str, detail: str = "") -> None:
    """向流式输出队列发送一个 RAG 检索步骤事件。

    本函数可在任意线程中调用（同步工具运行在线程池时），
    通过 call_soon_threadsafe 将步骤推入主事件循环中的输出队列。

    Args:
        icon: 步骤图标标识（如 "search", "filter", "merge"）。
        label: 步骤简短描述（如 "混合检索", "重排序"）。
        detail: 步骤详细信息（如 "召回 30 条候选"）。
    """
    global _RAG_STEP_QUEUE, _RAG_STEP_LOOP
    if _RAG_STEP_QUEUE is not None and _RAG_STEP_LOOP is not None:
        step = {"icon": icon, "label": label, "detail": detail}
        try:
            if not _RAG_STEP_LOOP.is_closed():
                _RAG_STEP_LOOP.call_soon_threadsafe(
                    _RAG_STEP_QUEUE.put_nowait, step
                )
        except Exception:
            logger.debug("emit_rag_step 推送失败", exc_info=True)


# ── Agent 工具函数 ──────────────────────────────────────────────────


def get_current_weather(location: str, extensions: Optional[str] = "base") -> str:
    """获取指定城市的天气信息（高德地图 API）。

    支持两种查询模式：
      - base: 实时天气（温度、湿度、风向、风力）
      - all:  天气预报（今日白天/夜间天气、气温范围）

    Args:
        location: 城市名称或行政区划代码（如 "北京"、"110000"）。
        extensions: 查询类型，"base" 为实时天气，"all" 为天气预报。默认为 "base"。

    Returns:
        格式化后的天气信息字符串，发生错误时返回错误描述字符串。

    配置依赖（从 backend.core.config 导入）：
      - AMAP_WEATHER_API: 高德天气 API 端点 URL
      - AMAP_API_KEY: 高德 API 密钥
    """
    if not location:
        return "location参数不能为空"
    if extensions not in ("base", "all"):
        return "extensions参数错误，请输入base或all"

    if not AMAP_WEATHER_API or not AMAP_API_KEY:
        logger.warning("天气服务未配置（缺少 AMAP_WEATHER_API 或 AMAP_API_KEY）")
        return "天气服务未配置（缺少 AMAP_WEATHER_API 或 AMAP_API_KEY）"

    params = {
        "key": AMAP_API_KEY,
        "city": location,
        "extensions": extensions,
        "output": "json",
    }

    try:
        resp = requests.get(AMAP_WEATHER_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            return f"查询失败：{data.get('info', '未知错误')}"

        if extensions == "base":
            # 实时天气
            lives = data.get("lives", [])
            if not lives:
                return f"未查询到 {location} 的天气数据"
            w = lives[0]
            return (
                f"【{w.get('city', location)} 实时天气】\n"
                f"天气状况：{w.get('weather', '未知')}\n"
                f"温度：{w.get('temperature', '未知')}℃\n"
                f"湿度：{w.get('humidity', '未知')}%\n"
                f"风向：{w.get('winddirection', '未知')}\n"
                f"风力：{w.get('windpower', '未知')}级\n"
                f"更新时间：{w.get('reporttime', '未知')}"
            )

        # 天气预报
        forecasts = data.get("forecasts", [])
        if not forecasts:
            return f"未查询到 {location} 的天气预报数据"
        f0 = forecasts[0]
        out = [
            f"【{f0.get('city', location)} 天气预报】",
            f"更新时间：{f0.get('reporttime', '未知')}",
            "",
        ]
        today = (f0.get("casts") or [])[0] if f0.get("casts") else {}
        out += [
            "今日天气：",
            f"  白天：{today.get('dayweather', '未知')}",
            f"  夜间：{today.get('nightweather', '未知')}",
            f"  气温：{today.get('nighttemp', '未知')}~{today.get('daytemp', '未知')}℃",
        ]
        return "\n".join(out)

    except requests.exceptions.Timeout:
        logger.error("天气服务请求超时: location=%s", location)
        return "错误：请求天气服务超时"
    except requests.exceptions.RequestException as e:
        logger.error("天气服务请求失败: location=%s, error=%s", location, e)
        return f"错误：天气服务请求失败 - {e}"
    except Exception as e:
        logger.exception("天气数据解析失败: location=%s", location)
        return f"错误：解析天气数据失败 - {e}"


@tool("search_knowledge_base")
def search_knowledge_base(query: str) -> str:
    """在知识库中搜索信息，使用混合检索（密集向量 + BM25 稀疏向量）。

    本工具被 LangChain Agent 调用，执行完整的 RAG 检索流水线：
    查询扩展 -> 混合检索 -> 重排序 -> 自动合并 -> 上下文扩展。

    调用限制：每轮对话最多调用一次，防止 Agent 陷入无限检索循环。

    Args:
        query: 用户的问题或搜索查询字符串。

    Returns:
        格式化后的检索结果字符串，包含来源文档、页码和文本内容。
        若未检索到相关文档，返回提示信息。
    """
    global _KNOWLEDGE_TOOL_CALLS_THIS_TURN

    # 每轮最多调用一次的限制守卫
    if _KNOWLEDGE_TOOL_CALLS_THIS_TURN >= 1:
        return (
            "TOOL_CALL_LIMIT_REACHED: search_knowledge_base has already been called once in this turn. "
            "Use the existing retrieval result and provide the final answer directly."
        )
    _KNOWLEDGE_TOOL_CALLS_THIS_TURN += 1

    logger.info("知识库检索开始: query='%s'", query[:100])

    # 运行 RAG 流水线
    rag_result = run_rag_graph(query)

    docs = rag_result.get("docs", []) if isinstance(rag_result, dict) else []
    rag_trace = rag_result.get("rag_trace", {}) if isinstance(rag_result, dict) else {}

    # 保存 RAG 追踪信息（供 Agent 关联到对话消息）
    if rag_trace:
        _set_last_rag_context({"rag_trace": rag_trace})

    if not docs:
        logger.info("知识库检索无结果: query='%s'", query[:100])
        return "No relevant documents found in the knowledge base."

    # 格式化检索结果
    formatted = []
    for i, result in enumerate(docs, 1):
        source = result.get("filename", "Unknown")
        page = result.get("page_number", "N/A")
        text = result.get("text", "")
        formatted.append(f"[{i}] {source} (Page {page}):\n{text}")

    logger.info("知识库检索完成: query='%s', 命中 %d 条", query[:100], len(docs))
    return "Retrieved Chunks:\n" + "\n\n---\n\n".join(formatted)
