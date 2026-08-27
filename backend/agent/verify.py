"""Citation verification system for academic paper RAG.

答案中的引用使用 ``[Source N]`` 标签格式，与 ``search_knowledge_base``
工具返回给模型的检索块标签一一对应。工具同时把 ``source_map``（N → 文件/页码/
chunk_id 的映射）写入请求级上下文；校验时检查答案里引用的每个标签是否都能
映射回真实检索到的分块，从而拦截模型编造的引用。

主要入口：
  - extract_citations(answer): 提取答案中的 ``[Source N]`` 引用
  - verify_citations(citations, source_map): 对照 source_map 验证
  - extract_outcome(messages, source_map): 从 Agent 输出中提取最终答案并验证
"""

import logging
import re

logger = logging.getLogger(__name__)

# 匹配 [Source 3] / [source 3] / [ Source 3 ]
_CITATION_RE = re.compile(r"\[\s*Source\s+(\d+)\s*\]", re.IGNORECASE)


def extract_citations(answer: str) -> list[dict]:
    """从答案中提取 ``[Source N]`` 引用（去重、保持出现顺序）。"""
    citations = []
    seen: set[str] = set()
    for match in _CITATION_RE.finditer(answer or ""):
        label = f"Source {match.group(1)}"
        if label in seen:
            continue
        seen.add(label)
        citations.append({"text": label, "span": match.span()})
    return citations


def verify_citations(
    citations: list[dict],
    source_map: dict | None,
) -> tuple[list[dict], list[dict]]:
    """验证引用是否映射到真实检索到的分块。

    Args:
        citations: extract_citations 的输出。
        source_map: ``search_knowledge_base`` 工具提供的映射，
            形如 ``{"Source 1": {"filename":..., "page":..., "chunk_id":...}}``。

    Returns:
        (verified_citations, unsupported_citations)。
        verified 项附带 ``locator`` 字段（filename/page/chunk_id）。
    """
    verified = []
    unsupported = []
    mapping = source_map or {}

    for citation in citations:
        label = citation["text"]
        locator = mapping.get(label)
        if locator:
            enriched = dict(citation)
            enriched["locator"] = {
                "filename": locator.get("filename"),
                "page": locator.get("page"),
                "chunk_id": locator.get("chunk_id"),
            }
            verified.append(enriched)
        else:
            unsupported.append(citation)
            logger.warning("Unsupported citation: %s (not in source_map)", label)

    return verified, unsupported


def _format_citation(citation: dict) -> dict:
    """把校验通过的引用格式化为 CitationInfo 兼容的字典。"""
    locator = citation.get("locator") or {}
    return {
        "source_label": citation["text"],
        "filename": locator.get("filename"),
        "page": locator.get("page"),
        "chunk_id": locator.get("chunk_id"),
        "supported": True,
    }


def _format_unsupported(citation: dict) -> dict:
    """把未通过的引用格式化为 CitationInfo 兼容的字典。"""
    return {
        "source_label": citation["text"],
        "supported": False,
        "reason": "引用的来源编号不在本次检索结果中",
    }


def extract_outcome(messages: list, source_map: dict | None = None) -> dict:
    """从 agent 输出中提取最终结果并验证引用。

    优先从 ``Answer`` 工具调用参数中取最终答案；否则回退到最后一条
    有内容的 AI 消息。
    """
    final_answer = ""
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls or []:
                if tc["name"] == "Answer":
                    final_answer = tc["args"].get("answer", "")
                    break
        if final_answer:
            break

    if not final_answer:
        for msg in reversed(messages):
            content = getattr(msg, "content", "")
            if content and "out_of_scope" not in str(content):
                final_answer = content
                break

    citations = extract_citations(final_answer)
    verified, unsupported = verify_citations(citations, source_map)

    return {
        "answer": final_answer,
        "citations": [_format_citation(c) for c in verified],
        "unsupported": [_format_unsupported(c) for c in unsupported],
        "verified_count": len(verified),
        "unsupported_count": len(unsupported),
    }
