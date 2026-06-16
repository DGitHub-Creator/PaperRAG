"""RAG 工具函数单元测试 —— HyDE、Step-back、核心检索。"""

from unittest.mock import MagicMock, patch


class TestGenerateHypotheticalDocument:
    def test_generates_document(self, mock_llm):
        with patch("backend.rag.rag_utils._get_stepback_model") as mock_model:
            mock_instance = MagicMock()
            mock_instance.invoke.return_value.content = "This is a hypothetical document about MPC."
            mock_model.return_value = mock_instance

            from backend.rag.rag_utils import generate_hypothetical_document

            result = generate_hypothetical_document("What is MPC?")
            assert "hypothetical document" in result

    def test_returns_empty_on_model_failure(self, mock_llm):
        with patch("backend.rag.rag_utils._get_stepback_model") as mock_model:
            mock_model.return_value = None
            from backend.rag.rag_utils import generate_hypothetical_document

            result = generate_hypothetical_document("What is MPC?")
            assert result == ""

    def test_returns_empty_on_invoke_exception(self, mock_llm):
        with patch("backend.rag.rag_utils._get_stepback_model") as mock_model:
            mock_instance = MagicMock()
            mock_instance.invoke.side_effect = RuntimeError("API error")
            mock_model.return_value = mock_instance
            from backend.rag.rag_utils import generate_hypothetical_document

            result = generate_hypothetical_document("What is MPC?")
            assert result == ""


class TestStepBackExpand:
    def test_full_expansion(self, mock_llm):
        with (
            patch("backend.rag.rag_utils._get_stepback_model") as mock_model,
            patch("backend.rag.rag_utils._generate_step_back_question") as mock_q,
            patch("backend.rag.rag_utils._answer_step_back_question") as mock_a,
        ):
            mock_q.return_value = "What is the general principle?"
            mock_a.return_value = "General answer."
            mock_model.return_value = MagicMock()

            from backend.rag.rag_utils import step_back_expand

            result = step_back_expand("How does MPC work?")
            assert result["step_back_question"] == "What is the general principle?"
            assert result["step_back_answer"] == "General answer."
            assert "How does MPC work" in result["expanded_query"]
            assert "What is the general principle?" in result["expanded_query"]

    def test_no_expansion_when_empty(self, mock_llm):
        with (
            patch("backend.rag.rag_utils._generate_step_back_question") as mock_q,
            patch("backend.rag.rag_utils._answer_step_back_question") as mock_a,
        ):
            mock_q.return_value = ""
            mock_a.return_value = ""
            from backend.rag.rag_utils import step_back_expand

            result = step_back_expand("How does MPC work?")
            assert result["expanded_query"] == "How does MPC work?"


class TestRetrieveDocuments:
    def _patch_deps(self):
        """Patch rag_utils module-level dependency references."""
        embedding = MagicMock()
        embedding.get_embeddings.return_value = [[0.1] * 1024]
        embedding.get_sparse_embedding.return_value = {0: 0.5}
        milvus = MagicMock()
        return [
            patch("backend.rag.rag_utils.get_embedding_service", return_value=embedding),
            patch("backend.rag.rag_utils.get_milvus_manager", return_value=milvus),
            milvus,
        ]

    def test_hybrid_success(self):
        patches = self._patch_deps()
        patches[2].hybrid_retrieve.return_value = [
            {"id": 1, "text": "doc1", "filename": "test.pdf", "chunk_level": 3,
             "chunk_id": "c1", "parent_chunk_id": "p1", "root_chunk_id": "r1",
             "score": 0.9, "page_number": 1}
        ]
        with patches[0], patches[1]:
            from backend.rag.rag_utils import retrieve_documents
            result = retrieve_documents("test query")
        assert "docs" in result
        assert "meta" in result

    def test_hybrid_failure_falls_back_to_dense(self):
        patches = self._patch_deps()
        patches[2].hybrid_retrieve.side_effect = RuntimeError("Hybrid failed")
        patches[2].dense_retrieve.return_value = [
            {"id": 1, "text": "doc1", "filename": "test.pdf", "chunk_level": 3,
             "chunk_id": "c1", "parent_chunk_id": "p1", "root_chunk_id": "r1",
             "score": 0.8, "page_number": 1}
        ]
        with patches[0], patches[1]:
            from backend.rag.rag_utils import retrieve_documents
            result = retrieve_documents("test query")
        assert result["meta"]["retrieval_mode"] == "dense_fallback"

    def test_both_fail_return_empty(self):
        patches = self._patch_deps()
        patches[2].hybrid_retrieve.side_effect = RuntimeError("Hybrid failed")
        patches[2].dense_retrieve.side_effect = RuntimeError("Dense also failed")
        with patches[0], patches[1]:
            from backend.rag.rag_utils import retrieve_documents
            result = retrieve_documents("test query")
        assert result["docs"] == []
        assert result["meta"]["retrieval_mode"] == "failed"
