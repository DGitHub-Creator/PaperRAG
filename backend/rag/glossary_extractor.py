"""缩略语/术语提取器 —— 从论文文本中提取首字母缩写词及其全称。

常见学术模式:
  - "Long Definition (LDD)" — 全称紧跟括号内缩写
  - "Abbreviation (ABBR)" — 缩写跟在定义后的括号中
  - "LDD/ldd" — 全称/缩写格式
"""

import re
from typing import NamedTuple


class GlossaryEntry(NamedTuple):
    term: str
    definition: str
    line_index: int


# 匹配 "Long Definition (ABBR)" 或 "Definition (ABBR)"
_RE_DEFINITION_ACRONYM = re.compile(
    r"([A-Z][a-zA-Z\s\-]+?)\s*\(([A-Z]{2,})\)"
)

# 匹配 "ABBR: Long Definition" 或 "ABBR — Long Definition"
_RE_ACRONYM_DEFINITION = re.compile(
    r"([A-Z]{2,})\s*[:\-–—]\s*([A-Z][a-zA-Z\s\-]+)"
)


def extract_glossary(text: str) -> list[GlossaryEntry]:
    """从文本中提取缩略语-全称对。

    策略:
      1. 查找 "Definition (ABBR)" 模式
      2. 查找 "ABBR: Definition" 模式
      3. 去重（同一缩写只保留首次出现）

    Args:
        text: 论文文本。

    Returns:
        GlossaryEntry 列表，按出现顺序排列。
    """
    entries: list[GlossaryEntry] = []
    seen_terms: set[str] = set()

    for i, line in enumerate(text.split("\n")):
        line = line.strip()
        if not line:
            continue

        # "Long Definition (ABBR)"
        for m in _RE_DEFINITION_ACRONYM.finditer(line):
            definition = m.group(1).strip()
            term = m.group(2).strip()
            if term not in seen_terms:
                seen_terms.add(term)
                entries.append(GlossaryEntry(term=term, definition=definition, line_index=i))

        # "ABBR: Long Definition"
        for m in _RE_ACRONYM_DEFINITION.finditer(line):
            term = m.group(1).strip()
            definition = m.group(2).strip()
            if term not in seen_terms:
                seen_terms.add(term)
                entries.append(GlossaryEntry(term=term, definition=definition, line_index=i))

    return entries


def has_glossary(text: str) -> bool:
    """检查文本是否包含缩略语定义。"""
    return bool(
        _RE_DEFINITION_ACRONYM.search(text)
        or _RE_ACRONYM_DEFINITION.search(text)
    )
