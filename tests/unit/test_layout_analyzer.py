from backend.rag.layout_analyzer import LayoutBlock, extract_regions_by_type
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.rag import layout_analyzer


@pytest.mark.parametrize("fail", [False, True])
def test_layout_releases_pdf_and_temporary_images(tmp_path, monkeypatch, fail):
    import sys
    import fitz

    document = MagicMock()
    document.__enter__.return_value = document
    document.__len__.return_value = 1
    written = []

    def save(path):
        written.append(Path(path))
        Path(path).write_bytes(b"image")

    document.__getitem__.return_value.get_pixmap.return_value.save.side_effect = save
    monkeypatch.setattr(fitz, "open", lambda _: document)
    model = MagicMock()
    model.detect.return_value = []
    if fail:
        model.detect.side_effect = RuntimeError("检测失败")
    monkeypatch.setattr(layout_analyzer, "_load_model", lambda *_: model)
    monkeypatch.setitem(sys.modules, "layoutparser", SimpleNamespace(load_image=lambda path: path))
    # 临时目录由系统创建，测试不依赖 /tmp 或平台固定路径。
    assert layout_analyzer.analyze_layout("paper.pdf") == []
    document.__exit__.assert_called_once()
    assert written
    assert not written[0].parent.exists()


class TestLayoutBlock:
    def test_creates_block(self):
        block = LayoutBlock(
            block_type="Text",
            page_number=1,
            x1=0, y1=0, x2=100, y2=50,
            text="Hello",
        )
        assert block.block_type == "Text"
        assert block.page_number == 1
        assert block.text == "Hello"

    def test_repr(self):
        block = LayoutBlock("Figure", 0, 0, 0, 10, 10, "")
        assert block.block_type == "Figure"


class TestExtractRegionsByType:
    def setup_method(self):
        self.blocks = [
            LayoutBlock("Text", 0, 0, 0, 10, 10, "text"),
            LayoutBlock("Figure", 0, 0, 0, 10, 10, ""),
            LayoutBlock("Table", 1, 0, 0, 10, 10, ""),
            LayoutBlock("Text", 1, 0, 0, 10, 10, "more"),
        ]

    def test_filter_figures(self):
        result = extract_regions_by_type(self.blocks, {"Figure"})
        assert len(result) == 1
        assert result[0].block_type == "Figure"

    def test_filter_tables(self):
        result = extract_regions_by_type(self.blocks, {"Table"})
        assert len(result) == 1
        assert result[0].block_type == "Table"

    def test_filter_multiple(self):
        result = extract_regions_by_type(self.blocks, {"Figure", "Table"})
        assert len(result) == 2

    def test_no_match(self):
        result = extract_regions_by_type(self.blocks, {"Formula"})
        assert result == []

    def test_empty_input(self):
        assert extract_regions_by_type([], {"Text"}) == []
