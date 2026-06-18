"""Citation verification system for academic paper RAG."""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def extract_citations(answer: str) -> list[dict]:
    """从答案中提取引用"""
    citations = []
    pattern = r'\[([^\]]+\.pdf\s*\(p\.\d+\))\]'
    for match in re.finditer(pattern, answer):
        citations.append({"text": match.group(1), "span": match.span()})
    return citations


def verify_citations(
    citations: list[dict],
    retrieved_locators: list[str],
    evidence: list[dict]
) -> tuple[list[dict], list[dict]]:
    """验证引用是否与检索内容匹配
    
    Returns:
        (verified_citations, unsupported_citations)
    """
    verified = []
    unsupported = []
    
    for citation in citations:
        citation_text = citation["text"]
        is_verified = False
        
        for locator in retrieved_locators:
            if _locator_matches(citation_text, locator):
                is_verified = True
                citation["locator"] = locator
                break
        
        if is_verified:
            verified.append(citation)
        else:
            unsupported.append(citation)
            logger.warning("Unsupported citation: %s", citation_text)
    
    return verified, unsupported


def _locator_matches(citation_text: str, locator: str) -> bool:
    """检查引用文本是否匹配检索器的 locator"""
    # 提取文件名和页码
    citation_match = re.match(r'(.+?)\s*\(p\.(\d+)\)', citation_text)
    locator_match = re.match(r'(.+?)\s*\(p\.(\d+)\)', locator)
    
    if not citation_match or not locator_match:
        return citation_text.lower() in locator.lower()
    
    c_file, c_page = citation_match.groups()
    l_file, l_page = locator_match.groups()
    
    return c_file.lower() == l_file.lower() and c_page == l_page


def extract_outcome(
    messages: list,
    retrieved_locators: list[str],
    evidence: list[dict]
) -> dict:
    """从 agent 输出中提取最终结果并验证引用"""
    final_answer = ""
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
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
    verified, unsupported = verify_citations(citations, retrieved_locators, evidence)
    
    return {
        "answer": final_answer,
        "citations": [c["text"] for c in verified],
        "unsupported": [c["text"] for c in unsupported],
        "verified_count": len(verified),
        "unsupported_count": len(unsupported),
    }
