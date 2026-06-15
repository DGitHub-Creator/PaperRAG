"""文本向量化服务 —— 密集向量（BGE-M3）+ BM25 稀疏向量 + 统计持久化。

核心能力:
    - 密集向量: 基于 langchain_huggingface 的本地 BGE-M3 模型（1024 维，IP 度量）
    - BM25 稀疏向量: 中英混合规则分词（单字中文 + 英文单词），手写 BM25 算法
    - 状态持久化: vocab + doc_freq + N 落盘到 bm25_state.json，入库增量增加、删除扣减
    - 词表索引永不回收: 避免与 Milvus 历史稀疏向量维度冲突

BM25 参数:
    - k1=1.5: 词频饱和参数，控制 tf 对得分的影响幅度
    - b=0.75: 文档长度归一化参数，b=1 表示完全归一化，b=0 表示不归一化

分词策略:
    - 每个中文字符作为独立 token（中文语义粒度通常在字级）
    - 连续英文字母组成一个 token（英文语义在词级）
    - 标点、数字、空白符直接跳过

使用示例:
    >>> from backend.rag.embedding import embedding_service
    >>> dense_vec = embedding_service.get_embeddings(["查询文本"])
    >>> sparse_vec = embedding_service.get_sparse_embedding("查询文本")
"""

import json
import math
import re
import threading
from collections import Counter
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings

from backend.core.config import (
    BM25_STATE_PATH,
    EMBEDDING_MODEL,
    EMBEDDING_DEVICE,
    DENSE_EMBEDDING_DIM,
    HF_HOME,
)
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# 默认 BM25 状态文件路径（仅在环境变量未配置时使用）
_DEFAULT_STATE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "bm25_state.json"


def _create_dense_embedder() -> HuggingFaceEmbeddings:
    """创建 HuggingFace 稠密嵌入模型实例。

    使用 BAAI/bge-m3（多语言，1024 维），支持中英文混合检索。
    normalize_embeddings=True 确保向量归一化，与 Milvus IP（内积）度量配合。
    """
    model_name = EMBEDDING_MODEL or "BAAI/bge-m3"
    device = EMBEDDING_DEVICE or "cpu"
    logger.info("加载嵌入模型 '%s' (device=%s, cache=%s)", model_name, device, HF_HOME)
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device, "cache_folder": HF_HOME},
        encode_kwargs={"normalize_embeddings": True},
    )


class EmbeddingService:
    """文本向量化服务 —— 密集向量 + BM25 稀疏向量。

    全进程唯一实例（模块级 singleton），写入与检索共用同一份 BM25 持久化状态，
    保证统计一致性。

    Attributes:
        k1: BM25 词频饱和参数，默认 1.5
        b: BM25 文档长度归一化参数，默认 0.75
        _vocab: 词 → 稀疏向量维度下标的映射（永不回收）
        _doc_freq: 词 → 文档频次（用于 IDF 计算）
        _total_docs: 已索引的叶子 chunk 总数 (N)
        _sum_token_len: 所有文档的 token 长度之和（用于计算 avg_doc_len）
    """

    def __init__(self, state_path: Path | str | None = None):
        self._embedder = _create_dense_embedder()
        self._state_path = Path(state_path or BM25_STATE_PATH or _DEFAULT_STATE_PATH)
        self._lock = threading.Lock()

        # BM25 超参数 —— 经验值，适用于学术论文等中长文本
        self.k1 = 1.5       # 词频饱和参数
        self.b = 0.75       # 文档长度归一化

        # 内部统计状态
        self._vocab: dict[str, int] = {}        # 词 → 稀疏维度索引
        self._vocab_counter = 0                   # 下一个可用维度下标
        self._doc_freq: Counter[str] = Counter()  # 词 → 文档频次 (df)
        self._total_docs = 0                      # 总文档数 (N)
        self._sum_token_len = 0                    # 总 token 长度
        self._avg_doc_len = 1.0                    # 平均文档 token 长度

        self._load_state()
        logger.info(
            "BM25 状态已加载: vocab=%d, N=%d, avg_len=%.1f",
            len(self._vocab), self._total_docs, self._avg_doc_len,
        )

    # ── 辅助计算 ──────────────────────────────────────────────────

    def _recompute_avg_len(self) -> None:
        """重新计算平均文档长度（当 N 或 sum_token_len 变化时调用）。"""
        self._avg_doc_len = (
            self._sum_token_len / self._total_docs if self._total_docs > 0 else 1.0
        )

    # ── 状态持久化 ────────────────────────────────────────────────

    def _load_state(self) -> None:
        """从 bm25_state.json 加载 BM25 统计状态。

        文件不存在或损坏时静默跳过，后续入库会自动重建。
        版本号检查保证向后兼容。
        """
        path = self._state_path
        if not path.is_file():
            logger.info("BM25 状态文件不存在，将使用空统计: %s", path)
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("BM25 状态文件损坏，将使用空统计: %s", path)
            return
        if raw.get("version") != 1:
            logger.warning("BM25 状态版本不兼容，将使用空统计")
            return
        self._vocab = {str(k): int(v) for k, v in raw.get("vocab", {}).items()}
        self._doc_freq = Counter({str(k): int(v) for k, v in raw.get("doc_freq", {}).items()})
        self._total_docs = int(raw.get("total_docs", 0))
        self._sum_token_len = int(raw.get("sum_token_len", 0))
        if self._vocab:
            self._vocab_counter = max(self._vocab.values()) + 1
        else:
            self._vocab_counter = 0
        self._recompute_avg_len()

    def _persist_unlocked(self) -> None:
        """将 BM25 统计写入磁盘（原子写入：先写临时文件再替换）。

        调用方必须持有 self._lock。
        """
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "total_docs": self._total_docs,
            "sum_token_len": self._sum_token_len,
            "vocab": self._vocab,
            "doc_freq": dict(self._doc_freq),
        }
        tmp = self._state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._state_path)
        logger.debug("BM25 状态已持久化: N=%d, vocab=%d", self._total_docs, len(self._vocab))

    def _persist(self) -> None:
        """线程安全的持久化入口。"""
        with self._lock:
            self._persist_unlocked()

    # ── 增量统计更新 ──────────────────────────────────────────────

    def increment_add_documents(self, texts: list[str]) -> None:
        """入库时增量增加 BM25 统计。

        每个 text 视为一篇独立文档（与当前叶子 chunk 写入粒度一致），
        更新 total_docs、sum_token_len、vocab、doc_freq。
        词表索引只增不减，避免与历史 Milvus 稀疏向量维度冲突。

        Args:
            texts: 叶子 chunk 文本列表。
        """
        if not texts:
            return
        with self._lock:
            for text in texts:
                tokens = self.tokenize(text)
                doc_len = len(tokens)
                self._sum_token_len += doc_len
                self._total_docs += 1
                # 用 set 去重：BM25 的 df 统计每个词在多少个文档中出现
                for token in set(tokens):
                    if token not in self._vocab:
                        self._vocab[token] = self._vocab_counter
                        self._vocab_counter += 1
                    self._doc_freq[token] += 1
            self._recompute_avg_len()
            self._persist_unlocked()
            logger.debug(
                "BM25 增量增加: +%d docs, N=%d, avg_len=%.1f",
                len(texts), self._total_docs, self._avg_doc_len,
            )

    def increment_remove_documents(self, texts: list[str]) -> None:
        """删除/覆盖前增量扣减 BM25 统计。

        从语料统计中对称移除文档集合。df 减到 0 时从 Counter 中删除
        （但词表索引保留，保证与 Milvus 旧向量维度兼容）。

        Args:
            texts: 待移除的叶子 chunk 文本列表。
        """
        if not texts:
            return
        with self._lock:
            for text in texts:
                tokens = self.tokenize(text)
                doc_len = len(tokens)
                self._sum_token_len = max(0, self._sum_token_len - doc_len)
                self._total_docs = max(0, self._total_docs - 1)
                for token in set(tokens):
                    if token not in self._doc_freq:
                        continue
                    self._doc_freq[token] -= 1
                    if self._doc_freq[token] <= 0:
                        del self._doc_freq[token]
            self._recompute_avg_len()
            self._persist_unlocked()
            logger.debug(
                "BM25 增量扣减: -%d docs, N=%d, avg_len=%.1f",
                len(texts), self._total_docs, self._avg_doc_len,
            )

    # ── 密集向量 ──────────────────────────────────────────────────

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """生成文本的稠密向量（BGE-M3, 1024 维, 归一化）。

        Args:
            texts: 文本列表。

        Returns:
            浮点向量列表，每个向量为 1024 维。
        """
        if not texts:
            return []
        try:
            return self._embedder.embed_documents(texts)
        except Exception as e:
            logger.error("稠密嵌入失败: %s", e)
            raise Exception(f"本地嵌入模型调用失败: {str(e)}") from e

    # ── 分词 ──────────────────────────────────────────────────────

    def tokenize(self, text: str) -> list[str]:
        """中英混合规则分词。

        策略:
            - 每个中文字符（Unicode 范围 0x4e00-0x9fff）视为一个独立 token
            - 连续英文字母组成一个 token（如 "Theorem" → ["theorem"]）
            - 标点、数字、空白符跳过

        Args:
            text: 原始文本。

        Returns:
            小写化后的 token 列表。
        """
        text = text.lower()
        tokens = []
        chinese_pattern = re.compile(r"[一-鿿]")
        english_pattern = re.compile(r"[a-zA-Z]+")
        i = 0
        while i < len(text):
            char = text[i]
            if chinese_pattern.match(char):
                tokens.append(char)
                i += 1
            elif english_pattern.match(char):
                match = english_pattern.match(text[i:])
                if match:
                    tokens.append(match.group())
                    i += len(match.group())
            else:
                i += 1
        return tokens

    # ── BM25 稀疏向量 ─────────────────────────────────────────────

    def _sparse_vector_for_text_unlocked(self, text: str) -> tuple[dict, bool]:
        """为单条文本生成 BM25 稀疏向量（调用方必须持有锁）。

        BM25 公式:
            score(token, doc) = IDF(token) * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_doc_len))

        其中:
            IDF(token) = log((N - df + 0.5) / (df + 0.5) + 1)  [Robertson-Sparck Jones]

        Args:
            text: 查询文本或文档文本。

        Returns:
            (sparse_vector, vocab_changed): sparse_vector 为 {维度下标: BM25分数}，
            vocab_changed 表示是否新增了词表条目（需要持久化）。
        """
        tokens = self.tokenize(text)
        doc_len = len(tokens)
        tf = Counter(tokens)
        sparse_vector: dict[int, float] = {}
        vocab_changed = False
        n = max(self._total_docs, 0)
        avg = max(self._avg_doc_len, 1.0)

        for token, freq in tf.items():
            # 新词：动态扩展词表（检索时也可能遇到未见词）
            if token not in self._vocab:
                self._vocab[token] = self._vocab_counter
                self._vocab_counter += 1
                vocab_changed = True

            idx = self._vocab[token]
            df = self._doc_freq.get(token, 0)

            # IDF: Robertson-Sparck Jones 平滑版本
            if df == 0:
                idf = math.log((n + 1) / 1)
            else:
                idf = math.log((n - df + 0.5) / (df + 0.5) + 1)

            # BM25 得分
            numerator = freq * (self.k1 + 1)
            denominator = freq + self.k1 * (1 - self.b + self.b * doc_len / avg)
            score = idf * numerator / denominator
            if score > 0:
                sparse_vector[idx] = float(score)

        return sparse_vector, vocab_changed

    def get_sparse_embedding(self, text: str) -> dict:
        """为查询文本生成 BM25 稀疏向量。

        Args:
            text: 查询文本。

        Returns:
            {维度下标: BM25分数} 字典，可直接作为 Milvus SPARSE_FLOAT_VECTOR 使用。
        """
        with self._lock:
            sparse_vector, vocab_changed = self._sparse_vector_for_text_unlocked(text)
            if vocab_changed:
                self._persist_unlocked()
        return sparse_vector

    def get_sparse_embeddings(self, texts: list[str]) -> list[dict]:
        """批量生成 BM25 稀疏向量（写入用）。

        Args:
            texts: 文本列表。

        Returns:
            稀疏向量字典列表。
        """
        if not texts:
            return []
        with self._lock:
            out: list[dict] = []
            any_new_vocab = False
            for text in texts:
                sparse_vector, vocab_changed = self._sparse_vector_for_text_unlocked(text)
                out.append(sparse_vector)
                any_new_vocab = any_new_vocab or vocab_changed
            if any_new_vocab:
                self._persist_unlocked()
        return out

    def get_all_embeddings(self, texts: list[str]) -> tuple[list[list[float]], list[dict]]:
        """同时生成稠密和稀疏向量（写入用，减少两次遍历）。

        Args:
            texts: 文本列表。

        Returns:
            (dense_embeddings, sparse_embeddings): 稠密向量列表和稀疏向量字典列表。
        """
        dense_embeddings = self.get_embeddings(texts)
        sparse_embeddings = self.get_sparse_embeddings(texts)
        return dense_embeddings, sparse_embeddings


# 全进程唯一实例：写入（api）与检索（rag_utils）共用同一份 BM25 持久化状态
embedding_service = EmbeddingService()
