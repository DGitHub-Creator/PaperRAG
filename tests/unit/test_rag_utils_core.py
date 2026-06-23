"""RAG 核心检索函数单元测试 —— auto_merge、rerank、expand_context、retrieve_documents。"""

import sys
from unittest.mock import MagicMock, patch

# Mock langgraph if not installed
for mod in ["langgraph", "langgraph.checkpoint", "langgraph.checkpoint.memory",
            "langgraph.graph", "langgraph.types"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()


def _make_doc(**overrides) -> dict:
    base = {
        "id": 1, "text": "test text", "filename": "test.pdf",
        "page_number": 1, "chunk_id": "c1", "parent_chunk_id": "p1",
        "root_chunk_id": "r1", "chunk_level": 3, "score": 0.9,
        "parent_idx": 0, "child_idx": 0,
    }
    base.update(overrides)
    return base


class TestAutoMergeDocuments:
    def test_empty_docs(self):
        from backend.rag.rag_utils import _auto_merge_documents
        result, meta = _auto_merge_documents([], 5)
        assert result == []
        assert meta["auto_merge_applied"] is False

    def test_single_doc_no_merge(self):
        from backend.rag.rag_utils import _auto_merge_documents
        docs = [_make_doc(chunk_id="c1", parent_chunk_id="p1")]
        result, meta = _auto_merge_documents(docs, 5)
        assert len(result) == 1
        assert meta["auto_merge_applied"] is False

    def test_docs_below_threshold_no_merge(self):
        from backend.rag.rag_utils import _auto_merge_documents
        docs = [
            _make_doc(chunk_id="c1", parent_chunk_id="p1"),
            _make_doc(chunk_id="c2", parent_chunk_id="p2"),
        ]
        result, meta = _auto_merge_documents(docs, 5)
        assert len(result) == 2
        assert meta["auto_merge_applied"] is False

    def test_sorted_by_score(self):
        from backend.rag.rag_utils import _auto_merge_documents
        docs = [
            _make_doc(chunk_id="c1", score=0.5),
            _make_doc(chunk_id="c2", score=0.9),
            _make_doc(chunk_id="c3", score=0.7),
        ]
        result, meta = _auto_merge_documents(docs, 5)
        scores = [d["score"] for d in result]
        assert scores == sorted(scores, reverse=True)

    def test_truncated_to_top_k(self):
        from backend.rag.rag_utils import _auto_merge_documents
        docs = [_make_doc(chunk_id=f"c{i}", score=float(i) / 10) for i in range(10)]
        result, meta = _auto_merge_documents(docs, 3)
        assert len(result) == 3


class TestRerankDocuments:
    def test_empty_docs(self):
        from backend.rag.rag_utils import _rerank_documents
        result, meta = _rerank_documents("query", [], 5)
        assert result == []

    def test_rerank_disabled_passthrough(self):
        from backend.rag.rag_utils import _rerank_documents
        docs = [_make_doc(score=0.5), _make_doc(score=0.9)]
        with patch("backend.rag.rag_utils.LOCAL_RERANKER", False), \
             patch("backend.rag.rag_utils.RERANK_API_KEY", ""):
            result, meta = _rerank_documents("query", docs, 5)
            assert len(result) == 2
            assert meta["rerank_applied"] is False

    def test_rrf_rank_added(self):
        from backend.rag.rag_utils import _rerank_documents
        docs = [_make_doc(score=0.5), _make_doc(score=0.9)]
        with patch("backend.rag.rag_utils.LOCAL_RERANKER", False), \
             patch("backend.rag.rag_utils.RERANK_API_KEY", ""):
            result, meta = _rerank_documents("query", docs, 5)
            assert all("rrf_rank" in d for d in result)
            assert result[0]["rrf_rank"] == 1


class TestCitationBoost:
    def test_no_refs_in_query(self):
        from backend.rag.rag_utils import _citation_boost
        docs = [_make_doc(text="some text")]
        result = _citation_boost(docs, "what is MPC?")
        assert len(result) == 1

    def test_cited_docs_moved_forward(self):
        from backend.rag.rag_utils import _citation_boost
        docs = [
            _make_doc(text="plain text no citation"),
            _make_doc(text="text with [1] citation"),
        ]
        with patch("backend.rag.rag_utils.extract_citation_refs") as mock_extract:
            mock_extract.side_effect = lambda t: ["1"] if "[1]" in t else []
            result = _citation_boost(docs, "关于[1]的论文")
            assert "[1]" in result[0]["text"]

    def test_empty_docs(self):
        from backend.rag.rag_utils import _citation_boost
        result = _citation_boost([], "query [1]")
        assert result == []


class TestEmptyRetrieveResult:
    def test_structure(self):
        from backend.rag.rag_utils import _empty_retrieve_result
        result = _empty_retrieve_result(15)
        assert "docs" in result
        assert "meta" in result
        assert result["docs"] == []
        assert result["meta"]["retrieval_mode"] == "failed"


class TestRetrieveDocuments:
    def test_hybrid_success(self):
        from backend.rag.rag_utils import retrieve_documents
        embedding = MagicMock()
        embedding.get_embeddings.return_value = [[0.1] * 1024]
        embedding.get_sparse_embedding.return_value = {0: 0.5}
        milvus = MagicMock()
        milvus.hybrid_retrieve.return_value = [
            _make_doc(id=1, chunk_level=3, score=0.9),
        ]

        with patch("backend.rag.rag_utils.get_embedding_service", return_value=embedding), \
             patch("backend.rag.rag_utils.get_milvus_manager", return_value=milvus), \
             patch("backend.rag.rag_utils._formula_search", return_value=[]), \
             patch("backend.rag.rag_utils._rerank_documents") as mock_rerank, \
             patch("backend.rag.rag_utils._auto_merge_documents") as mock_merge, \
             patch("backend.rag.rag_utils._expand_context") as mock_expand, \
             patch("backend.rag.rag_utils._citation_boost", side_effect=lambda d, q: d):
            mock_rerank.return_value = ([_make_doc()], {"rerank_applied": False})
            mock_merge.return_value = ([_make_doc()], {"auto_merge_applied": False})
            mock_expand.return_value = ([_make_doc()], {"expanded_chunk_count": 0})

            result = retrieve_documents("test query")
            assert "docs" in result
            assert "meta" in result
            milvus.hybrid_retrieve.assert_called_once()

    def test_hybrid_fallback_to_dense(self):
        from backend.rag.rag_utils import retrieve_documents
        embedding = MagicMock()
        embedding.get_embeddings.return_value = [[0.1] * 1024]
        embedding.get_sparse_embedding.return_value = {0: 0.5}
        milvus = MagicMock()
        milvus.hybrid_retrieve.side_effect = RuntimeError("Hybrid failed")
        milvus.dense_retrieve.return_value = [
            _make_doc(id=1, chunk_level=3, score=0.8),
        ]

        with patch("backend.rag.rag_utils.get_embedding_service", return_value=embedding), \
             patch("backend.rag.rag_utils.get_milvus_manager", return_value=milvus), \
             patch("backend.rag.rag_utils._formula_search", return_value=[]), \
             patch("backend.rag.rag_utils._rerank_documents") as mock_rerank, \
             patch("backend.rag.rag_utils._auto_merge_documents") as mock_merge, \
             patch("backend.rag.rag_utils._expand_context") as mock_expand, \
             patch("backend.rag.rag_utils._citation_boost", side_effect=lambda d, q: d):
            mock_rerank.return_value = ([_make_doc()], {"rerank_applied": False})
            mock_merge.return_value = ([_make_doc()], {"auto_merge_applied": False})
            mock_expand.return_value = ([_make_doc()], {"expanded_chunk_count": 0})

            result = retrieve_documents("test query")
            assert result["meta"]["retrieval_mode"] == "dense_fallback"
            milvus.dense_retrieve.assert_called_once()

    def test_all_fail_returns_empty(self):
        from backend.rag.rag_utils import retrieve_documents
        embedding = MagicMock()
        embedding.get_embeddings.return_value = [[0.1] * 1024]
        embedding.get_sparse_embedding.return_value = {0: 0.5}
        milvus = MagicMock()
        milvus.hybrid_retrieve.side_effect = RuntimeError("Hybrid failed")
        milvus.dense_retrieve.side_effect = RuntimeError("Dense also failed")

        with patch("backend.rag.rag_utils.get_embedding_service", return_value=embedding), \
             patch("backend.rag.rag_utils.get_milvus_manager", return_value=milvus), \
             patch("backend.rag.rag_utils._formula_search", return_value=[]):
            result = retrieve_documents("test query")
            assert result["docs"] == []
            assert result["meta"]["retrieval_mode"] == "failed"
