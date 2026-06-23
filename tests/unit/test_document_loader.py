"""文档加载模块单元测试 —— PDF 多解析器降级链。"""

import sys
from unittest.mock import MagicMock, patch


def _ensure_doc_loader_importable():
    """Mock missing dependencies so document_loader can be imported."""
    mocks = {
        "langchain_community": MagicMock(),
        "langchain_community.document_loaders": MagicMock(),
        "langchain_text_splitters": MagicMock(),
    }
    for mod, mock_obj in mocks.items():
        if mod not in sys.modules:
            sys.modules[mod] = mock_obj
    # Ensure submodule attributes exist
    sys.modules["langchain_community.document_loaders"].PyPDFLoader = MagicMock()
    sys.modules["langchain_community.document_loaders"].Docx2txtLoader = MagicMock()
    sys.modules["langchain_community.document_loaders"].UnstructuredExcelLoader = MagicMock()
    sys.modules["langchain_text_splitters"].MarkdownHeaderTextSplitter = MagicMock()
    sys.modules["langchain_text_splitters"].RecursiveCharacterTextSplitter = MagicMock()


_ensure_doc_loader_importable()


class TestParsePdfWithFallback:
    def test_first_parser_succeeds(self):
        text = "This is a valid academic paper content with more than fifty non-whitespace characters for testing purposes. " * 3
        with patch("backend.rag.document_loader._PDF_PARSERS", [
            ("fast_parser", lambda p: text),
            ("slow_parser", lambda p: ""),
        ]):
            from backend.rag.document_loader import parse_pdf_with_fallback
            result_text, parser_name = parse_pdf_with_fallback("/path/to/test.pdf")
            assert parser_name == "fast_parser"
            assert len(result_text) > 50

    def test_second_parser_on_empty(self):
        text = "A shorter but still valid document text that has more than fifty characters in total for testing. " * 2
        with patch("backend.rag.document_loader._PDF_PARSERS", [
            ("parser_a", lambda p: ""),
            ("parser_b", lambda p: text),
        ]):
            from backend.rag.document_loader import parse_pdf_with_fallback
            result_text, parser_name = parse_pdf_with_fallback("/path/to/test.pdf")
            assert parser_name == "parser_b"

    def test_skip_too_short_text(self):
        text = "This is a valid academic paper content with more than fifty non-whitespace characters for testing purposes. " * 3
        with patch("backend.rag.document_loader._PDF_PARSERS", [
            ("parser_a", lambda p: "short"),
            ("parser_b", lambda p: text),
        ]):
            from backend.rag.document_loader import parse_pdf_with_fallback
            result_text, parser_name = parse_pdf_with_fallback("/path/to/test.pdf")
            assert parser_name == "parser_b"

    def test_all_parsers_fail_raises(self):
        with patch("backend.rag.document_loader._PDF_PARSERS", [
            ("parser_a", lambda p: ""),
            ("parser_b", lambda p: ""),
        ]):
            import pytest
            from backend.rag.document_loader import parse_pdf_with_fallback
            with pytest.raises(RuntimeError):
                parse_pdf_with_fallback("/path/to/test.pdf")


class TestDocumentLoader:
    def test_init_reads_config(self):
        with (
            patch("backend.rag.document_loader.CHUNK_SIZE", 800),
            patch("backend.rag.document_loader.CHUNK_OVERLAP", 100),
            patch("backend.rag.document_loader.PARSE_MAX_WORKERS", 4),
        ):
            from backend.rag.document_loader import DocumentLoader
            loader = DocumentLoader()
            assert loader._max_workers == 4

    def test_load_empty_path(self):
        import pytest
        from backend.rag.document_loader import DocumentLoader
        with pytest.raises(Exception):
            DocumentLoader().load_document("/nonexistent/file.pdf", "test.pdf")
