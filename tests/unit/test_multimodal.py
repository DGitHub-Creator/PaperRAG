"""多模态检索模块测试。

由于 CLIP + Milvus 外部依赖不可用，测试主要覆盖：
  - FigureExtractor 降级返回空列表
  - MultimodalEmbedding 模型未加载时返回占位向量
  - MultimodalRetriever 降级返回空结果
  - 全局单例模式
"""

from unittest.mock import MagicMock, patch

from backend.rag.multimodal import (
    FigureExtractor,
    MultimodalEmbedding,
    MultimodalRetriever,
    get_multimodal_retriever,
    reset_multimodal_retriever,
)


class TestFigureExtractor:
    def test_extract_figures_fitz_raises(self):
        extractor = FigureExtractor()
        import fitz

        def _fake_open(*args, **kwargs):
            raise RuntimeError("mock error")

        with patch.object(fitz, "open", side_effect=_fake_open):
            result = extractor.extract_figures("test.pdf")
            assert result == []




class TestMultimodalEmbedding:
    def setup_method(self):
        self.embedder = MultimodalEmbedding()

    def test_embed_text_mocked(self):
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_instance = MagicMock()
            mock_instance.encode.return_value = [[0.1, 0.2, 0.3]]
            mock_st.return_value = mock_instance
            self.embedder._model = None
            result = self.embedder.embed_text(["hello"])
            assert len(result) == 1
            mock_instance.encode.assert_called_once_with(
                ["hello"], normalize_embeddings=True,
            )

    def test_embed_image_mocked(self):
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_instance = MagicMock()
            mock_instance.encode.return_value = [[0.1, 0.2, 0.3]]
            mock_st.return_value = mock_instance
            with patch("PIL.Image.open") as mock_img:
                mock_img.return_value.convert.return_value = MagicMock()
                self.embedder._model = None
                result = self.embedder.embed_image([b"fake"])
                assert len(result) == 1
                mock_instance.encode.assert_called_once()

    def test_embed_text_empty(self):
        result = self.embedder.embed_text([])
        assert result == []

    def test_embed_image_empty(self):
        result = self.embedder.embed_image([])
        assert result == []

    def test_embed_text_model_fail(self):
        embedder = MultimodalEmbedding()
        with patch.object(embedder, "_load") as mock_load:
            mock_load.side_effect = None
            embedder._model = None
            result = embedder.embed_text(["hello"])
            assert result == [[0.0]]


class TestMultimodalRetriever:
    def setup_method(self):
        reset_multimodal_retriever()
        self.retriever = MultimodalRetriever()

    def test_search_by_text_no_milvus(self):
        with patch.object(self.retriever, "_get_milvus", return_value=None):
            result = self.retriever.search_by_text("test query")
            assert result == []

    def test_index_figures_empty(self):
        self.retriever.index_figures([], "test.pdf", "/tmp/test.pdf")

    def test_get_multimodal_retriever(self):
        r1 = get_multimodal_retriever()
        r2 = get_multimodal_retriever()
        assert r1 is r2

    def test_reset_multimodal_retriever(self):
        r1 = get_multimodal_retriever()
        reset_multimodal_retriever()
        r2 = get_multimodal_retriever()
        assert r1 is not r2

    def test_search_by_text_milvus_available(self):
        with patch.object(self.retriever, "_get_milvus") as mock_get:
            mock_milvus = MagicMock()
            mock_get.return_value = mock_milvus
            with patch.object(self.retriever._embedding, "embed_text") as mock_emb:
                mock_emb.return_value = [[0.1] * 512]
                mock_milvus.client.search.return_value = [[{
                    "id": 1, "filename": "test.pdf", "page_number": 1,
                }]]
                result = self.retriever.search_by_text("test")
                assert len(result) == 1
                assert result[0]["filename"] == "test.pdf"

    def test_index_figures_with_data(self):
        figures = [
            {"page_number": 1, "image_data": b"fake1", "width": 100, "height": 100, "ext": "png", "source": "embedded"},
        ]
        with patch.object(self.retriever, "_get_milvus") as mock_get:
            mock_milvus = MagicMock()
            mock_get.return_value = mock_milvus
            with patch.object(self.retriever._embedding, "embed_image") as mock_emb:
                mock_emb.return_value = [[0.1] * 512]
                self.retriever.index_figures(figures, "test.pdf", "/tmp/test.pdf")
                mock_milvus.client.insert.assert_called_once()
