"""引文提取器 —— 从论文文本中提取结构化引文标注。

支持的引文格式:
  - [1], [1,2,3], [1-3] (数字编号)
  - [Author, Year], [Author et al., Year]
  - (Author, Year), (Author et al., Year)
  - Author (Year)
  - \\cite{label} (LaTeX)
"""

import re
from typing import NamedTuple


class Citation(NamedTuple):
    raw: str
    index: int


_RE_BRACKET_NUM = re.compile(r"\[(\d+(?:\s*[,–\-]\s*\d+)*)\]")
_RE_BRACKET_AUTHOR_YEAR = re.compile(
    r"\[([A-Z][a-zA-Z.\-]+(?:\s+et\s+al\.?)?,\s*(\d{4})[a-z]?)\]"
)
_RE_PAREN_AUTHOR_YEAR = re.compile(
    r"\(([A-Z][a-zA-Z.\-]+(?:\s+et\s+al\.?)?,\s*(\d{4})[a-z]?)\)"
)
_RE_LATEX_CITE = re.compile(r"\\cite\{([^}]+)\}")
_RE_AUTHOR_PAREN_YEAR = re.compile(
    r"([A-Z][a-zA-Z.\-]+(?:\s+et\s+al\.?)?)\s*\((\d{4})[a-z]?\)"
)


def extract_citations(text: str) -> list[Citation]:
    """从文本中提取所有引文标注。

    支持数字编号、作者-年份、LaTeX cite 三种格式。
    每条引文记录其原始文本和在全文中的出现索引。

    Args:
        text: 论文文本。

    Returns:
        Citation 列表，按出现顺序排列。
    """
    citations: list[Citation] = []
    seen: set[str] = set()

    for i, line in enumerate(text.split("\n")):
        # LaTeX \cite{label}
        for m in _RE_LATEX_CITE.finditer(line):
            for label in m.group(1).split(","):
                raw = label.strip()
                if raw and raw not in seen:
                    seen.add(raw)
                    citations.append(Citation(raw=raw, index=i))

        # [1], [1,2], [1-3]
        for m in _RE_BRACKET_NUM.finditer(line):
            raw = m.group(1)
            if raw and raw not in seen:
                seen.add(raw)
                citations.append(Citation(raw=f"[{raw}]", index=i))

        # [Author, Year]
        for m in _RE_BRACKET_AUTHOR_YEAR.finditer(line):
            raw = m.group(0)
            if raw and raw not in seen:
                seen.add(raw)
                citations.append(Citation(raw=raw, index=i))

        # (Author, Year)
        for m in _RE_PAREN_AUTHOR_YEAR.finditer(line):
            raw = m.group(0)
            if raw and raw not in seen:
                seen.add(raw)
                citations.append(Citation(raw=raw, index=i))

        # Author (Year)
        for m in _RE_AUTHOR_PAREN_YEAR.finditer(line):
            raw = m.group(0)
            if raw and raw not in seen:
                seen.add(raw)
                citations.append(Citation(raw=raw, index=i))

    return citations


def extract_citation_refs(text: str) -> list[str]:
    """提取引文编号引用关系（如 [1], [1,2,3] → ["1", "2", "3"]）。

    Args:
        text: 包含数字引用的文本。

    Returns:
        引用的编号字符串列表。
    """
    refs: list[str] = []
    for m in _RE_BRACKET_NUM.finditer(text):
        content = m.group(1)
        for part in re.split(r"\s*[,–\-]\s*", content):
            part = part.strip()
            if part:
                refs.append(part)
    return refs


def has_citations(text: str) -> bool:
    """检查文本是否包含任何引文标注。"""
    return bool(
        _RE_BRACKET_NUM.search(text)
        or _RE_BRACKET_AUTHOR_YEAR.search(text)
        or _RE_PAREN_AUTHOR_YEAR.search(text)
        or _RE_LATEX_CITE.search(text)
        or _RE_AUTHOR_PAREN_YEAR.search(text)
    )


CITATION_PATTERNS = {
    "bracket_num": _RE_BRACKET_NUM,
    "bracket_author_year": _RE_BRACKET_AUTHOR_YEAR,
    "paren_author_year": _RE_PAREN_AUTHOR_YEAR,
    "latex_cite": _RE_LATEX_CITE,
    "author_paren_year": _RE_AUTHOR_PAREN_YEAR,
}
