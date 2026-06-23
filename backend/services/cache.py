"""
缓存服务模块 —— Redis + 内存两级缓存，含语义相似度缓存层。

本模块提供两层缓存抽象：
  1. RedisCache: 基于 Redis 的 JSON 序列化缓存，用于跨进程共享数据
     （如对话消息、会话列表）。支持按 key 读写删除、按 pattern 批量删除。
  2. SemanticCache: 线程安全的内存级缓存，提供两级匹配：
     - Level 1: 精确匹配（归一化后的查询字符串完全相同）
     - Level 2: 语义相似度匹配（基于嵌入向量的余弦相似度）
     适用于 RAG 场景的"问法不同但语义相同"的缓存命中。

架构：
  RedisCache 可通过 get_semantic() 获取一个 SemanticCache 代理，
  实现 "先精确 -> 再语义" 的缓存查询链。

配置来源：所有参数均从 backend.core.config 导入，不使用 os.getenv。
"""

import json
import re
import threading
import time
from typing import Any

import redis

from backend.core.config import (
    CACHE_MAX_SIZE,
    CACHE_SIM_THRESHOLD,
    CACHE_TTL_SECONDS,
    ENABLE_CACHE,
    REDIS_CACHE_TTL,
    REDIS_KEY_PREFIX,
    REDIS_URL,
)
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class SemanticCache:
    """线程安全的两级缓存：精确匹配 + 语义相似度（余弦相似度）。

    语义层运行在进程内存中，精确层可对接 RedisCache 实现跨进程共享。

    两级匹配策略：
      Level 1 —— 精确匹配：
        对查询字符串做归一化（小写 -> 去标点 -> 空格压缩）后，
        在字典中查找完全相同的键。命中的前提是条目未过期。

      Level 2 —— 语义匹配：
        若提供了 embedding_fn（嵌入函数），则对查询计算向量，
        与缓存中每个条目的向量计算余弦相似度。
        当相似度 >= _sim_threshold 时视为命中。

    线程安全：所有读写操作由 threading.Lock 保护。

    配置参数（从 backend.core.config 导入）：
      - CACHE_MAX_SIZE: 精确匹配层最大条目数（默认 500）
      - CACHE_TTL_SECONDS: 条目生存时间，单位秒（默认 604800，即 7 天）
      - CACHE_SIM_THRESHOLD: 语义匹配余弦相似度阈值（默认 0.92）
      - ENABLE_CACHE: 是否启用缓存（默认 True）
    """

    def __init__(self, embedding_fn=None):
        """初始化语义缓存。

        Args:
            embedding_fn: 可选的嵌入函数，签名为 fn(query: str) -> list[float]。
                          用于语义相似度层。若为 None，则仅使用精确匹配。
        """
        self._exact: dict[str, dict] = {}       # 精确匹配层: norm_query -> entry
        self._semantic: list[dict] = []          # 语义匹配层: list of entry(with emb)
        self._lock = threading.Lock()
        self._embed_fn = embedding_fn
        self._max_size = CACHE_MAX_SIZE
        self._ttl = CACHE_TTL_SECONDS
        self._sim_threshold = CACHE_SIM_THRESHOLD
        self._enabled = ENABLE_CACHE

    @staticmethod
    def _normalize(query: str) -> str:
        """对查询字符串做归一化处理，用于精确匹配的键计算。

        归一化步骤：
          1. 转小写并去除首尾空白。
          2. 移除所有非字母数字和空格的字符（标点符号等）。
          3. 将连续多个空格压缩为单个空格。

        Args:
            query: 原始查询字符串。

        Returns:
            归一化后的查询字符串。
        """
        q = query.lower().strip()
        q = re.sub(r"[^\w\s]", "", q)
        q = re.sub(r"\s+", " ", q)
        return q

    def lookup(self, query: str) -> dict | None:
        """在两级缓存中查找与查询匹配的缓存结果。

        先查精确匹配层，未命中再查语义相似度层。

        Args:
            query: 查询字符串。

        Returns:
            命中的缓存结果字典，未命中返回 None。
        """
        if not self._enabled:
            return None

        norm = self._normalize(query)
        with self._lock:
            # Level 1 —— 精确匹配
            if norm in self._exact:
                entry = self._exact[norm]
                if time.time() - entry["ts"] < self._ttl:
                    entry["hits"] += 1
                    logger.debug("语义缓存精确命中: query='%s'", query[:60])
                    return entry["result"]
                # 已过期，删除
                del self._exact[norm]

            # Level 2 —— 语义相似度匹配
            if self._semantic and self._embed_fn:
                try:
                    import numpy as np

                    q_emb = self._embed_fn(query)
                    best_score, best = -1.0, None
                    for e in self._semantic:
                        if time.time() - e["ts"] > self._ttl:
                            continue
                        # 计算余弦相似度
                        score = float(
                            np.dot(q_emb, e["emb"])
                            / (np.linalg.norm(q_emb) * np.linalg.norm(e["emb"]))
                        )
                        if score > best_score and score >= self._sim_threshold:
                            best_score, best = score, e
                    if best:
                        best["hits"] += 1
                        logger.debug(
                            "语义缓存相似度命中: query='%s', score=%.4f", query[:60], best_score
                        )
                        return best["result"]
                except Exception:
                    logger.debug("语义缓存相似度计算失败", exc_info=True)
        return None

    def store(self, query: str, result: dict) -> None:
        """将查询-结果对存入缓存（同时写入精确层和语义层）。

        自动淘汰策略：
          - 精确层：当条目数超过 max_size 时，删除最旧的条目。
          - 语义层：限制最多保留 min(max_size, 200) 条，超量时从头部移除。

        Args:
            query: 查询字符串。
            result: 查询结果字典。
        """
        if not self._enabled:
            return

        norm = self._normalize(query)
        entry = {"query": query, "result": result, "ts": time.time(), "hits": 1}

        with self._lock:
            # 精确层写入 + 容量限制
            while len(self._exact) >= self._max_size:
                oldest = min(self._exact, key=lambda k: self._exact[k]["ts"])
                del self._exact[oldest]
            self._exact[norm] = dict(entry)

            # 语义层写入（需嵌入函数支持）
            if self._embed_fn:
                try:
                    emb = self._embed_fn(query)
                    self._semantic.append(dict(entry, emb=emb))
                    # 清理过期条目
                    self._semantic = [
                        e
                        for e in self._semantic
                        if time.time() - e["ts"] < self._ttl
                    ]
                    # 容量限制
                    while len(self._semantic) > min(self._max_size, 200):
                        self._semantic.pop(0)
                except Exception:
                    logger.debug("语义缓存存储失败: query='%s'", query[:60], exc_info=True)

    def invalidate(self, query: str | None = None) -> int:
        """使缓存条目失效。

        Args:
            query: 指定查询字符串将使该条目的缓存失效；
                   传入 None 则清空所有缓存。

        Returns:
            移除的缓存条目总数。
        """
        with self._lock:
            if query is None:
                # 清空全部缓存
                n = len(self._exact) + len(self._semantic)
                self._exact.clear()
                self._semantic.clear()
                logger.info("语义缓存已全部清空，移除 %d 条记录", n)
                return n

            # 按查询使指定条目失效
            norm = self._normalize(query)
            removed = 1 if self._exact.pop(norm, None) else 0
            before = len(self._semantic)
            self._semantic = [
                e
                for e in self._semantic
                if self._normalize(e["query"]) != norm
            ]
            removed += before - len(self._semantic)
            logger.debug("语义缓存已按查询失效: query='%s', 移除 %d 条", query[:60], removed)
            return removed


class RedisCache:
    """Redis JSON 缓存封装 + 可选的语义缓存代理 + 熔断降级。

    所有 Redis 操作带有 try-except 保护，Redis 不可用时静默降级。
    连续失败达阈值后自动熔断，避免雪崩。
    """

    CIRCUIT_THRESHOLD = 5
    CIRCUIT_TIMEOUT = 60.0

    def __init__(self):
        self.redis_url = REDIS_URL
        self.key_prefix = REDIS_KEY_PREFIX
        self.default_ttl = REDIS_CACHE_TTL
        self._client: redis.Redis | None = None
        self._semantic: SemanticCache | None = None
        self._failure_count = 0
        self._circuit_open_until = 0.0

    def _is_circuit_open(self) -> bool:
        if self._failure_count >= self.CIRCUIT_THRESHOLD:
            if time.time() < self._circuit_open_until:
                return True
            self._failure_count = 0
        return False

    def _on_failure(self):
        self._failure_count += 1
        if self._failure_count >= self.CIRCUIT_THRESHOLD:
            self._circuit_open_until = time.time() + self.CIRCUIT_TIMEOUT
            logger.warning("Redis 熔断开启，%ds 后重试", self.CIRCUIT_TIMEOUT)

    def _on_success(self):
        self._failure_count = 0

    def _get_client(self) -> redis.Redis:
        """获取 Redis 客户端连接（懒加载模式）。

        Returns:
            redis.Redis 实例，decode_responses=True 自动解码为字符串。
        """
        if self._client is None:
            self._client = redis.Redis.from_url(
                self.redis_url, decode_responses=True
            )
            logger.debug("Redis 客户端已连接: %s", self.redis_url)
        return self._client

    def _key(self, key: str) -> str:
        """为缓存键添加统一前缀。

        Args:
            key: 原始缓存键。

        Returns:
            带前缀的完整 Redis 键，格式为 "{key_prefix}:{key}"。
        """
        return f"{self.key_prefix}:{key}"

    def get_json(self, key: str) -> Any | None:
        if self._is_circuit_open():
            return None
        try:
            value = self._get_client().get(self._key(key))
            self._on_success()
            if not value:
                return None
            return json.loads(value)
        except Exception:
            self._on_failure()
            logger.debug("Redis 读取失败: key=%s", key, exc_info=True)
            return None

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        if self._is_circuit_open():
            return
        try:
            payload = json.dumps(value, ensure_ascii=False)
            self._get_client().setex(
                self._key(key), ttl or self.default_ttl, payload
            )
            self._on_success()
        except Exception:
            self._on_failure()
            logger.debug("Redis 写入失败: key=%s", key, exc_info=True)

    def delete(self, key: str) -> None:
        if self._is_circuit_open():
            return
        try:
            self._get_client().delete(self._key(key))
            self._on_success()
        except Exception:
            self._on_failure()
            logger.debug("Redis 删除失败: key=%s", key, exc_info=True)

    def delete_pattern(self, pattern: str) -> None:
        if self._is_circuit_open():
            return
        try:
            full_pattern = self._key(pattern)
            keys = self._get_client().keys(full_pattern)
            if keys:
                self._get_client().delete(*keys)
            self._on_success()
            logger.debug("Redis 按模式删除: pattern=%s, 删除 %d 个键", pattern, len(keys))
        except Exception:
            self._on_failure()
            logger.debug("Redis 按模式删除失败: pattern=%s", pattern, exc_info=True)

    def get_semantic(self) -> SemanticCache:
        """获取或创建进程内 SemanticCache 实例。

        懒加载模式，首次调用时创建。

        Returns:
            SemanticCache 实例。
        """
        if self._semantic is None:
            self._semantic = SemanticCache()
            logger.debug("语义缓存实例已创建")
        return self._semantic


# 模块级单例 —— 全应用共享同一个 Redis 缓存实例
cache = RedisCache()
