"""Tests for citation extraction logic."""

import re

import pytest


def extract_citations(text: str, rag_trace: dict | None) -> list[dict]:
    if not text or not rag_trace:
        return []

    indices = {int(m) for m in re.findall(r"\[(\d+)\]", text)}
    if not indices:
        return []

    chunks = rag_trace.get("retrieved_chunks") or []
    citations = []
    for idx in sorted(indices):
        if 1 <= idx <= len(chunks):
            chunk = chunks[idx - 1]
            citations.append({
                "index": idx,
                "filename": chunk.get("filename", ""),
                "page": chunk.get("page_number"),
                "chunk_idx": chunk.get("child_idx"),
            })
    return citations


class TestExtractCitations:

    def test_single_citation(self):
        text = "According to [1], the theorem states that x = 1."
        rag_trace = {
            "retrieved_chunks": [
                {"filename": "paper.pdf", "page_number": 5, "child_idx": 0},
            ]
        }
        result = extract_citations(text, rag_trace)
        assert len(result) == 1
        assert result[0]["index"] == 1
        assert result[0]["filename"] == "paper.pdf"
        assert result[0]["page"] == 5

    def test_multiple_citations(self):
        text = "As shown in [1] and [3], the results differ."
        rag_trace = {
            "retrieved_chunks": [
                {"filename": "a.pdf", "page_number": 1, "child_idx": 0},
                {"filename": "b.pdf", "page_number": 2, "child_idx": 1},
                {"filename": "c.pdf", "page_number": 3, "child_idx": 2},
            ]
        }
        result = extract_citations(text, rag_trace)
        assert len(result) == 2
        assert result[0]["index"] == 1
        assert result[1]["index"] == 3

    def test_no_citations(self):
        text = "This is a general statement with no references."
        rag_trace = {"retrieved_chunks": [{"filename": "a.pdf"}]}
        result = extract_citations(text, rag_trace)
        assert result == []

    def test_empty_text(self):
        result = extract_citations("", {"retrieved_chunks": []})
        assert result == []

    def test_none_rag_trace(self):
        result = extract_citations("According to [1] something.", None)
        assert result == []

    def test_citation_out_of_range(self):
        text = "Reference [5] is out of range."
        rag_trace = {
            "retrieved_chunks": [
                {"filename": "a.pdf", "page_number": 1},
            ]
        }
        result = extract_citations(text, rag_trace)
        assert result == []

    def test_citation_without_chunks(self):
        text = "According to [1] something."
        rag_trace = {}
        result = extract_citations(text, rag_trace)
        assert result == []

    def test_citation_with_none_fields(self):
        text = "Based on [1] and [2]."
        rag_trace = {
            "retrieved_chunks": [
                {"filename": "a.pdf", "page_number": None, "child_idx": None},
                {"filename": "b.pdf"},
            ]
        }
        result = extract_citations(text, rag_trace)
        assert len(result) == 2
        assert result[0]["page"] is None
        assert result[0]["chunk_idx"] is None

    def test_deduplication(self):
        text = "As shown in [1], [1], and [1] again."
        rag_trace = {
            "retrieved_chunks": [
                {"filename": "a.pdf", "page_number": 1},
            ]
        }
        result = extract_citations(text, rag_trace)
        assert len(result) == 1
        assert result[0]["index"] == 1

    def test_sorted_indices(self):
        text = "Reference [3] and [1] and [2]."
        rag_trace = {
            "retrieved_chunks": [
                {"filename": "a.pdf", "page_number": 1},
                {"filename": "b.pdf", "page_number": 2},
                {"filename": "c.pdf", "page_number": 3},
            ]
        }
        result = extract_citations(text, rag_trace)
        assert [c["index"] for c in result] == [1, 2, 3]
