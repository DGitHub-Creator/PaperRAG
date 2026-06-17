"""Tests for layout analysis helpers and clean_paper_text_with_layout."""

from unittest.mock import MagicMock
from backend.rag.academic_cleaner import (
    _group_chars_into_lines,
    _is_caption,
    _is_reference_line,
    analyze_page_layout,
    clean_paper_text_with_layout,
)


def _make_char(text, top, bottom, x0, x1):
    return {'text': text, 'top': top, 'bottom': bottom, 'x0': x0, 'x1': x1}


class TestGroupCharsIntoLines:
    def test_single_line(self):
        chars = [_make_char('A', 10, 20, 0, 10), _make_char('B', 10, 20, 11, 20)]
        lines = _group_chars_into_lines(chars, y_tolerance=2)
        assert len(lines) == 1
        assert lines[0]['text'] == 'AB'

    def test_two_lines(self):
        chars = [
            _make_char('A', 10, 20, 0, 10),
            _make_char('B', 10, 20, 11, 20),
            _make_char('C', 30, 40, 0, 10),
            _make_char('D', 30, 40, 11, 20),
        ]
        lines = _group_chars_into_lines(chars, y_tolerance=2)
        assert len(lines) == 2
        assert lines[0]['text'] == 'AB'
        assert lines[1]['text'] == 'CD'

    def test_tolerance_grouping(self):
        chars = [
            _make_char('A', 10, 20, 0, 10),
            _make_char('B', 11, 21, 11, 20),
        ]
        lines = _group_chars_into_lines(chars, y_tolerance=2)
        assert len(lines) == 1

    def test_empty_chars(self):
        assert _group_chars_into_lines([], y_tolerance=2) == []


class TestIsCaption:
    def test_figure(self):
        assert _is_caption("Figure 1: Architecture overview")
        assert _is_caption("Fig. 2: Results")
        assert _is_caption("Figure~3: Test")

    def test_table(self):
        assert _is_caption("Table 1: Performance comparison")
        assert _is_caption("表 2: 实验结果")

    def test_not_caption(self):
        assert not _is_caption("This is normal text")
        assert not _is_caption("FigureX1")  # no space before digit


class TestIsReferenceLine:
    def test_reference(self):
        assert _is_reference_line("[1] Smith et al. Some paper.")
        assert _is_reference_line("[42] Jones. Another paper.")

    def test_not_reference(self):
        assert not _is_reference_line("Normal text without brackets")
        assert not _is_reference_line("[42]No space after bracket")


class TestAnalyzePageLayout:
    def _mock_page(self, width=600, height=800, chars=None, images=None, tables=None):
        page = MagicMock()
        page.width = width
        page.height = height
        page.chars = chars or []
        page.images = images or []
        page.find_tables.return_value = tables or []
        return page

    def test_header_footer_detection(self):
        chars = [
            _make_char('Conference 2025', 20, 30, 200, 400),  # top 10% → header
            _make_char('Main body text here', 400, 410, 50, 550),  # middle → text
            _make_char('Page 42', 760, 770, 280, 320),  # bottom 10% → footer
        ]
        page = self._mock_page(chars=chars)
        regions = analyze_page_layout(page)
        types = [r['type'] for r in regions]
        assert 'header_footer' in types
        assert 'text' in types

    def test_caption_detection(self):
        chars = [
            _make_char('Figure 1: Architecture', 400, 410, 50, 300),
        ]
        page = self._mock_page(chars=chars)
        regions = analyze_page_layout(page)
        assert any(r['type'] == 'caption' for r in regions)

    def test_reference_detection(self):
        chars = [
            _make_char('[1] Smith et al. Paper.', 400, 410, 50, 400),
        ]
        page = self._mock_page(chars=chars)
        regions = analyze_page_layout(page)
        assert any(r['type'] == 'reference' for r in regions)

    def test_images_detected(self):
        images = [{'x0': 100, 'top': 200, 'x1': 400, 'bottom': 350}]
        page = self._mock_page(chars=[_make_char('text', 400, 410, 50, 200)], images=images)
        regions = analyze_page_layout(page)
        assert any(r['type'] == 'image' for r in regions)

    def test_empty_page(self):
        page = self._mock_page(chars=[])
        assert analyze_page_layout(page) == []


class TestCleanPaperTextWithLayout:
    def test_keeps_body_text(self):
        regions = [
            {'type': 'text', 'bbox': (0, 0, 10, 10), 'content': 'Body text here'},
        ]
        result = clean_paper_text_with_layout("raw", regions)
        assert result == 'Body text here'

    def test_keeps_captions(self):
        regions = [
            {'type': 'caption', 'bbox': (0, 0, 10, 10), 'content': 'Figure 1: Test'},
        ]
        result = clean_paper_text_with_layout("raw", regions)
        assert 'Figure 1: Test' in result

    def test_removes_headers_and_references(self):
        regions = [
            {'type': 'header_footer', 'bbox': (0, 0, 10, 10), 'content': 'EUROCRYPT 2025'},
            {'type': 'reference', 'bbox': (0, 0, 10, 10), 'content': '[1] Smith paper'},
            {'type': 'text', 'bbox': (0, 0, 10, 10), 'content': 'Important body'},
        ]
        result = clean_paper_text_with_layout("raw", regions)
        assert 'EUROCRYPT' not in result
        assert 'Smith' not in result
        assert 'Important body' in result

    def test_fallback_to_regex(self):
        result = clean_paper_text_with_layout("Some text\n42\nMore", regions=None)
        assert "Some text" in result
        assert "More" in result
