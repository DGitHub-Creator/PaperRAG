"""学术论文文本清洗 —— 移除页眉页脚、页码、引用块等干扰内容。

针对密码学/计算机科学会议论文格式优化。

两阶段处理流程:
    1. 逐行过滤: 移除页眉页脚、独立页码、连续重复短行
    2. 文末引用块检测: 识别并移除 5 行以上连续引用块（需含 DOI/卷/页码特征，
       避免误删正文中带方括号编号的公式或定理行）

使用示例:
    >>> from backend.rag.academic_cleaner import clean_paper_text
    >>> cleaned = clean_paper_text(raw_pdf_text)
"""

import logging
import re

from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# ── 页眉/页脚特征模式 ──────────────────────────────────────────────
# 匹配常见密码学/计算机科学会议论文的页眉页脚：
#   "Advances in Cryptology – EUROCRYPT 2025"
#   "Lecture Notes in Computer Science, Vol. 14004"
#   "Springer-Verlag Berlin Heidelberg 2023"
#   "© International Association for Cryptologic Research 2024"
_HEADER_FOOTER_PATS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"Advances\s+in\s+Cryptolog\w*",
        r"EUROCRYPT\b",
        r"CRYPTO\s+\'?\d{2}",
        r"Proceedings\s+of\s+the\b",
        r"Lecture\s+Notes\s+in\s+Computer\s+Science",
        r"International\s+Association\s+for\s+Cryptologic",
        r"Springer[\s-]*Verlag",
        r"©\s+\d{4}",
        r"All\s+rights?\s+reserved",
        r"This\s+work\s+is\s+licensed",
    ]
]

# 匹配带方括号编号的引用行，如 "[42] Smith et al. ..."、"[13,14,15] ..."
_REF_LINE = re.compile(r"^\s*\[\d+[,\d\s]*\]\s")

# 引用块特征关键词：用于判断多行连续引用是否构成参考文献列表
_CITATION_CLUES = re.compile(
    r"(?:et\s+al\.?|doi\s*:|vol\.\s*\d|pp\.\s*\d|Proc\.\s|Proceedings\b)",
    re.IGNORECASE,
)


def clean_paper_text(text: str) -> str:
    """清洗 PDF 解析后的文本，去除页眉/页脚/引用列表等噪声。

    处理逻辑:
        Phase 1 - 逐行过滤:
            - 连续空行压缩为单行
            - 独立页码行（如 "42"、"-- 15 --"）移除
            - 匹配页眉/页脚特征的行移除
            - 连续重复的短行（<120 字符）移除

        Phase 2 - 文末引用块移除:
            - 检测以方括号编号开头的连续行
            - 若累计 5 行以上且含引用特征关键词（DOI、卷、页码等），整体移除
            - 不足 5 行或不含特征的保留（避免误删正文）

    Args:
        text: 原始 PDF 解析文本。

    Returns:
        清洗后的文本字符串。
    """
    logger.debug("clean_paper_text: 输入 %d 字符", len(text))

    lines = text.split("\n")
    cleaned: list[str] = []
    prev_stripped: str | None = None
    removed_lines = 0

    # ── Phase 1: 逐行过滤 ─────────────────────────────────────────
    for i, line in enumerate(lines):
        stripped = line.strip()
        # 空行处理：压缩连续空行
        if not stripped:
            if i > 0 and not lines[i - 1].strip():
                removed_lines += 1
                continue
            cleaned.append(line)
            continue

        # 独立页码行（纯数字或带短横线修饰，如 "42"、"-- 15 --"、"- 128 -"）
        if re.match(r"^\s*[–\-]?\s*\d{1,4}\s*[–\-]?\s*$", stripped):
            removed_lines += 1
            continue

        # 页眉/页脚特征匹配（不在引用行中检查，避免引用编号干扰）
        if not _REF_LINE.match(stripped) and any(
            p.search(stripped) for p in _HEADER_FOOTER_PATS
        ):
            removed_lines += 1
            continue

        # 连续重复短行（常见于页眉/页脚的多次出现）
        if prev_stripped and stripped == prev_stripped and len(stripped) < 120:
            removed_lines += 1
            continue

        cleaned.append(line)
        prev_stripped = stripped

    # ── Phase 2: 文末引用块检测与移除 ─────────────────────────────
    def _is_ref_block(block: list[str]) -> bool:
        """判断一组连续引用行是否构成真正的参考文献块。

        条件: 行数 > 5 且文本中含引用特征关键词（DOI、卷号、页码等）。
        阈值 5 行保证不会误删正文中单个带编号的公式或定理行。
        """
        return len(block) > 5 and bool(_CITATION_CLUES.search("\n".join(block)))

    ref_block_lines: list[int] = []  # 暂存当前引用块的原始行号
    result: list[str] = []
    ref_removed = 0

    for i, line in enumerate(cleaned):
        if _REF_LINE.match(line):
            ref_block_lines.append(i)
        else:
            # 遇到非引用行，判断之前的引用块是保留还是移除
            if _is_ref_block([cleaned[j] for j in ref_block_lines]):
                ref_removed += len(ref_block_lines)
            elif ref_block_lines:
                # 不足阈值的保留原样
                for j in ref_block_lines:
                    result.append(cleaned[j])
            ref_block_lines.clear()
            result.append(line)

    # 文件末尾的引用块处理
    if ref_block_lines and not _is_ref_block([cleaned[j] for j in ref_block_lines]):
        for j in ref_block_lines:
            result.append(cleaned[j])

    total_removed = removed_lines + ref_removed
    logger.debug(
        "clean_paper_text: 输出 %d 字符 (-%d 行: %d 噪声 + %d 引用)",
        len("\n".join(result)), total_removed, removed_lines, ref_removed,
    )
    return "\n".join(result)


def clean_paper_text_with_layout(text: str, regions=None) -> str:
    """Clean paper text using layout analysis.

    Args:
        text: Raw paper text
        regions: Optional list of layout regions from analyze_page_layout()
    """
    if not regions:
        return clean_paper_text(text)

    body_texts = []

    for region in regions:
        if region['type'] == 'text':
            body_texts.append(region['content'])
        elif region['type'] == 'caption':
            body_texts.append(region['content'])

    return '\n'.join(body_texts)


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF 页面布局分析（基于 pdfplumber）
# ═══════════════════════════════════════════════════════════════════════════════


def _group_chars_into_lines(chars, y_tolerance=2):
    """Group characters into lines based on y-position."""
    lines = []
    current_line = {'chars': [], 'y0': float('inf'), 'y1': 0, 'x0': float('inf'), 'x1': 0}

    sorted_chars = sorted(chars, key=lambda c: (round(c['top'] / y_tolerance), c['x0']))

    for char in sorted_chars:
        if abs(char['top'] - current_line['y0']) > y_tolerance and current_line['chars']:
            current_line['text'] = ''.join(c['text'] for c in current_line['chars'])
            lines.append(current_line)
            current_line = {'chars': [], 'y0': char['top'], 'y1': char['bottom'],
                          'x0': char['x0'], 'x1': char['x1']}

        current_line['chars'].append(char)
        current_line['y0'] = min(current_line['y0'], char['top'])
        current_line['y1'] = max(current_line['y1'], char['bottom'])
        current_line['x0'] = min(current_line['x0'], char['x0'])
        current_line['x1'] = max(current_line['x1'], char['x1'])

    if current_line['chars']:
        current_line['text'] = ''.join(c['text'] for c in current_line['chars'])
        lines.append(current_line)

    return lines


_CAPTION_PATS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^Figure \d+",
        r"^Fig\. \d+",
        r"^Table \d+",
        r"^图 \d+",
        r"^表 \d+",
        r"^Figure~\d+",
    ]
]


def _is_caption(text):
    """Check if text is a figure/table caption."""
    return any(p.match(text) for p in _CAPTION_PATS)


def _is_reference_line(text):
    """Check if text is a reference/citation line.
    
    Reference lines start with [number] and look like citation entries.
    Theorem statements starting with [number] are NOT reference lines.
    """
    if not re.match(r"^\[\d+\]\s", text):
        return False
    
    # Theorem/definition patterns - these are NOT references
    theorem_patterns = [
        r"This\s+is\s+a\s+theorem",
        r"We\s+prove",
        r"The\s+theorem\s+states",
        r"Definition\s+\d+",
        r"Lemma\s+\d+",
        r"Proof\s+of",
    ]
    
    if any(re.search(p, text, re.IGNORECASE) for p in theorem_patterns):
        return False
    
    # If it starts with [number] and doesn't look like a theorem, treat as reference
    return True


def analyze_page_layout(page):
    """Analyze page layout using pdfplumber.

    Returns list of dicts with:
    - type: 'text' | 'image' | 'table' | 'caption' | 'header_footer' | 'reference'
    - bbox: (x0, y0, x1, y1)
    - content: extracted text or None
    """
    regions = []

    width, height = page.width, page.height
    header_zone = height * 0.1
    footer_zone = height * 0.9

    chars = page.chars
    if not chars:
        return regions

    lines = _group_chars_into_lines(chars)

    for line in lines:
        y_center = (line['y0'] + line['y1']) / 2
        text = line['text'].strip()

        if not text:
            continue

        if y_center < header_zone or y_center > footer_zone:
            region_type = 'header_footer'
        elif _is_caption(text):
            region_type = 'caption'
        elif _is_reference_line(text):
            region_type = 'reference'
        else:
            region_type = 'text'

        regions.append({
            'type': region_type,
            'bbox': (line['x0'], line['y0'], line['x1'], line['y1']),
            'content': text
        })

    for img in page.images:
        regions.append({
            'type': 'image',
            'bbox': (img['x0'], img['top'], img['x1'], img['bottom']),
            'content': None
        })

    for table in page.find_tables():
        regions.append({
            'type': 'table',
            'bbox': table.bbox,
            'content': table.extract()
        })

    return regions
