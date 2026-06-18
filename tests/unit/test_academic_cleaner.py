"""Tests for backend.rag.academic_cleaner — academic text cleaning."""

from backend.rag.academic_cleaner import clean_paper_text


class TestCleanPaperText:
    """Tests for the two-phase academic text cleaner."""

    def test_removes_page_numbers(self):
        """Standalone page numbers should be removed."""
        text = "Some content\n42\nMore content"
        result = clean_paper_text(text)
        assert "42" not in result.split("\n")
        assert "Some content" in result
        assert "More content" in result

    def test_removes_decorated_page_numbers(self):
        """Page numbers with single dashes should be removed."""
        text = "Content\n- 15 -\nMore"
        result = clean_paper_text(text)
        assert "- 15 -" not in result

    def test_removes_header_footer(self):
        """Lines matching conference header patterns should be removed."""
        text = "Real content\nEUROCRYPT 2025\nMore content"
        result = clean_paper_text(text)
        assert "EUROCRYPT 2025" not in result
        assert "Real content" in result

    def test_removes_springer_verlag(self):
        """Springer-Verlag footer should be removed."""
        text = "Content\nSpringer-Verlag Berlin Heidelberg 2023\nMore"
        result = clean_paper_text(text)
        assert "Springer-Verlag" not in result

    def test_preserves正文方括号编号(self):
        """Lines with [N] that are NOT reference blocks should be kept."""
        text = "Content\n[42] This is a theorem statement.\nMore content"
        result = clean_paper_text(text)
        assert "[42] This is a theorem statement." in result

    def test_removes_reference_block(self):
        """A long block of [N] lines with citation clues should be removed."""
        refs = "\n".join([
            "[1] Smith et al. Proc. of Crypto 2020, pp. 1-20.",
            "[2] Jones et al. doi:10.1007/978-3-030-12345-6_1 vol. 12.",
            "[3] Lee et al. Proceedings of EUROCRYPT 2021, pp. 100-120.",
            "[4] Wang et al. doi:10.1007/s00145-020-09345-2 vol. 2.",
            "[5] Kim et al. Proc. of ASIACRYPT 2022, pp. 50-80.",
            "[6] Chen et al. doi:10.1007/978-3-030-99999-9_9 pp. 200-230.",
        ])
        text = f"Main content ends here.\n{refs}\n"
        result = clean_paper_text(text)
        assert "Main content ends here." in result
        assert "Smith et al." not in result

    def test_preserves_short_ref_block(self):
        """Reference block with <= 5 lines should be kept."""
        refs = "\n".join([
            "[1] Smith et al. doi:10.1007/001 pp. 1-10.",
            "[2] Jones et al. doi:10.1007/002 pp. 20-30.",
        ])
        text = f"Content\n{refs}\nMore"
        result = clean_paper_text(text)
        assert "Smith et al." in result

    def test_compresses_consecutive_blank_lines(self):
        """Multiple blank lines should be compressed to one."""
        text = "Line1\n\n\n\nLine2"
        result = clean_paper_text(text)
        assert "\n\n\n" not in result

    def test_removes_duplicate_short_lines(self):
        """Consecutive identical short lines should be deduplicated."""
        text = "Content\nRepeated header\nRepeated header\nMore"
        result = clean_paper_text(text)
        count = result.count("Repeated header")
        assert count == 1

    def test_preserves_long_duplicate_lines(self):
        """Long duplicate lines (>120 chars) should be kept."""
        long_line = "x" * 130
        text = f"Content\n{long_line}\n{long_line}\nMore"
        result = clean_paper_text(text)
        assert result.count(long_line) == 2

    def test_empty_input(self):
        """Empty input should return empty string."""
        assert clean_paper_text("") == ""

    def test_copyright_line_removed(self):
        """Copyright lines should be removed."""
        text = "Content\n© 2024 International Association\nMore"
        result = clean_paper_text(text)
        assert "© 2024" not in result
