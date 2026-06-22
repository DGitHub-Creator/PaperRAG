"""公式 LSH 索引 —— 基于 MinHash 的快速公式相似度搜索。

在论文 RAG 场景中，同一数学公式可能以不同 LaTeX 写法出现
（如 $E=mc^2$ vs. $$E = m c^2$$）。本模块通过 MinHash LSH
将语义等价的公式聚类，为检索阶段提供候选增强。
"""

import hashlib
import threading

from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# ── 默认 MinHash 参数 ─────────────────────────────────────────────────────

_DEFAULT_NUM_HASHES = 128        # 哈希函数数量
_DEFAULT_BANDS = 16              # LSH band 数
_DEFAULT_BAND_SIZE = 8           # 每个 band 的行数
_DEFAULT_NGRAM = 3               # 字符 n-gram 长度


def _hash_int(s: str) -> int:
    """将字符串哈希为一个无符号 64 位整数（使用 SHA-256 前缀）。

    MinHash/LSH 场景不涉及安全，使用 SHA-256 满足 lint 要求。
    """
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:16], 16)


def _minhash_signature(shingles: set[str], num_hashes: int) -> list[int]:
    """计算 shingle 集合的 MinHash 签名向量。"""
    signature = []
    rng_seeds = list(range(num_hashes))
    for seed in rng_seeds:
        min_hash = min(
            (_hash_int(f"{seed}:{s}") for s in shingles),
            default=0,
        )
        signature.append(min_hash)
    return signature


def _shingle(text: str, n: int) -> set[str]:
    """将字符串拆分为字符 n-gram。"""
    return {text[i:i + n] for i in range(len(text) - n + 1)}


class FormulaLSHIndex:
    """公式 MinHash LSH 索引。

    用法:
        >>> index = FormulaLSHIndex()
        >>> index.add("e=mc^2", "formula:001")
        >>> index.add("E = m c^2", "formula:002")
        >>> candidates = index.query("E = mc^2", top_k=5)
    """

    def __init__(
        self,
        num_hashes: int = _DEFAULT_NUM_HASHES,
        bands: int = _DEFAULT_BANDS,
        band_size: int = _DEFAULT_BAND_SIZE,
        ngram: int = _DEFAULT_NGRAM,
    ):
        self._num_hashes = num_hashes
        self._bands = bands
        self._band_size = band_size
        self._ngram = ngram
        self._lock = threading.Lock()

        # band_id → {bucket_key → set[formula_id]}
        self._buckets: list[dict[str, set[str]]] = [{} for _ in range(bands)]

        # formula_id → signature 缓存
        self._signatures: dict[str, list[int]] = {}
        # formula_id → raw text（调试用）
        self._formulas: dict[str, str] = {}

    def _hash_band(self, signature: list[int], band_idx: int) -> str:
        """将一个 band 内的连续哈希值合并为桶键。"""
        start = band_idx * self._band_size
        end = start + self._band_size
        band_values = signature[start:end]
        return hashlib.sha256(
            ",".join(str(v) for v in band_values).encode(),
        ).hexdigest()[:16]

    def add(self, formula: str, formula_id: str) -> None:
        """向索引中添加一个公式（自动标准化）。

        Args:
            formula: 原始或标准化公式文本。
            formula_id: 唯一标识符（如 chunk_id + 公式序号）。
        """
        from backend.rag.formula_normalizer import normalize_formula
        normalized = normalize_formula(formula)
        if not normalized or not normalized.strip():
            return

        shingles = _shingle(normalized, self._ngram)
        if not shingles:
            return

        signature = _minhash_signature(shingles, self._num_hashes)

        with self._lock:
            self._signatures[formula_id] = signature
            self._formulas[formula_id] = normalized

            for band_idx in range(self._bands):
                bucket_key = self._hash_band(signature, band_idx)
                bucket = self._buckets[band_idx]
                if bucket_key not in bucket:
                    bucket[bucket_key] = set()
                bucket[bucket_key].add(formula_id)

    def add_from_list(self, formulas: list[tuple[str, str]]) -> None:
        """批量添加公式。

        Args:
            formulas: (公式文本, 公式 ID) 对列表。
        """
        for text, fid in formulas:
            self.add(text, fid)

    def query(
        self,
        formula: str,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """查询与目标公式最相似的候选公式（自动标准化）。

        Args:
            formula: 原始或已标准化的公式文本。
            top_k: 返回的最大候选数。

        Returns:
            (formula_id, jaccard_similarity) 列表，按相似度降序排列。
        """
        from backend.rag.formula_normalizer import normalize_formula
        normalized = normalize_formula(formula)
        if not normalized:
            return []

        shingles = _shingle(normalized, self._ngram)
        if not shingles:
            return []

        query_sig = _minhash_signature(shingles, self._num_hashes)

        candidates: set[str] = set()
        with self._lock:
            for band_idx in range(self._bands):
                bucket_key = self._hash_band(query_sig, band_idx)
                bucket = self._buckets[band_idx]
                if bucket_key in bucket:
                    candidates.update(bucket[bucket_key])

        if not candidates:
            return []

        # 对候选做 Jaccard 精排
        query_shingles = shingles
        scored: list[tuple[str, float]] = []
        for fid in candidates:
            candidate_text = self._formulas.get(fid, "")
            if not candidate_text:
                continue
            candidate_shingles = _shingle(candidate_text, self._ngram)
            inter = len(query_shingles & candidate_shingles)
            union = len(query_shingles | candidate_shingles)
            jaccard = inter / union if union > 0 else 0.0
            scored.append((fid, jaccard))

        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    def remove(self, formula_id: str) -> None:
        """从索引中移除一个公式。"""
        with self._lock:
            self._signatures.pop(formula_id, None)
            self._formulas.pop(formula_id, None)
            for band_idx in range(self._bands):
                bucket = self._buckets[band_idx]
                keys_to_delete = []
                for bucket_key, ids in bucket.items():
                    ids.discard(formula_id)
                    if not ids:
                        keys_to_delete.append(bucket_key)
                for key in keys_to_delete:
                    del bucket[key]

    def clear(self) -> None:
        """清空索引。"""
        with self._lock:
            self._buckets = [{} for _ in range(self._bands)]
            self._signatures.clear()
            self._formulas.clear()

    def __len__(self) -> int:
        return len(self._signatures)


# ── 全局单例（便于缓存复用）────────────────────────────────────────────────

_formula_lsh_index: FormulaLSHIndex | None = None
_index_lock = threading.Lock()


def get_formula_lsh_index() -> FormulaLSHIndex:
    """获取全局公式 LSH 索引单例。"""
    global _formula_lsh_index
    if _formula_lsh_index is None:
        with _index_lock:
            if _formula_lsh_index is None:
                _formula_lsh_index = FormulaLSHIndex()
    return _formula_lsh_index


def reset_formula_lsh_index() -> None:
    """重置全局 LSH 索引（测试用）。"""
    global _formula_lsh_index
    with _index_lock:
        _formula_lsh_index = None
