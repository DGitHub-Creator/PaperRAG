"""Tests for the citation verification module."""

from backend.agent.verify import _locator_matches, extract_citations, verify_citations


class TestExtractCitations:
    """Test citation extraction."""

    def test_extract_single_citation(self):
        answer = "BERT is a transformer model [bert.pdf (p.1)]."
        citations = extract_citations(answer)
        assert len(citations) == 1
        assert citations[0]["text"] == "bert.pdf (p.1)"

    def test_extract_multiple_citations(self):
        answer = "BERT [bert.pdf (p.1)] uses attention [bert.pdf (p.3)]."
        citations = extract_citations(answer)
        assert len(citations) == 2
        assert citations[0]["text"] == "bert.pdf (p.1)"
        assert citations[1]["text"] == "bert.pdf (p.3)"

    def test_extract_no_citations(self):
        answer = "No citations here."
        citations = extract_citations(answer)
        assert len(citations) == 0


class TestLocatorMatches:
    """Test locator matching."""

    def test_exact_match(self):
        assert _locator_matches("bert.pdf (p.1)", "bert.pdf (p.1)") is True

    def test_case_insensitive_filename(self):
        assert _locator_matches("BERT.pdf (p.1)", "bert.pdf (p.1)") is True

    def test_different_page(self):
        assert _locator_matches("bert.pdf (p.1)", "bert.pdf (p.2)") is False

    def test_different_file(self):
        assert _locator_matches("bert.pdf (p.1)", "rag.pdf (p.1)") is False


class TestVerifyCitations:
    """Test citation verification."""

    def test_verified_citation(self):
        citations = [{"text": "bert.pdf (p.1)"}]
        locators = ["bert.pdf (p.1)", "rag.pdf (p.2)"]
        verified, unsupported = verify_citations(citations, locators, [])
        assert len(verified) == 1
        assert len(unsupported) == 0

    def test_unsupported_citation(self):
        citations = [{"text": "unknown.pdf (p.1)"}]
        locators = ["bert.pdf (p.1)", "rag.pdf (p.2)"]
        verified, unsupported = verify_citations(citations, locators, [])
        assert len(verified) == 0
        assert len(unsupported) == 1

    def test_mixed_citations(self):
        citations = [
            {"text": "bert.pdf (p.1)"},
            {"text": "unknown.pdf (p.1)"},
            {"text": "rag.pdf (p.2)"},
        ]
        locators = ["bert.pdf (p.1)", "rag.pdf (p.2)"]
        verified, unsupported = verify_citations(citations, locators, [])
        assert len(verified) == 2
        assert len(unsupported) == 1
