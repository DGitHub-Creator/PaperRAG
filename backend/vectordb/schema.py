"""Milvus 集合与索引定义；连接生命周期由 milvus_client 管理。"""

from pymilvus import DataType, MilvusClient
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


def ensure_collection(client: MilvusClient, collection_name: str, dense_dim: int) -> None:
    if client.has_collection(collection_name):
        logger.info(f"集合 '{collection_name}' 已存在，跳过创建")
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

    # 创建集合（包含 Schema + 索引）
    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )
    logger.info(f"集合 '{collection_name}' 创建成功 (dense_dim={dense_dim})")

