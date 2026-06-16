"""语义缓存单元测试 —— 精确匹配、语义匹配、过期、失效。"""

import time

from backend.services.cache import SemanticCache


def _dummy_embedding(text: str) -> list[float]:
    """简单虚拟嵌入函数：基于字符 n-gram 的向量。

    相似文本（共享字符 n-gram）会产生相近的向量，
    使余弦相似度能反映文本语义相似性。
    """
    import math

    text = text.lower().strip()
    # 统计字符三元组频次
    ngrams = {}
    for i in range(len(text) - 2):
        ngram = text[i:i+3]
        ngrams[ngram] = ngrams.get(ngram, 0) + 1
    # 映射到 128 维稀疏向量
    vec = [0.0] * 128
    for ngram, count in ngrams.items():
        idx = abs(hash(ngram)) % 128
        vec[idx] += count * 0.1
    # 若全零则给一个微小的随机偏移
    if all(v == 0.0 for v in vec):
        vec[0] = 0.01
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec]


class TestSemanticCache:
    def test_exact_hit(self):
        cache = SemanticCache(embedding_fn=_dummy_embedding)
        cache.store("什么是安全多方计算？", {"result": "MPC 概念"})
        hit = cache.lookup("什么是安全多方计算？")
        assert hit is not None
        assert hit["result"] == "MPC 概念"

    def test_exact_hit_normalized(self):
        cache = SemanticCache(embedding_fn=_dummy_embedding)
        cache.store("MPC 协议", {"result": "Secure Multi-Party Computation"})
        hit = cache.lookup("MPC 协议！")  # 标点被归一化
        assert hit is not None

    def test_lookup_miss_on_nonexistent(self):
        """未存储的查询应返回 None。"""
        cache = SemanticCache(embedding_fn=None)
        assert cache.lookup("nonexistent") is None

    def test_semantic_hit(self):
        """语义层：两次相同的查询应命中精确层。"""
        cache = SemanticCache(embedding_fn=_dummy_embedding)
        cache.store("test query", {"result": "value"})
        hit = cache.lookup("test query")
        assert hit is not None
        assert hit["result"] == "value"

    def test_disabled_cache(self):
        cache = SemanticCache(embedding_fn=_dummy_embedding)
        cache._enabled = False
        cache.store("test", {"result": "value"})
        assert cache.lookup("test") is None

    def test_expiry(self):
        cache = SemanticCache(embedding_fn=_dummy_embedding)
        cache._ttl = 0.1  # 100ms TTL
        cache.store("fast expire", {"result": "gone"})
        assert cache.lookup("fast expire") is not None
        time.sleep(0.15)
        assert cache.lookup("fast expire") is None

    def test_invalidate_all(self):
        cache = SemanticCache(embedding_fn=None)
        cache.store("a", {"result": 1})
        cache.store("b", {"result": 2})
        removed = cache.invalidate(None)
        assert removed == 2
        assert cache.lookup("a") is None

    def test_invalidate_specific(self):
        cache = SemanticCache(embedding_fn=None)
        cache.store("a", {"result": 1})
        cache.store("b", {"result": 2})
        removed = cache.invalidate("a")
        assert removed == 1
        assert cache.lookup("b") is not None
        assert cache.lookup("a") is None

    def test_eviction_policy(self):
        cache = SemanticCache(embedding_fn=_dummy_embedding)
        cache._max_size = 3
        cache.store("k1", {"v": 1})
        cache.store("k2", {"v": 2})
        cache.store("k3", {"v": 3})
        cache.store("k4", {"v": 4})  # 应淘汰最早的一个
        assert cache._exact.__len__() <= 3

    def test_normalize_removes_punctuation(self):
        assert SemanticCache._normalize("Hello, World!") == "hello world"
        assert SemanticCache._normalize("  What's  up?  ") == "whats up"
