"""
Milvus 写入器 —— 文档向量化并批量写入 Milvus 向量库。

本模块提供 MilvusWriter 类，负责:
  - 将文档分块批量转换为密集向量 + 稀疏向量
  - 将向量连同元数据批量写入 Milvus 集合
  - 支持进度回调，供前端实时展示写入进度

工作流程:
  1. 接收文档分块列表（dict 列表，每个 dict 含 text 和各项元数据）
  2. 调用 EmbeddingService 对所有文本生成密集向量和稀疏向量
  3. 按 batch_size 分批组装 insert_data，写入 Milvus
  4. 每批写入后回调 progress_callback(processed, total)

依赖:
  - EmbeddingService (backend.rag.embedding): 负责同时生成密集和稀疏嵌入
  - MilvusManager (backend.vectordb.milvus_client): 负责 Milvus 连接和集合写入

日志通过 backend.core.logging_config.get_logger 获取标准化 logger。
"""

from backend.core.dependencies import get_embedding_service, get_milvus_manager
from backend.core.logging_config import get_logger
from backend.rag.embedding import EmbeddingService

logger = get_logger(__name__)


class MilvusWriter:
    """文档向量化并写入 Milvus —— 支持密集+稀疏混合向量。

    典型用法:
        writer = MilvusWriter()                      # 使用默认的 embedding_service 和 milvus_manager
        writer.write_documents(
            documents=chunk_list,
            batch_size=50,
            progress_callback=lambda processed, total: print(f"{processed}/{total}")
        )

    可通过构造函数注入自定义的 EmbeddingService 或 MilvusManager 实例，
    便于测试和不同环境下的灵活配置。
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        milvus_manager = None,
    ):
        """初始化 MilvusWriter。

        Args:
            embedding_service: EmbeddingService 实例。
                               默认使用懒加载 get_embedding_service() 获取。
            milvus_manager: MilvusManager 实例。
                            默认使用懒加载 get_milvus_manager() 获取。
        """
        self.embedding_service = embedding_service or get_embedding_service()
        self.milvus_manager = milvus_manager or get_milvus_manager()
        logger.info("MilvusWriter 已初始化")

    def write_documents(
        self,
        documents: list[dict],
        batch_size: int = 50,
        progress_callback=None,
    ):
        """将文档分块列表批量向量化并写入 Milvus。

        处理流程:
          1. 确保 Milvus 集合已初始化（不存在则创建 Schema + 索引）。
          2. 收集所有文档的文本，调用 EmbeddingService.increment_add_documents
             更新 BM25 的增量统计信息（保持稀疏向量质量）。
          3. 按 batch_size 分批:
             a. 调用 get_all_embeddings() 批量生成密集和稀疏向量
             b. 将向量与元数据打包为 insert_data
             c. 调用 MilvusManager.insert() 写入
             d. 回调 progress_callback 汇报进度

        Args:
            documents: 文档分块列表。每个 dict 需包含以下字段:
                       - text (str):                 分块文本，必填。
                       - filename (str):             来源文件名，必填。
                       - file_type (str):            文件类型 (pdf/txt/md 等)，必填。
                       - file_path (str):            文件完整路径，可选，默认 ""。
                       - page_number (int):          页码 (非PDF为0)，可选，默认 0。
                       - chunk_idx (int):            分块在文件内的序号，可选，默认 0。
                       - chunk_id (str):             全局唯一分块ID，可选，默认 ""。
                       - parent_chunk_id (str):      直属父分块ID，可选，默认 ""。
                       - root_chunk_id (str):        根分块ID，可选，默认 ""。
                       - chunk_level (int):          分块层级，可选，默认 0。
                       - parent_idx (int):           在父块中的序号，可选，默认 0。
                       - child_idx (int):            全局子块序号，可选，默认 0。
                       - num_children (int):         父块下子块总数，可选，默认 0。
                       - has_theorem_in_parent (bool): 父块是否含定理，可选，默认 False。
                       - has_proof_in_parent (bool):   父块是否含证明，可选，默认 False。
            batch_size: 每批写入的文档数量。默认 50。
                        值越大单次吞吐越高，但内存占用也越大。
            progress_callback: 进度回调函数，签名为 callback(processed: int, total: int)。
                               每批次写入后调用。用于前端展示 "向量化入库 xx%"。
        """
        if not documents:
            logger.warning("write_documents: 文档列表为空，跳过")
            return

        total = len(documents)
        logger.info(f"开始写入 {total} 条文档到 Milvus (batch_size={batch_size})")

        # ── 步骤 1: 确保集合已初始化 ──
        self.milvus_manager.init_collection()

        # ── 步骤 2: 增量更新 BM25 统计 ──
        # 收集所有文本并告知 EmbeddingService，使其维护全局词频统计，
        # 保证后续稀疏编码的准确性（特别是增量导入场景）。
        all_texts = [doc["text"] for doc in documents]
        self.embedding_service.increment_add_documents(all_texts)
        logger.debug(f"已向 EmbeddingService 注册 {len(all_texts)} 条文本用于稀疏统计")

        # ── 步骤 3: 分批向量化并写入 ──
        for i in range(0, total, batch_size):
            batch = documents[i : i + batch_size]
            texts = [doc["text"] for doc in batch]

            # 调用 EmbeddingService 同时生成密集向量和稀疏向量
            # dense_embeddings: list[list[float]] — 每个元素为 1024 维浮点向量
            # sparse_embeddings: list[dict] — 每个元素为 {index: value} 稀疏表示
            dense_embeddings, sparse_embeddings = self.embedding_service.get_all_embeddings(texts)

            # ── 组装插入数据 ──
            # 将向量与元数据逐一打包，字段顺序对 Milvus 无要求
            insert_data = [
                {
                    # 向量字段（核心检索字段）
                    "dense_embedding": dense_emb,
                    "sparse_embedding": sparse_emb,
                    # 文本与来源信息
                    "text": doc["text"],
                    "filename": doc["filename"],
                    "file_type": doc["file_type"],
                    "file_path": doc.get("file_path", ""),
                    "page_number": doc.get("page_number", 0),
                    # 分块顺序
                    "chunk_idx": doc.get("chunk_idx", 0),
                    # Auto-merging 层级字段
                    "chunk_id": doc.get("chunk_id", ""),
                    "parent_chunk_id": doc.get("parent_chunk_id", ""),
                    "root_chunk_id": doc.get("root_chunk_id", ""),
                    "chunk_level": doc.get("chunk_level", 0),
                    # 父子分块索引元数据（用于检索后处理和上下文扩展）
                    "parent_idx": doc.get("parent_idx", 0),
                    "child_idx": doc.get("child_idx", 0),
                    "num_children": doc.get("num_children", 0),
                    # 定理/证明标记（用于学术内容过滤和增强检索）
                    "has_theorem_in_parent": doc.get("has_theorem_in_parent", False),
                    "has_proof_in_parent": doc.get("has_proof_in_parent", False),
                }
                for doc, dense_emb, sparse_emb in zip(
                    batch, dense_embeddings, sparse_embeddings
                )
            ]

            # ── 写入 Milvus ──
            self.milvus_manager.insert(insert_data)

            # ── 进度回调 ──
            # 调用方可通过此回调更新前端进度条或记录日志
            if progress_callback:
                processed = min(i + batch_size, total)
                progress_callback(processed, total)

            logger.debug(
                f"批次写入完成: {min(i + batch_size, total)}/{total} "
                f"({len(batch)} 条本批)"
            )

        logger.info(f"全部文档写入完成: {total} 条已入库")
