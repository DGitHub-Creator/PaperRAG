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
        s1._persist()

        s2 = _make_service(state_path=tmp)
        s2._load_state()
        assert s2._total_docs == 2
        assert "test" in s2._vocab
