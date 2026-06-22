"""LaTeX 公式标准化 —— 用于公式相似度比较和检索。

将不同写法但语义等价的 LaTeX 公式归一化为规范形式：
- 去除无关空格
- 统一指令大小写
- 合并连续 mathrm / text 括号内的空白差异
- 变量名脱敏（可选的通用化处理）
"""

import re

# ── 正则预编译 ──────────────────────────────────────────────────────────────

_RE_MULTI_SPACE = re.compile(r" {2,}")
_RE_LEADING_TRAILING_SPACE = re.compile(r"^\s+|\s+$")
_RE_COMMAND = re.compile(r"\\([a-zA-Z]+)")
_RE_LBRACE_COMMAND = re.compile(r"\\([a-zA-Z]+)\s*\{")
_RE_DOLLAR_MATH = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$")
_RE_ENV_MATH = re.compile(r"\\begin\{([a-z]+?\*?)\}(.+?)\\end\{\1\}", re.DOTALL)


def _strip_tex_comments(text: str) -> str:
    """移除 LaTeX 注释（以 % 开头到行末）。"""
    return re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)


def _normalize_whitespace(text: str) -> str:
    """规范化 LaTeX 空白：去除行首尾空白、压缩连续空格、去除公式内所有空格。"""
    text = _RE_LEADING_TRAILING_SPACE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _RE_MULTI_SPACE.sub(" ", text)
    # 去除公式内所有空格（LaTeX 公式中空格通常无语义）
    text = re.sub(r"(\s)", "", text)
    return text.strip()


def _unify_mathrm(text: str) -> str:
    """统一 \\mathrm{...} 和 \\text{...} 内部的空白差异。"""
    def _unify(m: re.Match) -> str:
        prefix = m.group(1)
        inner = m.group(2).strip()
        inner = _RE_MULTI_SPACE.sub(" ", inner)
        return f"\\{prefix}{{{inner}}}"
    return re.sub(r"\\(mathrm|text|textbf|textit)\s*\{([^}]*)\}", _unify, text)


def _normalize_command_case(text: str) -> str:
    """将 LaTeX 指令统一为小写（常见易混指令）。"""
    return _RE_COMMAND.sub(lambda m: "\\" + m.group(1).lower(), text)


def _simplify_fraction(text: str) -> str:
    """将 \\frac{a}{b} → a/b 以便于不同书写风格间的比较。"""
    return re.sub(
        r"\\frac\{([^}]*)\}\{([^}]*)\}",
        r"(\1)/(\2)",
        text,
    )


def _simplify_sqrt(text: str) -> str:
    """\\sqrt[n]{x} → \\sqrt{x}（丢弃可选根指数）。"""
    return re.sub(r"\\sqrt(?:\[[^\]]*\])?\{", r"\\sqrt{", text)


def _strip_display_math_delimiters(text: str) -> str:
    """移除行间公式 \\[ ... \\] 和 $$ ... $$ 的定界符。"""
    text = re.sub(r"\$\$", "", text)
    text = re.sub(r"\\\[", "", text)
    text = re.sub(r"\\\]", "", text)
    text = re.sub(r"\\\(|\\\)", "", text)
    return text


def normalize_formula(formula: str, generalize_vars: bool = False) -> str:
    """将 LaTeX 公式标准化为规范形式。

    Args:
        formula: 原始 LaTeX 公式字符串（可含 $$ / $ 定界符）。
        generalize_vars: 是否将单字母变量名通用化为占位符（默认 False）。

    Returns:
        标准化后的公式字符串。
    """
    if not formula or not formula.strip():
        return ""

    text = formula.strip()

    # 去除注释
    text = _strip_tex_comments(text)

    # 移除数学环境定界符
    text = _strip_display_math_delimiters(text)

    # 规范化空白
    text = _normalize_whitespace(text)

    # 指令小写化
    text = _normalize_command_case(text)

    # 统一 \\mathrm / \\text 内部空白
    text = _unify_mathrm(text)

    # 简化分数
    text = _simplify_fraction(text)

    # 简化根号
    text = _simplify_sqrt(text)

    # 去除双重嵌套大括号（保留 LaTeX 指令后的必要括号）
    text = re.sub(r"\{\s*\{([^}]*)\}\s*\}", r"{\1}", text)

    # 再次压缩空白
    text = _normalize_whitespace(text)

    if generalize_vars:
        text = _generalize_variables(text)

    return text


# ── 变量通用化（可选）──────────────────────────────────────────────────────


def _generalize_variables(text: str) -> str:
    """将单字母 LaTeX 变量名替换为通用占位符。

    - 普通字母如 a, b, x, y → V
    - 希腊字母如 \\alpha, \\beta → G
    - 带下标如 x_i → V_i（下标保留数字）

    注意：此操作可能有损语义，仅在模糊匹配时使用。
    """
    # 希腊字母 → G
    greek = (
        "alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|"
        "lambda|mu|nu|xi|omicron|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega|"
        "var|varepsilon|vartheta|varpi|varrho|varsigma|varphi"
    )
    text = re.sub(
        rf"\\(?:{greek})\b",
        "G",
        text,
        flags=re.IGNORECASE,
    )

    # 单字母变量（非 LaTeX 指令）→ V
    # 避免匹配到指令名中的字母
    text = re.sub(r"(?<!\\)\b([a-zA-Z])\b", "V", text)

    # 带下标变量名 → V_sub
    text = re.sub(r"V\s*_\s*\{?([a-zA-Z0-9]+)\}?", r"V_{\1}", text)

    return text


def extract_formulas(text: str) -> list[str]:
    """从文本中提取所有 LaTeX 公式。

    支持以下模式：
    - $$ ... $$（行间公式）
    - $ ... $（行内公式）
    - \\[ ... \\]（行间公式）
    - \\begin{equation} ... \\end{equation} 等环境

    Args:
        text: 原始文本（可能包含 LaTeX 公式）。

    Returns:
        提取到的公式列表（保留原始格式，未标准化）。
    """
    formulas: list[str] = []

    # 行间公式 $$ ... $$
    for m in re.finditer(r"\$\$(.+?)\$\$", text, re.DOTALL):
        formulas.append(m.group(1).strip())

    # 行内公式 $ ... $
    for m in re.finditer(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", text):
        formulas.append(m.group(1).strip())

    # \\[ ... \\]
    for m in re.finditer(r"\\\[(.+?)\\\]", text, re.DOTALL):
        formulas.append(m.group(1).strip())

    # 数学环境
    for m in re.finditer(
        r"\\begin\{([a-z]+?\*?)\}(.+?)\\end\{\1\}", text, re.DOTALL
    ):
        env_name = m.group(1).lower()
        if env_name in ("equation", "align", "gather", "multline",
                        "eqnarray", "split", "cases"):
            formulas.append(m.group(2).strip())

    return formulas


def formula_similarity(a: str, b: str) -> float:
    """计算两个标准化公式的 Jaccard 相似度（基于字符 trigram）。

    Args:
        a: 第一个公式。
        b: 第二个公式。

    Returns:
        0.0 ~ 1.0 的相似度分数。
    """
    a_norm = normalize_formula(a)
    b_norm = normalize_formula(b)
    if not a_norm or not b_norm:
        return 0.0

    def _shingles(s: str, n: int = 3) -> set[str]:
        return {s[i:i + n] for i in range(len(s) - n + 1)}

    shingles_a = _shingles(a_norm)
    shingles_b = _shingles(b_norm)

    if not shingles_a or not shingles_b:
        return 0.0

    intersection = shingles_a & shingles_b
    union = shingles_a | shingles_b
    return len(intersection) / len(union)



