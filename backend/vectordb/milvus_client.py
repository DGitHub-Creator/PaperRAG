"""Milvus 连接生命周期、读写与检索；集合定义在 schema.py，非幂等插入不自动重试。"""

import threading
import json
from collections.abc import Callable
from typing import TypeVar

from pymilvus import AnnSearchRequest, MilvusClient, RRFRanker

from backend.core.config import (
    DENSE_EMBEDDING_DIM,
    MILVUS_COLLECTION,
    MILVUS_CONNECT_TIMEOUT,
    MILVUS_OPERATION_TIMEOUT,
    MILVUS_HOST,
    MILVUS_PORT,
)
from backend.core.logging_config import get_logger

from backend.vectordb.schema import ensure_collection

logger = get_logger(__name__)

# Milvus 单次 query 的 limit 上限（超出会报 invalid max query result window 错误）
QUERY_MAX_LIMIT = 16384

# 泛型类型变量，用于 _run_with_reconnect 的返回类型标注
T = TypeVar("T")


class MilvusManager:
    """Milvus 连接和集合管理 —— 支持密集+稀疏混合检索。

    特性:
      - 懒加载连接: 首次访问时才建立 Milvus 连接，避免应用启动时阻塞。
      - 线程安全: 使用 RLock 保护 client 的创建和重置。
      - 自动重连: 检测到 "closed channel" 错误时自动重建连接并重试操作。
      - 动态字段: 通过 enable_dynamic_field=True 允许插入 Schema 外字段
        (parent_idx, child_idx, num_children, has_theorem_in_parent, has_proof_in_parent)。
    """

    def __init__(self):
        """初始化 MilvusManager —— 仅保存连接参数，不立即建立连接。"""
        self.host = MILVUS_HOST
        self.port = MILVUS_PORT
        self.collection_name = MILVUS_COLLECTION
        # 构建 gRPC URI（如 http://127.0.0.1:19530）
        self.uri = f"http://{self.host}:{self.port}"
        # MilvusClient 实例引用（懒创建）
        self.client: MilvusClient | None = None
        # 线程锁：保护 client 的创建与重置操作
        self._client_lock = threading.RLock()
        logger.info(
            f"MilvusManager 已初始化: uri={self.uri}, collection={self.collection_name}"
        )

    def _get_client(self, timeout: float | None = None) -> MilvusClient:
        """获取 MilvusClient 实例（懒加载，线程安全）。

        首次调用时创建 MilvusClient，后续调用直接返回已有实例。
        使用 RLock 确保多线程环境下只创建一个实例。

        连接建立（gRPC channel ready）受 ``timeout`` 约束：未显式指定时
        使用 ``MILVUS_CONNECT_TIMEOUT``（默认 10s）。不设上限时 gRPC 会
        无限重连，Milvus 宕机期间会泄漏永久阻塞的线程。"""
        with self._client_lock:
            if self.client is None:
                self.client = MilvusClient(
                    uri=self.uri,
                    timeout=timeout if timeout is not None else MILVUS_CONNECT_TIMEOUT,
                )
                logger.info(f"Milvus 客户端已连接: {self.uri}")
            return self.client

    @staticmethod
    def _is_closed_channel_error(exc: Exception) -> bool:
        """判断异常是否为 gRPC "closed channel" 错误。

        pymilvus 在底层 gRPC 连接断开后会抛出 ValueError，
        消息中包含 "closed channel" 字样。"""
        return isinstance(exc, ValueError) and "closed channel" in str(exc).lower()

    @staticmethod
    def _close_client(client: MilvusClient | None) -> None:
        """安全关闭 MilvusClient 连接。"""
        if client is None:
            return
        close = getattr(client, "close", None)
        if not callable(close):
            return
        try:
            close()
            logger.debug("Milvus 客户端连接已关闭")
        except Exception:
            logger.warning("可选操作失败: _close_client", exc_info=True)

    def _reset_client(self, failed_client: MilvusClient | None = None) -> None:
        """重置内部 client 引用（通常在检测到断连后调用）。

        为保证线程安全，仅在 failed_client 与当前 self.client 为同一实例时才重置。
        这样可以避免：线程 A 检测到错误时，线程 B 已经创建了新 client 的情况。"""
        with self._client_lock:
            if self.client is None:
                return
            # 仅当当前实例与传入的失败实例相同（或无指定）时才重置
            if failed_client is not None and self.client is not failed_client:
                return
            client_to_close = self.client
            self.client = None

        # 在锁外关闭连接，避免阻塞其他线程
        self._close_client(client_to_close)
        logger.info("Milvus 客户端引用已重置，下次操作将自动重连")

    def _run_with_reconnect(self, operation: Callable[[MilvusClient], T], *, retry: bool = True) -> T:
        """执行 Milvus 操作，遇到 "closed channel" 错误时自动重连并重试。

        重试逻辑:
          1. 获取当前 client，执行操作。
          2. 若抛出 "closed channel" 错误 → 重置 client → 重新获取新 client → 重试一次。
          3. 若非 "closed channel" 错误，直接向上抛出。"""
        client = self._get_client()
        try:
            return operation(client)
        except Exception as exc:
            if not self._is_closed_channel_error(exc):
                raise

            logger.warning("检测到 Milvus closed channel 错误，正在重连并重试...")
            self._reset_client(client)
            if not retry:
                raise
            return operation(self._get_client())

    # ─────────────────────────────────────────────────────────────────
    # 集合管理
    # ─────────────────────────────────────────────────────────────────

    def init_collection(self, dense_dim: int | None = None):
        """按现有索引定义幂等创建集合。"""
        dimension = DENSE_EMBEDDING_DIM if dense_dim is None else dense_dim
        self._run_with_reconnect(lambda client: ensure_collection(client, self.collection_name, dimension))

    def has_collection(self) -> bool:
        """检查集合是否已存在于 Milvus 中。

        Returns:
            True 表示集合存在。
        """
        return self._run_with_reconnect(
            lambda client: client.has_collection(self.collection_name, timeout=MILVUS_OPERATION_TIMEOUT)
        )

    def drop_collection(self):
        """删除整个集合（用于重建 Schema 或清空数据）。

        谨慎使用：此操作不可逆，会删除集合中的所有向量数据。
        """
        logger.warning(f"正在删除集合 '{self.collection_name}'...")

        def _drop(client: MilvusClient) -> None:
            if client.has_collection(self.collection_name, timeout=MILVUS_OPERATION_TIMEOUT):
                client.drop_collection(self.collection_name, timeout=MILVUS_OPERATION_TIMEOUT)
                logger.info(f"集合 '{self.collection_name}' 已删除")
            else:
                logger.info(f"集合 '{self.collection_name}' 不存在，无需删除")

        self._run_with_reconnect(_drop)

    # ─────────────────────────────────────────────────────────────────
    # 数据写入与删除
    # ─────────────────────────────────────────────────────────────────

    def insert(self, data: list[dict]):
        """将数据批量插入 Milvus 集合。"""
        logger.debug(f"插入 {len(data)} 条数据到集合 '{self.collection_name}'")
        return self._run_with_reconnect(
            lambda client: client.insert(self.collection_name, data, timeout=MILVUS_OPERATION_TIMEOUT)
        , retry=False)

    def delete(self, filter_expr: str):
        """按条件删除集合中的数据。"""
        logger.info(f"删除数据: filter='{filter_expr}'")
        return self._run_with_reconnect(
            lambda client: client.delete(
                collection_name=self.collection_name,
                filter=filter_expr,
                timeout=MILVUS_OPERATION_TIMEOUT,
            )
        )

    # ─────────────────────────────────────────────────────────────────
    # 通用查询
    # ─────────────────────────────────────────────────────────────────

    def query(
        self,
        filter_expr: str = "",
        output_fields: list[str] | None = None,
        limit: int = 10000,
        offset: int = 0,
    ) -> list[dict]:
        """通用标量查询 —— 按过滤条件获取指定字段。

        限制: 单次查询的 limit 不能超过 QUERY_MAX_LIMIT (16384)，
              这是 Milvus 服务端的硬限制（max query result window）。"""
        return self._run_with_reconnect(
            lambda client: client.query(
                collection_name=self.collection_name,
                filter=filter_expr,
                output_fields=output_fields or ["filename", "file_type"],
                limit=min(limit, QUERY_MAX_LIMIT),
                offset=offset,
                timeout=MILVUS_OPERATION_TIMEOUT,
            )
        )

    def query_all(self, filter_expr: str = "", output_fields: list[str] | None = None) -> list[dict]:
        """使用服务端游标，避免 offset + limit 超过 Milvus 的结果窗口。"""
        def collect(client):
            iterator = client.query_iterator(
                collection_name=self.collection_name, filter=filter_expr,
                output_fields=output_fields or ["filename", "file_type"], batch_size=1000,
                timeout=MILVUS_OPERATION_TIMEOUT,
            )
            rows = []
            try:
                while batch := iterator.next():
                    rows.extend(batch)
                return rows
            finally:
                iterator.close()
        return self._run_with_reconnect(collect)

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict]:
        """根据 chunk_id 批量查询分块（用于 Auto-merging 拉取父块）。

        Auto-merging 策略: 当同一父块下召回的子块数超过阈值时，
        用此方法拉取父块文本，替代多个子块以扩大上下文窗口。"""
        # 过滤空字符串
        ids = [item for item in chunk_ids if item]
        if not ids:
            return []

        # 构建 Milvus 过滤表达式: chunk_id in ["id1", "id2", ...]
        filter_expr = f"chunk_id in {json.dumps(ids, ensure_ascii=False)}"

        logger.debug(f"get_chunks_by_ids: 查询 {len(ids)} 个 chunk_id")
        return self.query(
            filter_expr=filter_expr,
            output_fields=[
                "text",
                "filename",
                "file_type",
                "page_number",
                "chunk_id",
                "parent_chunk_id",
                "root_chunk_id",
                "chunk_level",
                "chunk_idx",
            ],
            limit=len(ids),
        )

    # ─────────────────────────────────────────────────────────────────
    # 向量检索
    # ─────────────────────────────────────────────────────────────────

    # 混合检索 / 密集检索共用的输出字段列表
    _RETRIEVAL_OUTPUT_FIELDS: list[str] = [
        "text",
        "filename",
        "file_type",
        "page_number",
        "chunk_id",
        "parent_chunk_id",
        "root_chunk_id",
        "chunk_level",
        "chunk_idx",
        # 以下为动态字段（通过 enable_dynamic_field 存储）:
        "parent_idx",            # 当前分块在父块中的序号
        "child_idx",             # 当前分块在全局子块序列中的序号
        "num_children",          # 该父块下子块的总数
        "has_theorem_in_parent", # 父块中是否包含定理内容
        "has_proof_in_parent",   # 父块中是否包含证明内容
    ]

    def hybrid_retrieve(
        self,
        dense_embedding: list[float],
        sparse_embedding: dict,
        top_k: int = 5,
        rrf_k: int = 60,
        filter_expr: str = "",
    ) -> list[dict]:
        """混合检索 —— 使用 RRF (Reciprocal Rank Fusion) 融合密集和稀疏向量结果。

        流程:
          1. Dense AnnSearchRequest: 在 dense_embedding 字段上进行 ANN 搜索 → limit=top_k*2 条
          2. Sparse AnnSearchRequest: 在 sparse_embedding 字段上进行稀疏搜索 → limit=top_k*2 条
          3. RRFRanker(k=rrf_k): 对两路结果进行 RRF 融合排序
          4. 返回最终的 top_k 条结果

        这是推荐的检索方式，兼具语义匹配（密集向量）和关键词匹配（稀疏向量）的优势。"""
        logger.debug(
            f"hybrid_retrieve: top_k={top_k}, rrf_k={rrf_k}, filter='{filter_expr}'"
        )

        # ── 密集向量搜索请求 ──
        # limit=top_k*2: 多取一些候选，留给 RRF 融合时有足够的样本
        dense_search = AnnSearchRequest(
            data=[dense_embedding],
            anns_field="dense_embedding",
            param={
                "metric_type": "IP",       # 内积距离（cosine 归一化后等价于余弦相似度）
                "params": {"ef": 64},      # HNSW 搜索宽度
            },
            limit=top_k * 2,
            expr=filter_expr,
        )

        # ── 稀疏向量搜索请求 ──
        # drop_ratio_search=0.2: 搜索时丢弃 20% 低频词以加速
        sparse_search = AnnSearchRequest(
            data=[sparse_embedding],
            anns_field="sparse_embedding",
            param={
                "metric_type": "IP",
                "params": {"drop_ratio_search": 0.2},
            },
            limit=top_k * 2,
            expr=filter_expr,
        )

        # ── RRF 融合排序 ──
        reranker = RRFRanker(k=rrf_k)

        results = self._run_with_reconnect(
            lambda client: client.hybrid_search(
                collection_name=self.collection_name,
                reqs=[dense_search, sparse_search],
                ranker=reranker,
                limit=top_k,
                output_fields=self._RETRIEVAL_OUTPUT_FIELDS,
                timeout=MILVUS_OPERATION_TIMEOUT,
            )
        )

        # ── 格式化返回结果 ──
        formatted_results = _format_hits(results)

        logger.info(
            f"hybrid_retrieve 完成: 返回 {len(formatted_results)} 条结果 (请求 top_k={top_k})"
        )
        return formatted_results

    def dense_retrieve(
        self,
        dense_embedding: list[float],
        top_k: int = 5,
        filter_expr: str = "",
    ) -> list[dict]:
        """仅使用密集向量检索（降级模式）。

        当稀疏向量不可用时（如 BM25 模型未加载、稀疏编码失败等），
        退回到纯密集向量检索以保证基本可用性。"""
        logger.debug(
            f"dense_retrieve: top_k={top_k}, filter='{filter_expr}'"
        )

        results = self._run_with_reconnect(
            lambda client: client.search(
                collection_name=self.collection_name,
                data=[dense_embedding],
                anns_field="dense_embedding",
                search_params={
                    "metric_type": "IP",
                    "params": {"ef": 64},
                },
                limit=top_k,
                output_fields=self._RETRIEVAL_OUTPUT_FIELDS,
                filter=filter_expr,
                timeout=MILVUS_OPERATION_TIMEOUT,
            )
        )

        # ── 格式化返回结果 ──
        # 注意: client.search 返回的 hits 结构与 hybrid_search 不同，
        #       实体字段位于 hit["entity"] 而非直接位于 hit 下
        formatted_results = _format_hits(results)

        logger.info(
            f"dense_retrieve 完成: 返回 {len(formatted_results)} 条结果 (请求 top_k={top_k})"
        )
        return formatted_results


def _format_hits(results: list) -> list[dict]:
    defaults = {
        "text": "", "filename": "", "file_type": "", "page_number": 0,
        "chunk_id": "", "parent_chunk_id": "", "root_chunk_id": "", "chunk_level": 0,
        "chunk_idx": 0, "parent_idx": 0, "child_idx": 0, "num_children": 0,
        "has_theorem_in_parent": False, "has_proof_in_parent": False,
    }
    rows = []
    for hits in results:
        for hit in hits:
            entity = hit.get("entity", hit)
            row = {key: entity.get(key, default) for key, default in defaults.items()}
            row.update(id=hit.get("id"), score=hit.get("distance", 0.0))
            rows.append(row)
    return rows
