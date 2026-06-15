"""文档加载和分片服务 —— 学术论文增强版。

本模块负责将各类文档（PDF / Word / Excel）解析为纯文本，并在可配置的
分块策略下生成父子层级 chunk，供下游嵌入和向量存储使用。

核心能力:
    - PDF 多解析器降级链路: OpenDataLoader -> PyMuPDF -> pdfplumber -> PyPDF
      依次尝试，任一成功即返回，全失败时抛出异常。
    - 学术文本清洗: 自动移除页眉/页脚、页码、文末引用块。
    - 双轨分块策略:
        * 结构分块（默认）: 基于 Markdown 标题划分父块，父块内递归字符切分
          生成子块，每个子块携带父块元数据（章节路径、定理/证明标记等）。
        * 标准分块: 三层重叠滑动窗口，兼容非学术场景。
    - 定理/证明检测: 正则识别学术结构，标记于父块元数据，用于检索时优先级排序。

使用示例:
    >>> from backend.rag.document_loader import DocumentLoader
    >>> loader = DocumentLoader()
    >>> chunks = loader.load_document("/path/to/paper.pdf", "paper.pdf")
"""

import os
import traceback
from typing import Dict, List, Tuple

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    UnstructuredExcelLoader,
)

from backend.core.config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    ENABLE_ACADEMIC_CLEANING,
    ENABLE_STRUCTURAL_CHUNKING,
    PARSE_MAX_WORKERS,
)
from backend.core.logging_config import get_logger
from backend.rag.academic_cleaner import clean_paper_text
from backend.rag.theorem_detector import detect_theorem_proof

logger = get_logger(__name__)

# ── 结构分块用的 Markdown 标题层级 ──────────────────────────────────────
# 从 H1 到 H3 依次划分父块；更深的标题层级（#### 等）不作为父块边界。
_HEADERS_TO_SPLIT = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF 多解析器降级链路（4 级，按质量/鲁棒性排序）
# ═══════════════════════════════════════════════════════════════════════════════


def _try_opendataloader(file_path: str) -> str | None:
    """使用 OpenDataLoader 解析 PDF，输出 Markdown 格式文本。

    OpenDataLoader 基于 Apache PDFBox (Java)，支持表格/公式/标题的
    结构保留，是学术论文 PDF 解析的首选方案。输出的 Markdown 格式文本
    天然适合下游的结构化分块。

    依赖安装:
        pip install langchain-opendataloader-pdf

    Args:
        file_path: PDF 文件的绝对路径。

    Returns:
        解析成功返回 Markdown 格式的完整文本，失败返回 None。
    """
    try:
        from langchain_opendataloader_pdf import OpenDataLoaderPDFLoader
    except ImportError:
        logger.warning(
            "OpenDataLoader 未安装，跳过。安装: pip install langchain-opendataloader-pdf"
        )
        return None
    try:
        loader = OpenDataLoaderPDFLoader(
            file_path=file_path, format="markdown", quiet=True
        )
        docs = loader.load()
        if not docs:
            return None
        # 将各页 Markdown 用双换行拼接，保留段落边界
        return "\n\n".join(d.page_content for d in docs)
    except Exception:
        logger.debug("OpenDataLoader 解析异常: %s", traceback.format_exc())
        return None


def _try_pymupdf(file_path: str) -> str | None:
    """使用 PyMuPDF (fitz) 解析 PDF，返回合并文本。

    PyMuPDF 是 C 库 MuPDF 的 Python 绑定，解析速度快、对中西文字体
    支持好，是仅次于 OpenDataLoader 的二线方案。

    Args:
        file_path: PDF 文件的绝对路径。

    Returns:
        解析成功返回全部页面拼接文本，失败返回 None。
    """
    try:
        import fitz
    except ImportError:
        logger.debug("PyMuPDF (fitz) 未安装，跳过")
        return None
    try:
        doc = fitz.open(file_path)
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n\n".join(pages) if pages else None
    except Exception:
        logger.debug("PyMuPDF 解析异常: %s", traceback.format_exc())
        return None


def _try_pdfplumber(file_path: str) -> str | None:
    """使用 pdfplumber 解析 PDF，返回合并文本。

    pdfplumber 基于 pdfminer.six，对表格和复杂布局有较好的提取能力，
    作为第三候选解析器。

    Args:
        file_path: PDF 文件的绝对路径。

    Returns:
        解析成功返回全部页面拼接文本，失败返回 None。
    """
    try:
        import pdfplumber
    except ImportError:
        logger.debug("pdfplumber 未安装，跳过")
        return None
    try:
        with pdfplumber.open(file_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(pages) if pages else None
    except Exception:
        logger.debug("pdfplumber 解析异常: %s", traceback.format_exc())
        return None


def _try_pypdf(file_path: str) -> str | None:
    """使用 PyPDF (langchain_community) 解析 PDF，返回合并文本。

    PyPDF 是纯 Python 实现，兼容性最广但功能相对基础，作为最终兜底方案。

    Args:
        file_path: PDF 文件的绝对路径。

    Returns:
        解析成功返回全部页面拼接文本，失败返回 None。
    """
    try:
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        if not docs:
            return None
        return "\n\n".join(d.page_content for d in docs)
    except Exception:
        logger.debug("PyPDF 解析异常: %s", traceback.format_exc())
        return None


# ── 解析器注册表: 按优先级排列，依次尝试 ──────────────────────────────────
# 每个条目为 (显示名称, 解析函数)，遍历顺序即降级顺序。
_PDF_PARSERS: list[tuple[str, object]] = [
    ("OpenDataLoader", _try_opendataloader),  # 首选: 结构化 Markdown 输出
    ("PyMuPDF", _try_pymupdf),                # 二选: C 实现，速度快
    ("pdfplumber", _try_pdfplumber),           # 三选: 表格/布局友好
    ("PyPDF", _try_pypdf),                     # 兜底: 纯 Python
]


def parse_pdf_with_fallback(file_path: str) -> tuple[str, str]:
    """PDF 多解析器降级链：依次尝试直到成功提取有效文本。

    遍历 _PDF_PARSERS 注册表，每个解析器尝试解析，若返回非空且
    有效字符数 > 50 则认为成功。全链路失败则抛出 RuntimeError。

    Args:
        file_path: PDF 文件的绝对路径。

    Returns:
        (text, parser_name): 提取的完整文本和所用的解析器名称。

    Raises:
        RuntimeError: 所有解析器均无法提取有效文本时抛出。
    """
    fname = os.path.basename(file_path)
    for name, fn in _PDF_PARSERS:
        logger.info("  [%s] → 尝试解析器: %s ...", fname, name)
        try:
            text: str | None = fn(file_path)
            if text and len(text.strip()) > 50:
                # 有效文本：含至少 50 个非空白字符
                logger.info("  [%s] ✓ 解析成功 (%s), %d 字符", fname, name, len(text))
                return text, name
            else:
                # 文本过短或无内容，视为解析失败
                logger.warning("  [%s] ✗ %s 返回文本过短（%d 字符），降级...",
                               fname, name, len(text.strip()) if text else 0)
        except Exception as e:
            logger.warning("  [%s] ✗ %s 异常，降级... (%s)", fname, name, str(e))
            continue

    raise RuntimeError(f"所有 PDF 解析器均无法处理: {fname}")


# ═══════════════════════════════════════════════════════════════════════════════
#  DocumentLoader —— 主类
# ═══════════════════════════════════════════════════════════════════════════════


class DocumentLoader:
    """文档加载和分片服务（学术论文增强版）。

    负责将 PDF / Word / Excel 文档解析为纯文本，并根据配置选择
    结构分块或标准三层滑动窗口分块，输出带父子层级元数据的 chunk 列表。

    Attributes:
        _structural_chunk_size (int): 结构分块时子块的最大字符数。
        _structural_chunk_overlap (int): 结构分块时子块间的重叠字符数。
        _enable_academic_cleaning (bool): 是否启用学术文本清洗。
        _enable_structural_chunking (bool): 是否优先使用结构分块。

    分块策略选择逻辑:
        - 若 ENABLE_STRUCTURAL_CHUNKING=True（默认），PDF 文档走结构分块：
          先按 Markdown 标题划分父块，子块在父块内递归切分，携带章节上下文。
        - 否则走标准三层滑动窗口：1200/600/300 字符三个粒度，层层嵌套。
    """

    def __init__(self):
        """初始化 DocumentLoader。

        所有配置参数从 backend.core.config 集中读取，不再通过构造函数传入。
        三层滑动窗口的粒度设计为:
            Level 1 (父块): max(1200, chunk_size * 2)，重叠 max(240, overlap * 2)
            Level 2 (中块): chunk_size，重叠 chunk_overlap
            Level 3 (子块): chunk_size / 2，重叠 chunk_overlap / 2
        这种 2:1 的层级比例保证父子关系清晰，兼顾检索精度与上下文广度。
        """
        # ── 从集中配置读取所有参数 ────────────────────────────────────
        self._structural_chunk_size = CHUNK_SIZE
        self._structural_chunk_overlap = CHUNK_OVERLAP
        self._enable_academic_cleaning = ENABLE_ACADEMIC_CLEANING
        self._enable_structural_chunking = ENABLE_STRUCTURAL_CHUNKING
        self._max_workers = PARSE_MAX_WORKERS

        # ── 三层滑动窗口 splitter ────────────────────────────────────
        # Level 1: 粗粒度父块，如 1200 字符，重叠 240 字符
        level_1_size = max(1200, CHUNK_SIZE * 2)
        level_1_overlap = max(240, CHUNK_OVERLAP * 2)
        # Level 2: 中粒度块
        level_2_size = max(600, CHUNK_SIZE)
        level_2_overlap = max(120, CHUNK_OVERLAP)
        # Level 3: 细粒度子块
        level_3_size = max(300, CHUNK_SIZE // 2)
        level_3_overlap = max(60, CHUNK_OVERLAP // 2)

        # 中文友好的分隔符序列: 优先在自然断句处切分
        _CHINESE_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "，", "、", " ", ""]

        self._splitter_level_1 = RecursiveCharacterTextSplitter(
            chunk_size=level_1_size,
            chunk_overlap=level_1_overlap,
            add_start_index=True,
            separators=_CHINESE_SEPARATORS,
        )
        self._splitter_level_2 = RecursiveCharacterTextSplitter(
            chunk_size=level_2_size,
            chunk_overlap=level_2_overlap,
            add_start_index=True,
            separators=_CHINESE_SEPARATORS,
        )
        self._splitter_level_3 = RecursiveCharacterTextSplitter(
            chunk_size=level_3_size,
            chunk_overlap=level_3_overlap,
            add_start_index=True,
            separators=_CHINESE_SEPARATORS,
        )

    # ── 静态工具方法 ──────────────────────────────────────────────────

    @staticmethod
    def _build_chunk_id(filename: str, page_number: int, level: int, index: int) -> str:
        """构建唯一 chunk ID。

        格式: {filename}::p{page_number}::l{level}::{index}
        其中 level 1 为父块，level 3 为最细粒度子块。

        Args:
            filename: 源文件名（不含路径）。
            page_number: 所在页码（从 0 开始；PDF 解析时实际页码可能不准确）。
            level: 块层级（1=父, 2=中, 3=子）。
            index: 该层级内的序号。

        Returns:
            唯一标识字符串。
        """
        return f"{filename}::p{page_number}::l{level}::{index}"

    # ── 标准三层滑动窗口分块（非学术模式）─────────────────────────────

    def _split_page_to_three_levels(
        self,
        text: str,
        base_doc: Dict,
        page_global_chunk_idx: int,
    ) -> List[Dict]:
        """对单页（或单段）文本执行三层嵌套滑动窗口分块。

        流程:
            1. Level 1 splitter 将文本切分为粗粒度"父块"
            2. 每个父块内部用 Level 2 splitter 切分为"中块"
            3. 每个中块内部用 Level 3 splitter 切分为"子块"
            4. 每层块记录 parent_chunk_id / root_chunk_id 用于父子追溯

        Args:
            text: 待分块的原始文本。
            base_doc: 基础元数据字典，将被浅拷贝到每个 chunk。
            page_global_chunk_idx: 全局递增的 chunk 序号起始值。

        Returns:
            chunk 字典列表，每个包含 text、chunk_id、层级标记等字段。
        """
        if not text:
            return []

        root_chunks: List[Dict] = []
        page_number = int(base_doc.get("page_number", 0))
        filename = base_doc["filename"]

        level_1_docs = self._splitter_level_1.create_documents([text], [base_doc])
        level_1_counter = 0
        level_2_counter = 0
        level_3_counter = 0

        for level_1_doc in level_1_docs:
            level_1_text = (level_1_doc.page_content or "").strip()
            if not level_1_text:
                continue
            level_1_id = self._build_chunk_id(filename, page_number, 1, level_1_counter)
            level_1_counter += 1

            # Level 1 chunk: 根父块
            level_1_chunk = {
                **base_doc,
                "text": level_1_text,
                "chunk_id": level_1_id,
                "parent_chunk_id": "",        # 顶层无父块
                "root_chunk_id": level_1_id,  # 根指向自身
                "chunk_level": 1,
                "chunk_idx": page_global_chunk_idx,
            }
            page_global_chunk_idx += 1
            root_chunks.append(level_1_chunk)

            # Level 2: 中块，父块为 level_1_chunk
            level_2_docs = self._splitter_level_2.create_documents(
                [level_1_text], [base_doc]
            )
            for level_2_doc in level_2_docs:
                level_2_text = (level_2_doc.page_content or "").strip()
                if not level_2_text:
                    continue
                level_2_id = self._build_chunk_id(
                    filename, page_number, 2, level_2_counter
                )
                level_2_counter += 1

                level_2_chunk = {
                    **base_doc,
                    "text": level_2_text,
                    "chunk_id": level_2_id,
                    "parent_chunk_id": level_1_id,
                    "root_chunk_id": level_1_id,  # 根追溯至 Level 1
                    "chunk_level": 2,
                    "chunk_idx": page_global_chunk_idx,
                }
                page_global_chunk_idx += 1
                root_chunks.append(level_2_chunk)

                # Level 3: 子块，父块为 level_2_chunk
                level_3_docs = self._splitter_level_3.create_documents(
                    [level_2_text], [base_doc]
                )
                for level_3_doc in level_3_docs:
                    level_3_text = (level_3_doc.page_content or "").strip()
                    if not level_3_text:
                        continue
                    level_3_id = self._build_chunk_id(
                        filename, page_number, 3, level_3_counter
                    )
                    level_3_counter += 1
                    root_chunks.append({
                        **base_doc,
                        "text": level_3_text,
                        "chunk_id": level_3_id,
                        "parent_chunk_id": level_2_id,
                        "root_chunk_id": level_1_id,  # 根追溯至 Level 1
                        "chunk_level": 3,
                        "chunk_idx": page_global_chunk_idx,
                    })
                    page_global_chunk_idx += 1

        return root_chunks

    # ── 标准三层分块（非学术模式入口）─────────────────────────────────

    def _split_standard(
        self,
        full_text: str,
        filename: str,
        doc_type: str,
        file_path: str,
        parser: str = "",
    ) -> List[Dict]:
        """标准三层滑动窗口分块（兼容非 PDF 文档及关闭结构分块时使用）。

        对整个文档文本执行三层嵌套滑动窗口分块，所有 chunk 标记为
        page_number=0（非 PDF 文档无页码概念）。

        Args:
            full_text: 文档完整文本。
            filename: 源文件名。
            doc_type: 文档类型标识（如 "PDF", "Word", "Excel"）。
            file_path: 源文件绝对路径。
            parser: 使用的解析器名称（PDF 场景）；非 PDF 为空字符串。

        Returns:
            chunk 字典列表。
        """
        documents = []
        page_global_chunk_idx = 0

        # 构建基础元数据；非 PDF 文档无页码、无父块元数据
        base_doc = {
            "filename": filename,
            "file_path": file_path,
            "file_type": doc_type,
            "page_number": 0,
            "parser": parser,
            "parent_idx": 0,
            "child_idx": 0,
            "num_children": 0,
            "parent_content": "",
            "chapter_path": "",
            "has_theorem_in_parent": False,
            "has_proof_in_parent": False,
        }

        page_chunks = self._split_page_to_three_levels(
            text=full_text,
            base_doc=base_doc,
            page_global_chunk_idx=page_global_chunk_idx,
        )
        documents.extend(page_chunks)
        return documents

    # ── 结构分块（学术增强模式）───────────────────────────────────────

    def _split_structural(
        self,
        full_text: str,
        filename: str,
        parser: str = "",
    ) -> List[Dict]:
        """基于 Markdown 标题做结构分块 + 递归字符分块兜底。

        流程:
            1. 用 MarkdownHeaderTextSplitter 按 H1-H3 标题将全文划分为父块。
            2. 每个父块检测定理/证明，构建章节路径（如 "引言 → 方法 → 定理 3.1"）。
            3. 父块内用 RecursiveCharacterTextSplitter 切分子块。
            4. 每个子块携带父块元数据（parent_content、章节路径、定理标记），
               用于检索时的上下文扩展与优先级排序。

        Args:
            full_text: 完整文档文本（建议经 OpenDataLoader 解析，已为 Markdown 格式）。
            filename: 源文件名。
            parser: 解析器名称，记录于每个 chunk 的 metadata 中。

        Returns:
            chunk 字典列表，每个子块携带完整的父子关系元数据。
        """
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=_HEADERS_TO_SPLIT
        )
        parents = markdown_splitter.split_text(full_text)

        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._structural_chunk_size,
            chunk_overlap=self._structural_chunk_overlap,
        )

        all_docs: List[Dict] = []
        global_idx = 0

        for p_idx, parent in enumerate(parents):
            parent_text = parent.page_content
            # 检测父块中是否包含定理/证明结构
            has_theorem, has_proof = detect_theorem_proof(parent_text)

            # 构建章节路径: 如 "Header 1 → Header 2 → Header 3"
            chapter_parts = []
            for h in ("Header 1", "Header 2", "Header 3"):
                val = parent.metadata.get(h, "")
                if val:
                    chapter_parts.append(val)
            chapter_path = " → ".join(chapter_parts) if chapter_parts else ""

            # 父块内递归切分子块
            children = child_splitter.split_text(parent_text)
            num_children = len(children)

            for c_idx, child_text in enumerate(children):
                chunk_id = f"{filename}_p{p_idx}_c{c_idx}"
                all_docs.append({
                    "text": child_text,
                    "chunk_id": chunk_id,
                    "parent_chunk_id": f"{filename}_p{p_idx}",
                    "root_chunk_id": f"{filename}_p{p_idx}",
                    "chunk_level": 3,                  # 结构分块统一标记为 Level 3
                    "chunk_idx": global_idx,
                    "filename": filename,
                    "file_path": "",
                    "file_type": "PDF",
                    "page_number": 0,
                    "parser": parser,
                    # ── 父块元数据（用于上下文扩展与优先级排序）─────
                    "parent_idx": p_idx,
                    "child_idx": c_idx,
                    "num_children": num_children,
                    "parent_content": parent_text,
                    "chapter_path": chapter_path,
                    "has_theorem_in_parent": has_theorem,
                    "has_proof_in_parent": has_proof,
                })
                global_idx += 1

        logger.info("  [%s] → %d 子块 (%s)", filename, len(all_docs), parser)
        return all_docs

    # ── PDF 加载（多解析器降级 + 学术清洗 + 分块）─────────────────────

    def _load_pdf(self, file_path: str, filename: str) -> List[Dict]:
        """PDF 完整处理链路：多解析器降级 → 学术清洗 → 分块。

        步骤:
            1. 通过多解析器降级链提取原始文本
            2. 若启用学术清洗（ENABLE_ACADEMIC_CLEANING=True），
               调用 clean_paper_text 去除页眉/页脚/引用块
            3. 若启用结构分块（ENABLE_STRUCTURAL_CHUNKING=True），
               走 _split_structural；否则走 _split_standard

        Args:
            file_path: PDF 文件的绝对路径。
            filename: 源文件名（用于日志和 chunk ID 生成）。

        Returns:
            chunk 字典列表。
        """
        full_text, parser = parse_pdf_with_fallback(file_path)

        # 学术清洗: 移除页眉/页脚/页码/文末引用块
        if self._enable_academic_cleaning:
            full_text = clean_paper_text(full_text)

        # 分块策略选择
        if self._enable_structural_chunking:
            return self._split_structural(full_text, filename, parser)
        else:
            return self._split_standard(full_text, filename, "PDF", file_path, parser)

    # ── 公开接口 ──────────────────────────────────────────────────────

    def load_document(self, file_path: str, filename: str) -> list[dict]:
        """加载单个文档并分片。

        根据文件扩展名自动选择解析路径:
            - .pdf  → 多解析器降级 + 学术清洗 + 结构/标准分块
            - .docx / .doc → Docx2txtLoader 解析 + 标准三层分块
            - .xlsx / .xls → UnstructuredExcelLoader 解析 + 标准三层分块

        Args:
            file_path: 文件的绝对路径。
            filename: 文件名（含扩展名），用于类型判断。

        Returns:
            chunk 字典列表，每个 chunk 包含 text、chunk_id、层级元数据。

        Raises:
            ValueError: 不支持的文件类型。
            RuntimeError: PDF 所有解析器均失败。
            Exception: Word/Excel 解析过程中的 I/O 或格式错误。
        """
        file_lower = filename.lower()

        # PDF 文档: 走完整增强链路
        if file_lower.endswith(".pdf"):
            return self._load_pdf(file_path, filename)

        # Word 文档: 提取纯文本后走标准三层分块
        if file_lower.endswith((".docx", ".doc")):
            doc_type = "Word"
            loader = Docx2txtLoader(file_path)
        # Excel 文档: 提取内容后走标准三层分块
        elif file_lower.endswith((".xlsx", ".xls")):
            doc_type = "Excel"
            loader = UnstructuredExcelLoader(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {filename}")

        try:
            raw_docs = loader.load()
            full_text = "\n\n".join(d.page_content for d in raw_docs)
            return self._split_standard(full_text, filename, doc_type, file_path)
        except Exception as e:
            raise Exception(f"处理文档失败: {str(e)}")

    def load_documents_from_folder(self, folder_path: str) -> list[dict]:
        """从文件夹批量加载所有支持的文档并分片。

        扫描文件夹内的 .pdf / .docx / .doc / .xlsx / .xls 文件，
        逐个调用 load_document 处理。单个文件失败不影响其他文件的处理，
        异常被静默吞下并通过日志记录。

        Args:
            folder_path: 文件夹的绝对路径。

        Returns:
            所有成功解析的文档 chunk 的聚合列表。
        """
        all_documents = []

        for filename in os.listdir(folder_path):
            file_lower = filename.lower()
            # 仅处理支持的文件格式
            if not (
                file_lower.endswith(".pdf")
                or file_lower.endswith((".docx", ".doc"))
                or file_lower.endswith((".xlsx", ".xls"))
            ):
                continue

            file_path = os.path.join(folder_path, filename)
            try:
                documents = self.load_document(file_path, filename)
                all_documents.extend(documents)
                logger.info(
                    "[%s] 加载完成，共 %d 个 chunk", filename, len(documents)
                )
            except Exception as e:
                logger.error(
                    "[%s] 加载失败，跳过: %s", filename, str(e)
                )
                continue

        logger.info(
            "批量加载完成: %d 个文件 → 共 %d 个 chunk",
            len(set(d.get("filename", "") for d in all_documents)),
            len(all_documents),
        )
        return all_documents
