from backend.rag.citation_extractor import extract_citation_refs, extract_citations, has_citations


class TestExtractCitations:
    def test_bracket_numbers(self):
        result = extract_citations("Prior work [1,2] showed this [3].")
        raws = [c.raw for c in result]
        assert "[1,2]" in raws
        assert "[3]" in raws

    def test_bracket_author_year(self):
        result = extract_citations("[Smith et al., 2020] proposed a method.")
        raws = [c.raw for c in result]
        assert any("Smith" in r and "2020" in r for r in raws)

    def test_paren_author_year(self):
        result = extract_citations("The method (Zhang, 2021) is effective.")
        raws = [c.raw for c in result]
        assert any("Zhang" in r and "2021" in r for r in raws)

    def test_latex_cite(self):
        result = extract_citations(r"As shown in \cite{label2024}.")
        raws = [c.raw for c in result]
        assert "label2024" in raws

    def test_author_paren_year(self):
        result = extract_citations("Lee (2022) demonstrated this.")
        raws = [c.raw for c in result]
        assert any("Lee" in r and "2022" in r for r in raws)

    def test_plain_text_no_citations(self):
        assert extract_citations("This is just some text.") == []

    def test_multiple_citations_on_same_line(self):
        result = extract_citations("Refs [1] and [2] are relevant [3].")
        assert len(result) >= 2


class TestCitationRefs:
    def test_single_ref(self):
        assert extract_citation_refs("See [1].") == ["1"]

    def test_multi_ref(self):
        refs = extract_citation_refs("See [1,2,3].")
        assert refs == ["1", "2", "3"]

    def test_range_ref(self):
        refs = extract_citation_refs("See [1-3].")
        assert "1" in refs
        assert "3" in refs

    def test_no_refs(self):
        assert extract_citation_refs("Plain text.") == []


class TestHasCitations:
    def test_has_bracket_num(self):
        assert has_citations("See [1].")

    def test_has_author_year(self):
        assert has_citations("[Author, 2020]")

    def test_no_citations(self):
        assert not has_citations("Just plain text.")
