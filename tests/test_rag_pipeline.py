"""LangGraph RAG 管线节点单元测试 —— mock LLM 输出。"""

import sys
from unittest.mock import MagicMock, patch

# Mock langgraph if not installed
for mod in ["langgraph", "langgraph.checkpoint", "langgraph.checkpoint.memory",
            "langgraph.graph", "langgraph.types"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Mock langchain.chat_models if not installed
if "langchain" not in sys.modules:
    sys.modules["langchain"] = MagicMock()
if "langchain.chat_models" not in sys.modules:
    sys.modules["langchain.chat_models"] = MagicMock()


def _make_state(overrides: dict | None = None) -> dict:
    """创建一个最小的 RAGState。"""
    state = {
        "question": "什么是安全多方计算？",
        "query": "什么是安全多方计算？",
        "context": "Some retrieved context about MPC.",
        "docs": [{"filename": "test.pdf", "page_number": 1, "text": "MPC is..."}],
        "route": None,
        "expansion_type": None,
        "expanded_query": None,
        "step_back_question": None,
        "step_back_answer": None,
        "hypothetical_doc": None,
        "rag_trace": None,
    }
    if overrides:
        state.update(overrides)
    return state


class TestGradeDocumentsNode:
    """测试 grade_documents_node 的分支逻辑。"""

    @patch("backend.rag.rag_pipeline.get_grader_model")
    def test_grade_yes_routes_to_generate(self, mock_get_grader):
        from backend.rag.rag_pipeline import grade_documents_node

        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = mock_model
        mock_model.invoke.return_value = MagicMock(binary_score="yes")
        mock_get_grader.return_value = mock_model

        state = _make_state()
        result = grade_documents_node(state)
        assert result["route"] == "generate_answer"
        assert result["rag_trace"]["grade_score"] == "yes"

    @patch("backend.rag.rag_pipeline.get_grader_model")
    def test_grade_no_routes_to_rewrite(self, mock_get_grader):
        from backend.rag.rag_pipeline import grade_documents_node

        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = mock_model
        mock_model.invoke.return_value = MagicMock(binary_score="no")
        mock_get_grader.return_value = mock_model

        state = _make_state()
        result = grade_documents_node(state)
        assert result["route"] == "rewrite_question"
        assert result["rag_trace"]["grade_score"] == "no"

    @patch("backend.rag.rag_pipeline.get_grader_model")
    def test_grader_unavailable_defaults_to_rewrite(self, mock_get_grader):
        from backend.rag.rag_pipeline import grade_documents_node

        mock_get_grader.return_value = None

        state = _make_state()
        result = grade_documents_node(state)
        assert result["route"] == "rewrite_question"


class TestRewriteQuestionNode:
    """测试 rewrite_question_node 的策略选择。"""

    @patch("backend.rag.rag_pipeline.get_router_model")
    @patch("backend.rag.rag_pipeline.step_back_expand")
    def test_strategy_step_back(self, mock_step_back, mock_get_router):
        from backend.rag.rag_pipeline import rewrite_question_node

        mock_router = MagicMock()
        mock_router.with_structured_output.return_value = mock_router
        mock_router.invoke.return_value = MagicMock(strategy="step_back")
        mock_get_router.return_value = mock_router

        mock_step_back.return_value = {
            "step_back_question": "What is MPC?",
            "step_back_answer": "MPC is a cryptographic primitive...",
            "expanded_query": "expanded query",
        }

        state = _make_state()
        result = rewrite_question_node(state)
        assert result["expansion_type"] == "step_back"
        assert result["rag_trace"]["rewrite_strategy"] == "step_back"

    @patch("backend.rag.rag_pipeline.get_router_model")
    @patch("backend.rag.rag_pipeline.step_back_expand")
    @patch("backend.rag.rag_pipeline.generate_hypothetical_document")
    def test_strategy_hyde(self, mock_hyde, mock_step_back, mock_get_router):
        from backend.rag.rag_pipeline import rewrite_question_node

        mock_router = MagicMock()
        mock_router.with_structured_output.return_value = mock_router
        mock_router.invoke.return_value = MagicMock(strategy="hyde")
        mock_get_router.return_value = mock_router

        mock_hyde.return_value = "Hypothetical document about MPC..."

        state = _make_state()
        result = rewrite_question_node(state)
        assert result["expansion_type"] == "hyde"
        assert result["rag_trace"]["rewrite_strategy"] == "hyde"

    @patch("backend.rag.rag_pipeline.get_router_model")
    @patch("backend.rag.rag_pipeline.step_back_expand")
    @patch("backend.rag.rag_pipeline.generate_hypothetical_document")
    def test_strategy_complex(self, mock_hyde, mock_step_back, mock_get_router):
        from backend.rag.rag_pipeline import rewrite_question_node

        mock_router = MagicMock()
        mock_router.with_structured_output.return_value = mock_router
        mock_router.invoke.return_value = MagicMock(strategy="complex")
        mock_get_router.return_value = mock_router

        mock_step_back.return_value = {
            "step_back_question": "Q",
            "step_back_answer": "A",
            "expanded_query": "expanded",
        }
        mock_hyde.return_value = "Hypothetical doc..."

        state = _make_state()
        result = rewrite_question_node(state)
        assert result["expansion_type"] == "complex"
        assert result["rag_trace"]["rewrite_strategy"] == "complex"


class TestRetrieveExpanded:
    """测试 retrieve_expanded 的去重和合并逻辑。"""

    @patch("backend.rag.rag_pipeline.retrieve_documents")
    def test_dedup(self, mock_retrieve):
        from backend.rag.rag_pipeline import retrieve_expanded

        mock_retrieve.return_value = {
            "docs": [
                {"filename": "a.pdf", "page_number": 1, "text": "same text"},
                {"filename": "a.pdf", "page_number": 1, "text": "same text"},
                {"filename": "b.pdf", "page_number": 2, "text": "different"},
            ],
            "meta": {},
        }

        state = _make_state({"expansion_type": "step_back", "expanded_query": "query"})
        result = retrieve_expanded(state)
        # 去重后应有 2 条（重复的合并）
        assert len(result["docs"]) == 2

    @patch("backend.rag.rag_pipeline.retrieve_documents")
    def test_empty_result(self, mock_retrieve):
        from backend.rag.rag_pipeline import retrieve_expanded

        mock_retrieve.return_value = {"docs": [], "meta": {}}

        state = _make_state({"expansion_type": "step_back", "expanded_query": "query"})
        result = retrieve_expanded(state)
        assert len(result["docs"]) == 0
        assert result["context"] == ""
