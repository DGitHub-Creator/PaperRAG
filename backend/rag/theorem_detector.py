"""定理/证明检测 —— 识别学术论文中的定理、引理、证明等关键结构。

采用两级检测策略:
    1. 行级结构扫描: 匹配 Markdown heading / 列表项 / 粗体开头的定理或证明声明行。
       精确匹配，低误报率。覆盖 ``## Theorem 3.1``、``- Lemma 2.``、``**Proof.**`` 等格式。
    2. 正文关键词回退: 在第一级未命中时，搜索前 8000 字符内的关键词。
       用于捕获内联引用（如 "by Theorem 5, we have..."）。

使用示例:
    >>> from backend.rag.theorem_detector import detect_theorem_proof
    >>> has_theorem, has_proof = detect_theorem_proof(parent_text)
"""

import re

from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# ── 正文回退用关键词（仅在第一级行扫描未命中时使用）─────────────────
# 匹配学术论文中常见的定理类结构名称
_RE_THEOREM_BODY = re.compile(
    r"\b(?:Theorem|Lemma|Proposition|Claim|Corollary|Conjecture|Definition|"
    r"Assumption|Fact)\b",
    re.IGNORECASE,
)

# 匹配证明类结构名称
_RE_PROOF_BODY = re.compile(
    r"\b(?:Proof|Proof\s+(?:Sketch|Overview|Outline|Idea))\b",
    re.IGNORECASE,
)

# ── 行级结构模式（精确匹配声明行，低误报）──────────────────────────
# 覆盖密码学/CS 论文常见写法:
#   ## Theorem 3.1 (UC-secure Key Exchange) ...
#   - Theorem 1. The ISO 9798-3 ...
#   **Theorem 2.** Any protocol that ...
#   *Theorem 3.* ...
#   Theorem 4. ...
#   ### Proof ...
#   - Proof. ...
#   **Proof.** ...

# 定理/引理/定义声明行模式:
#   行首可选 # 标记 -> 可选列表符号(- * +) -> 可选粗体 -> 定理关键词 -> 可选编号 -> 终止符
_RE_THEOREM_LINE = re.compile(
    r"^\s*"
    r"(?:#+\s*)?"              # 可选 Markdown heading 前缀: ##, ### 等
    r"(?:[-*+]\s+)?"           # 可选列表标记: -, *, +
    r"(?:\*\*|__)?"            # 可选粗体开始: ** 或 __
    r"\s*"
    r"(?:Theorem|Lemma|Proposition|Claim|Corollary|Conjecture|Definition|"
    r"Assumption|Fact)"
    r"(?:\s+\d+(?:\.\d+)*)?"   # 可选编号: 1, 3.1, 2.1.3
    r"[.,:\s]",                # 声明终止符（空格/句号/冒号）
    re.IGNORECASE,
)

# 证明声明行模式: 结构同定理模式
_RE_PROOF_LINE = re.compile(
    r"^\s*"
    r"(?:#+\s*)?"
    r"(?:[-*+]\s+)?"
    r"(?:\*\*|__)?"
    r"\s*"
    r"(?:Proof|Proof\s+(?:Sketch|Overview|Outline|Idea))"
    r"[.,:\s]",
    re.IGNORECASE,
)


def detect_theorem_proof(text: str) -> tuple[bool, bool]:
    """检测文本中是否包含定理类结构和证明段落。

    两级检测策略:
        1. **行级结构扫描**: 逐行匹配 heading / 列表项 / 粗体开头的定理/证明声明行。
           精确、低误报。覆盖 ``##`` 标题、``- Theorem`` 列表、``**Theorem**`` 粗体等格式。
        2. **正文关键词回退**: 若行级未命中，在前 8000 字符内搜索关键词。
           捕获内联引用（如 "by Theorem 5..."）。

    Args:
        text: 父块（parent）的完整文本。

    Returns:
        (has_theorem, has_proof): 两个布尔值，分别表示是否包含定理和证明。
    """
    has_theorem = False
    has_proof = False

    # 第一级: 行级结构模式扫描 —— 精确匹配声明行
    for line in text.split("\n"):
        if not has_theorem and _RE_THEOREM_LINE.match(line):
            has_theorem = True
        if not has_proof and _RE_PROOF_LINE.match(line):
            has_proof = True
        if has_theorem and has_proof:
            return True, True

    # 第二级: 正文关键词回退（仅在第一级未命中时）—— 捕获内联引用
    search_span = text[:8000]
    if not has_theorem and _RE_THEOREM_BODY.search(search_span):
        has_theorem = True
    if not has_proof and _RE_PROOF_BODY.search(search_span):
        has_proof = True

    return has_theorem, has_proof
