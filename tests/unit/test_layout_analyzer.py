from backend.rag.layout_analyzer import LayoutBlock, extract_regions_by_type


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
