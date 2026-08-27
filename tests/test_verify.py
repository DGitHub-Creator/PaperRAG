"""Tests for the citation verification module.

引用使用 ``[Source N]`` 标签格式，与 search_knowledge_base 工具的
source_map 对应。
"""

from langchain_core.messages import AIMessage

from backend.agent.verify import extract_citations, extract_outcome, verify_citations


def _sample_source_map():
    return {
        "Source 1": {
            "filename": "bert.pdf",
            "page": 1,
            "chunk_id": "bert.pdf#1#0",
        },
        "Source 2": {
            "filename": "rag.pdf",
            "page": 3,
            "chunk_id": "rag.pdf#3#2",
        },
    }


class TestExtractCitations:
    """Test citation extraction."""

    def test_extract_single_citation(self):
        answer = "BERT is a transformer model [Source 1]."
        citations = extract_citations(answer)
        assert len(citations) == 1
        assert citations[0]["text"] == "Source 1"

    def test_extract_multiple_citations(self):
        answer = "BERT [Source 1] uses attention [Source 2]."
        citations = extract_citations(answer)
        assert len(citations) == 2
        assert citations[0]["text"] == "Source 1"
        assert citations[1]["text"] == "Source 2"

    def test_deduplicates_repeated_labels(self):
        answer = "Claim A [Source 1] and claim B [Source 1]."
        citations = extract_citations(answer)
        assert len(citations) == 1

    def test_case_insensitive_and_spacing(self):
        answer = "Claim [source 3] and [ Source 4 ] here."
        citations = extract_citations(answer)
        assert [c["text"] for c in citations] == ["Source 3", "Source 4"]

    def test_extract_no_citations(self):
        answer = "No citations here."
        assert extract_citations(answer) == []

    def test_ignores_non_source_brackets(self):
        answer = "See [Figure 2] and [Table 1] for details."
        assert extract_citations(answer) == []

    def test_empty_answer(self):
        assert extract_citations("") == []


class TestVerifyCitations:
    """Test citation verification against source_map."""

    def test_verified_citation(self):
        citations = extract_citations("Fact [Source 1].")
        verified, unsupported = verify_citations(citations, _sample_source_map())
        assert len(verified) == 1
        assert len(unsupported) == 0
        assert verified[0]["locator"]["filename"] == "bert.pdf"
        assert verified[0]["locator"]["page"] == 1

    def test_unsupported_citation(self):
        citations = extract_citations("Fact [Source 9].")
        verified, unsupported = verify_citations(citations, _sample_source_map())
        assert len(verified) == 0
        assert len(unsupported) == 1
        assert unsupported[0]["text"] == "Source 9"

    def test_mixed_citations(self):
        answer = "A [Source 1], b [Source 9], c [Source 2]."
        citations = extract_citations(answer)
        verified, unsupported = verify_citations(citations, _sample_source_map())
        assert len(verified) == 2
        assert len(unsupported) == 1

    def test_none_source_map_marks_all_unsupported(self):
        citations = extract_citations("Fact [Source 1].")
        verified, unsupported = verify_citations(citations, None)
        assert len(verified) == 0
        assert len(unsupported) == 1

    def test_empty_source_map_marks_all_unsupported(self):
        citations = extract_citations("Fact [Source 1].")
        verified, unsupported = verify_citations(citations, {})
        assert len(verified) == 0
        assert len(unsupported) == 1


class TestExtractOutcome:
    """Test end-to-end outcome extraction from agent messages."""

    def test_answer_tool_call_with_citations(self):
        class _FakeToolCall:
            def __init__(self, name, args):
                self.name = name
                self.args = args

        msg = AIMessage(content="")
        msg.tool_calls = [
            {"name": "Answer", "args": {"answer": "The method works [Source 2]."}}
        ]
        outcome = extract_outcome([msg], source_map=_sample_source_map())
        assert outcome["answer"] == "The method works [Source 2]."
        assert outcome["verified_count"] == 1
        assert outcome["unsupported_count"] == 0
        assert outcome["citations"][0]["filename"] == "rag.pdf"
        assert outcome["citations"][0]["supported"] is True

    def test_plain_ai_message_fallback(self):
        msg = AIMessage(content="Some answer without tool call [Source 1].")
        outcome = extract_outcome([msg], source_map=_sample_source_map())
        assert outcome["verified_count"] == 1

    def test_unsupported_included_with_reason(self):
        msg = AIMessage(content="Hallucinated [Source 42].")
        outcome = extract_outcome([msg], source_map=_sample_source_map())
        assert outcome["unsupported_count"] == 1
        assert outcome["unsupported"][0]["supported"] is False
        assert outcome["unsupported"][0]["reason"]

    def test_out_of_scope_message(self):
        msg = AIMessage(content="该问题超出知识库范围，无法回答。")
        outcome = extract_outcome([msg], source_map={})
        assert outcome["citations"] == []
        assert outcome["unsupported"] == []
