"""
Milvus 客户端 —— 连接管理、集合初始化与混合检索。

本模块提供 MilvusManager 类，封装:
  - Milvus gRPC 连接的生命周期管理（懒加载 + 断连自动重建）
  - 集合 (Collection) 的 Schema 定义与索引创建
  - 密集向量 + 稀疏向量混合检索（RRF 融合排序）
  - 纯密集向量检索（降级模式，稀疏向量不可用时）
  - 通用查询、分页全量拉取、按 chunk_id 批量查询
  - 数据插入与按条件删除

向量库 Schema 说明:
  - id (INT64, 主键, 自增):         每条向量记录的唯一标识
  - dense_embedding (FLOAT_VECTOR):  密集向量（BGE-M3 1024 维，IP 距离）
  - sparse_embedding (SPARSE_FLOAT_VECTOR): 稀疏向量（BM25 / BGE-M3 稀疏输出）
  - text (VARCHAR 2000):            分块文本内容
  - filename / file_type / file_path: 来源文件元数据
  - page_number / chunk_idx:         定位信息
  - chunk_id / parent_chunk_id / root_chunk_id / chunk_level: Auto-merging 层级字段
  - parent_idx / child_idx / num_children: 父子分块索引元数据（动态字段）
  - has_theorem_in_parent / has_proof_in_parent: 定理/证明标记（动态字段）

检索策略:
  - hybrid_retrieve: Dense + Sparse 双路召回 → RRF 重排序 → 返回 top_k
  - dense_retrieve:  仅 Dense 召回（降级方案）

所有配置值统一从 backend.core.config 导入。
日志通过 backend.core.logging_config.get_logger 获取标准化 logger。
"""

import threading
from typing import Callable, TypeVar

from pymilvus import MilvusClient, DataType, AnnSearchRequest, RRFRanker

from backend.core.config import (
    MILVUS_HOST,
    MILVUS_PORT,
    MILVUS_COLLECTION,
    DENSE_EMBEDDING_DIM,
)
from backend.core.logging_config import get_logger

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

    def _get_client(self) -> MilvusClient:
        """获取 MilvusClient 实例（懒加载，线程安全）。

        首次调用时创建 MilvusClient，后续调用直接返回已有实例。
        使用 RLock 确保多线程环境下只创建一个实例。

        Returns:
            已连接的 MilvusClient 实例。
        """
        with self._client_lock:
            if self.client is None:
                self.client = MilvusClient(uri=self.uri)
                logger.info(f"Milvus 客户端已连接: {self.uri}")
            return self.client

    @staticmethod
    def _is_closed_channel_error(exc: Exception) -> bool:
        """判断异常是否为 gRPC "closed channel" 错误。

        pymilvus 在底层 gRPC 连接断开后会抛出 ValueError，
        消息中包含 "closed channel" 字样。

        Args:
            exc: 捕获到的异常对象。

        Returns:
            True 表示是 closed channel 错误，需要重连。
        """
        return isinstance(exc, ValueError) and "closed channel" in str(exc).lower()

    @staticmethod
    def _close_client(client: MilvusClient | None) -> None:
        """安全关闭 MilvusClient 连接。

        Args:
            client: 需要关闭的 MilvusClient 实例（可为 None）。
        """
        if client is None:
            return
        close = getattr(client, "close", None)
        if not callable(close):
            return
        try:
            close()
            logger.debug("Milvus 客户端连接已关闭")
        except Exception:
            pass

    def _reset_client(self, failed_client: MilvusClient | None = None) -> None:
        """重置内部 client 引用（通常在检测到断连后调用）。

        为保证线程安全，仅在 failed_client 与当前 self.client 为同一实例时才重置。
        这样可以避免：线程 A 检测到错误时，线程 B 已经创建了新 client 的情况。

        Args:
            failed_client: 出错的旧 client 实例。如果为 None，则无条件重置当前 client。
        """
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

    def _run_with_reconnect(self, operation: Callable[[MilvusClient], T]) -> T:
        """执行 Milvus 操作，遇到 "closed channel" 错误时自动重连并重试。

        重试逻辑:
          1. 获取当前 client，执行操作。
          2. 若抛出 "closed channel" 错误 → 重置 client → 重新获取新 client → 重试一次。
          3. 若非 "closed channel" 错误，直接向上抛出。

        Args:
            operation: 接受 MilvusClient 并返回 T 的可调用对象。

        Returns:
            操作执行结果（类型 T）。

        Raises:
            Exception: 非 closed channel 错误，或重试后仍然失败。
        """
        client = self._get_client()
        try:
            return operation(client)
        except Exception as exc:
            if not self._is_closed_channel_error(exc):
                raise

            logger.warning("检测到 Milvus closed channel 错误，正在重连并重试...")
            self._reset_client(client)
            return operation(self._get_client())

    # ─────────────────────────────────────────────────────────────────
    # 集合管理
    # ─────────────────────────────────────────────────────────────────

    def init_collection(self, dense_dim: int | None = None):
        """初始化 Milvus 集合 —— 定义 Schema 并创建索引。

        仅在集合不存在时创建；已存在则跳过。
        集合包含密集向量 (FLOAT_VECTOR) 和稀疏向量 (SPARSE_FLOAT_VECTOR) 两个向量字段，
        以及用于过滤和检索的标量字段。
        启用 enable_dynamic_field 允许动态插入 schema 外的元数据字段。

        索引策略:
          - 密集向量: HNSW + IP (内积)，适合高精度近似最近邻搜索
          - 稀疏向量: SPARSE_INVERTED_INDEX + IP，适合 BM25 稀疏检索

        Args:
            dense_dim: 密集向量维度。默认从配置 DENSE_EMBEDDING_DIM 读取（BAAI/bge-m3 为 1024）。
        """
        if dense_dim is None:
            dense_dim = DENSE_EMBEDDING_DIM

        logger.info(f"初始化 Milvus 集合: {self.collection_name}, dense_dim={dense_dim}")

        def _init(client: MilvusClient) -> None:
            """集合创建的具体实现（作为回调传入 _run_with_reconnect）。"""
            if client.has_collection(self.collection_name):
                logger.info(f"集合 '{self.collection_name}' 已存在，跳过创建")
                return

            # 创建 Schema: auto_id=True 表示主键自动生成, enable_dynamic_field=True 允许动态字段
            schema = client.create_schema(
                auto_id=True, enable_dynamic_field=True
            )

            # ── 主键（自增 INT64） ──
            schema.add_field(
                "id", DataType.INT64, is_primary=True, auto_id=True
            )

            # ── 密集向量（来自 BGE-M3 等 Embedding 模型） ──
            schema.add_field(
                "dense_embedding", DataType.FLOAT_VECTOR, dim=dense_dim
            )

            # ── 稀疏向量（来自 BM25 或 BGE-M3 稀疏编码） ──
            schema.add_field(
                "sparse_embedding", DataType.SPARSE_FLOAT_VECTOR
            )

            # ── 文本和元数据字段（用于返回给 LLM 和前端展示） ──
            schema.add_field("text", DataType.VARCHAR, max_length=2000)
            schema.add_field("filename", DataType.VARCHAR, max_length=255)
            schema.add_field("file_type", DataType.VARCHAR, max_length=50)
            schema.add_field("file_path", DataType.VARCHAR, max_length=1024)
            schema.add_field("page_number", DataType.INT64)
            schema.add_field("chunk_idx", DataType.INT64)

            # ── Auto-merging 层级字段 ──
            # chunk_id:       当前分块的唯一标识（UUID）
            # parent_chunk_id: 直属父分块 ID；空字符串表示顶层
            # root_chunk_id:   根分块 ID（最顶层）
            # chunk_level:     层级深度（0=叶节点, 1=父节点, ...）
            schema.add_field("chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("parent_chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("root_chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("chunk_level", DataType.INT64)
            
            # ── 公式相关字段 ──
            schema.add_field("has_formula", DataType.BOOL, default=False)
            schema.add_field("formula_text", DataType.VARCHAR, max_length=1000, default="")
            schema.add_field("formula_embedding", DataType.FLOAT_VECTOR, dim=dense_dim)

            # 注: parent_idx, child_idx, num_children, has_theorem_in_parent,
            #      has_proof_in_parent 等字段通过 enable_dynamic_field 动态存储，
            #      无需在 Schema 中显式定义，Milvus 自动接受。

            # ── 构建索引参数 ──
            index_params = client.prepare_index_params()

            # 密集向量索引: HNSW (Hierarchical Navigable Small World)
            #   M=16: 每个节点的最大连接数（平衡内存与精度）
            #   efConstruction=256: 构建时搜索宽度（越高索引质量越好，构建越慢）
            index_params.add_index(
                field_name="dense_embedding",
                index_type="HNSW",
                metric_type="IP",
                params={"M": 16, "efConstruction": 256},
            )

            # 稀疏向量索引: SPARSE_INVERTED_INDEX
            #   drop_ratio_build=0.2: 构建索引时丢弃 20% 低频词，减小索引体积
            index_params.add_index(
                field_name="sparse_embedding",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP",
                params={"drop_ratio_build": 0.2},
            )
            
            # 公式向量索引: HNSW + COSINE (公式检索用余弦相似度)
            index_params.add_index(
                field_name="formula_embedding",
                index_type="HNSW",
                metric_type="COSINE",
                params={"M": 16, "efConstruction": 256},
            )

            # 创建集合（包含 Schema + 索引）
            client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index_params,
            )
            logger.info(f"集合 '{self.collection_name}' 创建成功 (dense_dim={dense_dim})")

        self._run_with_reconnect(_init)

    def has_collection(self) -> bool:
        """检查集合是否已存在于 Milvus 中。

        Returns:
            True 表示集合存在。
        """
        return self._run_with_reconnect(
            lambda client: client.has_collection(self.collection_name)
        )

    def drop_collection(self):
        """删除整个集合（用于重建 Schema 或清空数据）。

        谨慎使用：此操作不可逆，会删除集合中的所有向量数据。
        """
        logger.warning(f"正在删除集合 '{self.collection_name}'...")

        def _drop(client: MilvusClient) -> None:
            if client.has_collection(self.collection_name):
                client.drop_collection(self.collection_name)
                logger.info(f"集合 '{self.collection_name}' 已删除")
            else:
                logger.info(f"集合 '{self.collection_name}' 不存在，无需删除")

        self._run_with_reconnect(_drop)

    # ─────────────────────────────────────────────────────────────────
    # 数据写入与删除
    # ─────────────────────────────────────────────────────────────────

    def insert(self, data: list[dict]):
        """将数据批量插入 Milvus 集合。

        Args:
            data: dict 列表，每个 dict 包含所有必需字段和向量。
                  典型字段: dense_embedding, sparse_embedding, text, filename,
                  file_type, file_path, page_number, chunk_idx, chunk_id,
                  parent_chunk_id, root_chunk_id, chunk_level, parent_idx,
                  child_idx, num_children, has_theorem_in_parent, has_proof_in_parent。

        Returns:
            Milvus insert 接口的返回值（包含插入的 ID 列表等信息）。
        """
        logger.debug(f"插入 {len(data)} 条数据到集合 '{self.collection_name}'")
        return self._run_with_reconnect(
            lambda client: client.insert(self.collection_name, data)
        )

    def delete(self, filter_expr: str):
        """按条件删除集合中的数据。

        Args:
            filter_expr: Milvus 过滤表达式，如 'filename == "example.pdf"'。
                         支持 AND / OR / in / not in 等操作符。

        Returns:
            Milvus delete 接口的返回值。
        """
        logger.info(f"删除数据: filter='{filter_expr}'")
        return self._run_with_reconnect(
            lambda client: client.delete(
                collection_name=self.collection_name,
                filter=filter_expr,
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
              这是 Milvus 服务端的硬限制（max query result window）。

        Args:
            filter_expr: 过滤表达式（空字符串表示无过滤）。
            output_fields: 需要返回的字段列表。默认为 ["filename", "file_type"]。
            limit: 单次返回的最大行数（会被截断到 QUERY_MAX_LIMIT）。
            offset: 分页偏移量。

        Returns:
            dict 列表，每个 dict 包含 id 和请求的 output_fields。
        """
        return self._run_with_reconnect(
            lambda client: client.query(
                collection_name=self.collection_name,
                filter=filter_expr,
                output_fields=output_fields or ["filename", "file_type"],
                limit=min(limit, QUERY_MAX_LIMIT),
                offset=offset,
            )
        )

    def query_all(
        self,
        filter_expr: str = "",
        output_fields: list[str] | None = None,
    ) -> list[dict]:
        """分页拉取匹配 filter 的全部行。

        自动循环分页，每批 QUERY_MAX_LIMIT 条，直到返回数量少于
        QUERY_MAX_LIMIT（表示已到末尾）。避免单次请求超出服务端窗口限制。

        Args:
            filter_expr: 过滤表达式（空字符串表示全量拉取）。
            output_fields: 需要返回的字段列表。默认为 ["filename", "file_type"]。

        Returns:
            所有匹配行的完整列表。
        """
        fields = output_fields or ["filename", "file_type"]
        out: list = []
        offset = 0
        logger.debug(f"query_all 开始: filter='{filter_expr}', fields={fields}")

        while True:
            batch = self._run_with_reconnect(
                lambda client: client.query(
                    collection_name=self.collection_name,
                    filter=filter_expr,
                    output_fields=fields,
                    limit=QUERY_MAX_LIMIT,
                    offset=offset,
                )
            )
            if not batch:
                break
            out.extend(batch)
            # 如果返回量小于窗口上限，说明已取完
            if len(batch) < QUERY_MAX_LIMIT:
                break
            offset += len(batch)

        logger.debug(f"query_all 完成: 共获取 {len(out)} 条")
        return out

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict]:
        """根据 chunk_id 批量查询分块（用于 Auto-merging 拉取父块）。

        Auto-merging 策略: 当同一父块下召回的子块数超过阈值时，
        用此方法拉取父块文本，替代多个子块以扩大上下文窗口。

        Args:
            chunk_ids: 需要查询的 chunk_id 列表（来源于 Milvus 检索结果的 parent_chunk_id）。

        Returns:
            匹配的 dict 列表，包含 text, filename, file_type, page_number,
            chunk_id, parent_chunk_id, root_chunk_id, chunk_level, chunk_idx 等字段。
        """
        # 过滤空字符串
        ids = [item for item in chunk_ids if item]
        if not ids:
            return []

        # 构建 Milvus 过滤表达式: chunk_id in ["id1", "id2", ...]
        quoted_ids = ", ".join([f'"{item}"' for item in ids])
        filter_expr = f"chunk_id in [{quoted_ids}]"

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

        这是推荐的检索方式，兼具语义匹配（密集向量）和关键词匹配（稀疏向量）的优势。

        Args:
            dense_embedding:  密集向量（1024 维，来自 BGE-M3 的 dense embedding）。
            sparse_embedding: 稀疏向量（{index: value} 格式，来自 BM25 或 BGE-M3 稀疏编码）。
            top_k:            最终返回的结果数量。默认 5。
            rrf_k:            RRF 算法的平滑参数 k。值越小差异越显著；默认 60。
            filter_expr:      过滤表达式（如按文件名过滤 'filename == "x.pdf"'）。

        Returns:
            格式化后的检索结果列表，每个 dict 包含:
              - id:                     Milvus 内部 ID
              - text:                   分块文本
              - filename / file_type / page_number: 来源文件信息
              - chunk_id / parent_chunk_id / root_chunk_id / chunk_level: 层级信息
              - chunk_idx / parent_idx / child_idx / num_children: 索引信息
              - has_theorem_in_parent / has_proof_in_parent: 定理/证明标记
              - score:                  融合后的 RRF 分数（distance 字段映射）
        """
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
            )
        )

        # ── 格式化返回结果 ──
        formatted_results: list[dict] = []
        for hits in results:
            for hit in hits:
                formatted_results.append({
                    "id": hit.get("id"),
                    "text": hit.get("text", ""),
                    "filename": hit.get("filename", ""),
                    "file_type": hit.get("file_type", ""),
                    "page_number": hit.get("page_number", 0),
                    "chunk_id": hit.get("chunk_id", ""),
                    "parent_chunk_id": hit.get("parent_chunk_id", ""),
                    "root_chunk_id": hit.get("root_chunk_id", ""),
                    "chunk_level": hit.get("chunk_level", 0),
                    "chunk_idx": hit.get("chunk_idx", 0),
                    "parent_idx": hit.get("parent_idx", 0),
                    "child_idx": hit.get("child_idx", 0),
                    "num_children": hit.get("num_children", 0),
                    "has_theorem_in_parent": hit.get("has_theorem_in_parent", False),
                    "has_proof_in_parent": hit.get("has_proof_in_parent", False),
                    "score": hit.get("distance", 0.0),
                })

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
        退回到纯密集向量检索以保证基本可用性。

        Args:
            dense_embedding: 密集向量（1024 维）。
            top_k:           返回结果数量。默认 5。
            filter_expr:     过滤表达式。

        Returns:
            格式化后的检索结果列表，字段同 hybrid_retrieve。
        """
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
            )
        )

        # ── 格式化返回结果 ──
        # 注意: client.search 返回的 hits 结构与 hybrid_search 不同，
        #       实体字段位于 hit["entity"] 而非直接位于 hit 下
        formatted_results: list[dict] = []
        for hits in results:
            for hit in hits:
                entity = hit.get("entity", {})
                formatted_results.append({
                    "id": hit.get("id"),
                    "text": entity.get("text", ""),
                    "filename": entity.get("filename", ""),
                    "file_type": entity.get("file_type", ""),
                    "page_number": entity.get("page_number", 0),
                    "chunk_id": entity.get("chunk_id", ""),
                    "parent_chunk_id": entity.get("parent_chunk_id", ""),
                    "root_chunk_id": entity.get("root_chunk_id", ""),
                    "chunk_level": entity.get("chunk_level", 0),
                    "chunk_idx": entity.get("chunk_idx", 0),
                    "parent_idx": entity.get("parent_idx", 0),
                    "child_idx": entity.get("child_idx", 0),
                    "num_children": entity.get("num_children", 0),
                    "has_theorem_in_parent": entity.get("has_theorem_in_parent", False),
                    "has_proof_in_parent": entity.get("has_proof_in_parent", False),
                    "score": hit.get("distance", 0.0),
                })

        logger.info(
            f"dense_retrieve 完成: 返回 {len(formatted_results)} 条结果 (请求 top_k={top_k})"
        )
        return formatted_results
