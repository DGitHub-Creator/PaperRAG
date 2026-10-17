"""BM25 向量化服务和分词测试。

注意：conftest.py 已自动 patch HuggingFaceEmbeddings，
避免模块级 singleton 构造时下载模型。
"""

import tempfile
from pathlib import Path

from backend.rag.embedding import EmbeddingService


def _make_service(state_path: Path | None = None) -> EmbeddingService:
    return EmbeddingService(state_path=state_path or _tmp_state())


def _tmp_state() -> Path:
    return Path(tempfile.mktemp(suffix=".json"))


class TestEmbeddingServiceBM25:
    """BM25 分词和增量统计测试。"""

    def test_tokenize_chinese_chars(self):
        """中文字符应逐个成为独立 token。"""
        service = _make_service()
        tokens = service.tokenize("安全多方计算")
        assert len(tokens) == 6
        assert tokens == ["安", "全", "多", "方", "计", "算"]

    def test_tokenize_english_words(self):
        """英文字母应组成完整单词 token。"""
        service = _make_service()
        tokens = service.tokenize("Secure MPC protocol")
        assert "secure" in tokens
        assert "mpc" in tokens
        assert "protocol" in tokens

    def test_tokenize_mixed(self):
        """中英混合文本。"""
        service = _make_service()
        tokens = service.tokenize("MPC 安全多方计算 protocol")
        assert "mpc" in tokens
        assert "安" in tokens
        assert "protocol" in tokens

    def test_increment_add_documents(self):
        """增量添加文档应更新词频和文档数。"""
        service = _make_service()
        service.increment_add_documents(["MPC is secure", "安全多方计算"])
        assert service._total_docs == 2
        assert "mpc" in service._vocab
        assert "安" in service._vocab

    def test_increment_remove_documents(self):
        """增量删除应扣减词频和文档数。"""
        service = _make_service()
        service.increment_add_documents(["MPC protocol", "secure protocol", "protocol test"])
        assert service._total_docs == 3
        old_n = service._total_docs
        old_df = service._doc_freq.get("protocol", 0)

        service.increment_remove_documents(["MPC protocol"])
        assert service._total_docs == old_n - 1
        new_df = service._doc_freq.get("protocol", 0)
        assert new_df == old_df - 1

    def test_get_sparse_embedding(self):
        """稀疏向量应只包含 query 中出现的 token。"""
        service = _make_service()
        service.increment_add_documents(["security protocol", "MPC computation"])
        sparse = service.get_sparse_embedding("MPC security")
        assert isinstance(sparse, dict)
        assert len(sparse) > 0

    def test_state_persistence(self):
        """BM25 状态应能序列化到磁盘并恢复。"""
        tmp = _tmp_state()
        s1 = _make_service(state_path=tmp)
        s1.increment_add_documents(["test document one", "test document two"])

        s2 = _make_service(state_path=tmp)
        assert s2._total_docs == 2
        assert "test" in s2._vocab


def test_independent_instances_preserve_statistics_and_vocabulary(tmp_path):
    path = tmp_path / "bm25.json"
    first = _make_service(path)
    second = _make_service(path)
    first.increment_add_documents(["alpha beta"])
    second.increment_add_documents(["gamma delta"])
    first.get_sparse_embedding("newword")
    second.get_sparse_embedding("anotherword")
    reloaded = _make_service(path)
    assert reloaded._total_docs == 2
    assert set(reloaded._vocab) == {"alpha", "beta", "gamma", "delta", "newword", "anotherword"}
    assert len(set(reloaded._vocab.values())) == 6
    second.increment_remove_documents(["alpha beta"])
    assert _make_service(path)._total_docs == 1


def test_corrupt_bm25_never_resets_existing_dimensions(tmp_path):
    import pytest

    path = tmp_path / "bm25.json"
    service = _make_service(path)
    service.increment_add_documents(["existing document"])
    path.write_text("broken-json", encoding="utf-8")
    with pytest.raises(ValueError, match="拒绝覆盖"):
        service.increment_add_documents(["replacement"])
    assert path.read_text(encoding="utf-8") == "broken-json"


def test_real_huggingface_wrapper_passes_model_options_once(monkeypatch):
    from unittest.mock import MagicMock

    import sentence_transformers
    from langchain_huggingface.embeddings.huggingface import HuggingFaceEmbeddings
    from backend.rag import embedding

    observed = {}

    def construct(model_name, *, cache_folder, device, trust_remote_code):
        observed.update(model_name=model_name, cache_folder=cache_folder, device=device, trust_remote_code=trust_remote_code)
        return MagicMock()

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", construct)
    monkeypatch.setattr(embedding, "HuggingFaceEmbeddings", HuggingFaceEmbeddings)
    embedding._create_dense_embedder()
    assert observed["cache_folder"] == embedding.HF_HOME
    assert observed["trust_remote_code"] is False


def test_local_tiny_model_runs_real_updated_embedding_stack(tmp_path, monkeypatch):
    """真实运行依赖栈的 CPU 前向；随机小模型仅验兼容性，不代表 BGE 检索质量。"""
    import math

    from transformers import BertConfig, BertModel, BertTokenizer
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.sentence_transformer.modules import Transformer, Pooling
    from langchain_huggingface.embeddings.huggingface import HuggingFaceEmbeddings

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    base = tmp_path / "tiny-bert"
    BertModel(BertConfig(vocab_size=8, hidden_size=16, num_hidden_layers=1, num_attention_heads=2, intermediate_size=32)).save_pretrained(base)
    vocabulary = {word: index for index, word in enumerate(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "hello", "world", "research"])}
    BertTokenizer(vocab=vocabulary).save_pretrained(base)
    transformer = Transformer(str(base), model_args={"local_files_only": True})
    target = tmp_path / "tiny-sentence-model"
    SentenceTransformer(modules=[transformer, Pooling(16)]).save(str(target))
    embedder = HuggingFaceEmbeddings(model_name=str(target), model_kwargs={"device": "cpu", "local_files_only": True}, encode_kwargs={"normalize_embeddings": True})
    vectors = embedder.embed_documents(["hello world", "research"])
    assert len(vectors) == 2
    assert all(len(vector) == 16 and all(math.isfinite(value) for value in vector) for vector in vectors)
    assert all(abs(sum(value * value for value in vector) - 1.0) < 1e-5 for vector in vectors)
