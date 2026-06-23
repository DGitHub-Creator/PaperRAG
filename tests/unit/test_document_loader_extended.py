"""文档解析模块单元测试 —— 分块逻辑、结构分块、标准分块。"""

import sys
from unittest.mock import MagicMock, patch

# Mock missing dependencies
for mod in ["langchain_community", "langchain_community.document_loaders",
            "langchain_text_splitters"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

sys.modules["langchain_community.document_loaders"].PyPDFLoader = MagicMock()
sys.modules["langchain_community.document_loaders"].Docx2txtLoader = MagicMock()
sys.modules["langchain_community.document_loaders"].UnstructuredExcelLoader = MagicMock()

# Create proper mock for RecursiveCharacterTextSplitter that actually splits
class MockDocument:
    def __init__(self, page_content, metadata=None):
        self.page_content = page_content
        self.metadata = metadata or {}

class MockSplitter:
    def __init__(self, chunk_size=800, chunk_overlap=100, **kwargs):
        self.chunk_size = chunk_size
    def create_documents(self, texts, metadatas=None):
        results = []
        for text in texts:
            # Simple split by chunk_size
            for i in range(0, max(len(text), 1), self.chunk_size):
                chunk = text[i:i + self.chunk_size]
                if chunk.strip():
                    results.append(MockDocument(page_content=chunk))
        return results

mock_ts = sys.modules["langchain_text_splitters"]
mock_ts.RecursiveCharacterTextSplitter = MockSplitter
mock_ts.MarkdownHeaderTextSplitter = MagicMock()


def _make_base_doc(**overrides) -> dict:
    base = {
        "filename": "test.pdf", "file_path": "/tmp/test.pdf",
        "file_type": "PDF", "page_number": 1, "parser": "PyMuPDF",
        "parent_idx": 0, "child_idx": 0, "num_children": 0,
        "parent_content": "", "chapter_path": "",
        "has_theorem_in_parent": False, "has_proof_in_parent": False,
        "has_formula": False, "formulas": [], "has_citation": False,
        "citations": [], "has_glossary": False, "glossary_terms": [],
    }
    base.update(overrides)
    return base


class TestSplitPageToThreeLevels:
    def test_empty_text(self):
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        result = loader._split_page_to_three_levels("", _make_base_doc(), 0)
        assert result == []

    def test_short_text_produces_chunks(self):
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        text = "This is a test paragraph with enough content. " * 50
        result = loader._split_page_to_three_levels(text, _make_base_doc(), 0)
        assert len(result) > 0
        assert all("text" in c for c in result)
        assert all("chunk_id" in c for c in result)

    def test_chunk_levels_present(self):
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        text = "A" * 2000
        result = loader._split_page_to_three_levels(text, _make_base_doc(), 0)
        levels = {c["chunk_level"] for c in result}
        assert 1 in levels

    def test_parent_child_relationships(self):
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        text = "A" * 3000
        result = loader._split_page_to_three_levels(text, _make_base_doc(), 0)
        level_3 = [c for c in result if c["chunk_level"] == 3]
        for chunk in level_3:
            assert chunk["parent_chunk_id"] != ""
            assert chunk["root_chunk_id"] != ""

    def test_chunk_id_format(self):
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        text = "A" * 2000
        result = loader._split_page_to_three_levels(text, _make_base_doc(), 0)
        for chunk in result:
            assert "test.pdf" in chunk["chunk_id"]

    def test_global_idx_increments(self):
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        text = "A" * 3000
        result = loader._split_page_to_three_levels(text, _make_base_doc(), 10)
        indices = [c["chunk_idx"] for c in result]
        assert all(i >= 10 for i in indices)


class TestSplitStandard:
    def test_produces_chunks(self):
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        text = "This is a test document with enough content. " * 100
        with patch("backend.rag.document_loader.extract_formulas", return_value=[]), \
             patch("backend.rag.document_loader.extract_citations", return_value=[]), \
             patch("backend.rag.document_loader.extract_glossary", return_value=[]):
            result = loader._split_standard(text, "test.pdf", "PDF", "/tmp/test.pdf")
        assert len(result) > 0

    def test_metadata_populated(self):
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        text = "Test content with enough text. " * 100
        with patch("backend.rag.document_loader.extract_formulas", return_value=[]), \
             patch("backend.rag.document_loader.extract_citations", return_value=[]), \
             patch("backend.rag.document_loader.extract_glossary", return_value=[]):
            result = loader._split_standard(text, "test.pdf", "PDF", "/tmp/test.pdf")
        for chunk in result:
            assert chunk["filename"] == "test.pdf"
            assert chunk["file_type"] == "PDF"
            assert "has_formula" in chunk
            assert "has_citation" in chunk

    def test_formula_extraction(self):
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        text = "The formula is $E=mc^2$ and more text. " * 50
        mock_formula = MagicMock()
        mock_formula.raw = "$E=mc^2$"
        with patch("backend.rag.document_loader.extract_formulas", return_value=[mock_formula]), \
             patch("backend.rag.document_loader.extract_citations", return_value=[]), \
             patch("backend.rag.document_loader.extract_glossary", return_value=[]):
            result = loader._split_standard(text, "test.pdf", "PDF", "/tmp/test.pdf")
        has_formula = any(c.get("has_formula") for c in result)
        assert has_formula


class TestLoadDocument:
    def test_unsupported_file_type(self):
        import pytest
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        with pytest.raises(ValueError, match="不支持的文件类型"):
            loader.load_document("/tmp/test.xyz", "test.xyz")

    def test_pdf_calls_load_pdf(self):
        from backend.rag.document_loader import DocumentLoader
        loader = DocumentLoader()
        with patch.object(loader, "_load_pdf", return_value=[{"text": "parsed"}]) as mock_pdf:
            result = loader.load_document("/tmp/test.pdf", "test.pdf")
            mock_pdf.assert_called_once_with("/tmp/test.pdf", "test.pdf")
            assert result == [{"text": "parsed"}]
