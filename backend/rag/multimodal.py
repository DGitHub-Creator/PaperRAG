"""多模态检索 —— 图表提取、CLIP Embedding、并行图文检索。

模块组成:
  1. FigureExtractor: 从 PDF 页面提取图片（PyMuPDF / pdfplumber）
  2. MultimodalEmbedding: CLIP 文本+图片向量化
  3. MultimodalRetriever: 管理 Milvus 图表集合 + 图文混合检索

所有组件采用懒加载 + 降级策略：依赖不可用时返回空结果，
不影响主文本检索流程。
"""

import io
import os
import threading
import traceback
from typing import Any

from backend.core.logging_config import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════
# FigureExtractor —— 从 PDF 页面提取图片
# ══════════════════════════════════════════════════════════════════════


class FigureExtractor:
    """从 PDF 中提取图片和表格截图。

    使用 PyMuPDF (fitz) 提取页面中的内嵌图片及页面截图。
    """

    def extract_figures(self, file_path: str) -> list[dict]:
        """提取 PDF 中所有页面的图片。

        Args:
            file_path: PDF 文件的绝对路径。

        Returns:
            图片字典列表，每项包含 page_number、image_data (bytes)、width、height。
        """
        figures: list[dict] = []
        try:
            import fitz
        except ImportError:
            logger.warning("PyMuPDF 未安装，跳过图片提取")
            return []

        try:
            doc = fitz.open(file_path)

            # 策略 1: 提取页面中的内嵌图片
            for page_num in range(len(doc)):
                page = doc[page_num]
                for img_index, img in enumerate(page.get_images(full=True)):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    if len(image_bytes) < 1024:
                        continue
                    figures.append({
                        "page_number": page_num,
                        "image_data": image_bytes,
                        "width": base_image.get("width", 0),
                        "height": base_image.get("height", 0),
                        "ext": base_image.get("ext", "png"),
                        "source": "embedded",
                    })

            # 策略 2: 页面截图（用于不含内嵌图片的 PDF）
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=150)
                image_bytes = pix.tobytes("png")
                if len(image_bytes) > 1024:
                    figures.append({
                        "page_number": page_num,
                        "image_data": image_bytes,
                        "width": pix.width,
                        "height": pix.height,
                        "ext": "png",
                        "source": "screenshot",
                    })

            doc.close()
            logger.debug("图片提取完成: %s, %d 张", file_path, len(figures))

        except Exception:
            logger.debug("图片提取异常: %s", traceback.format_exc())

        return figures


# ══════════════════════════════════════════════════════════════════════
# MultimodalEmbedding —— CLIP 文本+图片向量化
# ══════════════════════════════════════════════════════════════════════


class MultimodalEmbedding:
    """CLIP 多模态 Embedding 服务。

    使用 sentence-transformers 的 CLIP 模型同时对文本和图片编码，
    使文本和图片在统一向量空间可比。
    """

    def __init__(self, model_name: str = "sentence-transformers/clip-ViT-B-32"):
        self._model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
                logger.info("CLIP 模型已加载: %s", self._model_name)
            except Exception as e:
                logger.warning("CLIP 模型加载失败: %s", e)

    def embed_text(self, texts: list[str]) -> list[list[float]]:
        """对文本列表编码为向量。

        Args:
            texts: 文本列表。

        Returns:
            向量列表，每项为 float 列表。
        """
        if not texts:
            return []
        self._load()
        if self._model is None:
            return [[0.0]] * len(texts)
        try:
            embeddings = self._model.encode(texts, normalize_embeddings=True)
            return embeddings.tolist()
        except Exception as e:
            logger.warning("文本编码失败: %s", e)
            return [[0.0]] * len(texts)

    def embed_image(self, image_bytes_list: list[bytes]) -> list[list[float]]:
        """对图片字节流列表编码为向量。

        Args:
            image_bytes_list: 图片字节流列表。

        Returns:
            向量列表，每项为 float 列表。
        """
        if not image_bytes_list:
            return []
        self._load()
        if self._model is None:
            return [[0.0]] * len(image_bytes_list)
        try:
            from PIL import Image
            images = []
            for img_bytes in image_bytes_list:
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                images.append(img)
            embeddings = self._model.encode(images, normalize_embeddings=True)
            return embeddings.tolist()
        except Exception as e:
            logger.warning("图片编码失败: %s", e)
            return [[0.0]] * len(image_bytes_list)


# ══════════════════════════════════════════════════════════════════════
# MultimodalRetriever —— 图文混合检索
# ══════════════════════════════════════════════════════════════════════


class MultimodalRetriever:
    """管理 Milvus 图表向量集合 + 图文混合检索。

    创建独立的 Milvus 集合存储图片向量，支持文本→图片检索、
    图片→图片检索和图文混合检索。
    """

    def __init__(self, collection_name: str = "figure_embeddings"):
        self._collection_name = collection_name
        self._embedding = MultimodalEmbedding()
        self._milvus = None
        self._lock = threading.Lock()

    def _get_milvus(self):
        if self._milvus is not None:
            return self._milvus
        with self._lock:
            if self._milvus is not None:
                return self._milvus
            try:
                from backend.vectordb.milvus_client import MilvusManager
                self._milvus = MilvusManager()
                self._init_collection()
            except Exception as e:
                logger.warning("Milvus 连接失败 (多模态): %s", e)
            return self._milvus

    def _init_collection(self):
        if self._milvus is None:
            return
        try:
            if self._milvus.client.has_collection(self._collection_name):
                return
            schema = self._milvus.client.create_schema(
                auto_id=True, enable_dynamic_field=True,
            )
            schema.add_field("id", "int64", is_primary=True, auto_id=True)
            schema.add_field("image_embedding", "float_vector", dim=512)
            schema.add_field("filename", "varchar", max_length=255)
            schema.add_field("page_number", "int64")
            schema.add_field("file_path", "varchar", max_length=1024)
            schema.add_field("caption", "varchar", max_length=1000)

            index_params = self._milvus.client.prepare_index_params()
            index_params.add_index(
                field_name="image_embedding",
                index_type="HNSW",
                metric_type="IP",
                params={"M": 16, "efConstruction": 256},
            )
            self._milvus.client.create_collection(
                collection_name=self._collection_name,
                schema=schema,
                index_params=index_params,
            )
            logger.info("多模态集合已创建: %s", self._collection_name)
        except Exception as e:
            logger.warning("多模态集合初始化失败: %s", e)

    def index_figures(self, figures: list[dict], filename: str, file_path: str):
        """将提取的图片批量编码并写入 Milvus。

        Args:
            figures: FigureExtractor.extract_figures 的输出。
            filename: 源文件名。
            file_path: 源文件路径。
        """
        if not figures:
            return

        milvus = self._get_milvus()
        if milvus is None:
            return

        image_bytes_list = [f["image_data"] for f in figures]
        embeddings = self._embedding.embed_image(image_bytes_list)

        data = []
        for fig, emb in zip(figures, embeddings):
            data.append({
                "image_embedding": emb,
                "filename": filename,
                "page_number": fig["page_number"],
                "file_path": file_path,
                "caption": "",
            })

        try:
            milvus.client.insert(self._collection_name, data)
            logger.debug("多模态索引完成: %s, %d 张图", filename, len(data))
        except Exception as e:
            logger.warning("多模态索引失败: %s", e)

    def search_by_text(
        self, query: str, top_k: int = 5,
    ) -> list[dict]:
        """文本→图片检索：用文本查询找到最相关的图片。

        Args:
            query: 查询文本。
            top_k: 返回的最相关图片数。

        Returns:
            匹配的图片记录列表。
        """
        milvus = self._get_milvus()
        if milvus is None:
            return []

        query_emb = self._embedding.embed_text([query])[0]

        try:
            results = milvus.client.search(
                collection_name=self._collection_name,
                data=[query_emb],
                anns_field="image_embedding",
                param={"metric_type": "IP", "params": {"ef": 64}},
                limit=top_k,
                output_fields=["filename", "page_number", "caption"],
            )
            return results[0] if results else []
        except Exception as e:
            logger.warning("多模态检索失败: %s", e)
            return []


# ── 全局单例 ──────────────────────────────────────────────────────────

_multimodal_retriever: MultimodalRetriever | None = None
_retriever_lock = threading.Lock()


def get_multimodal_retriever() -> MultimodalRetriever:
    """获取全局多模态检索器单例。"""
    global _multimodal_retriever
    if _multimodal_retriever is None:
        with _retriever_lock:
            if _multimodal_retriever is None:
                _multimodal_retriever = MultimodalRetriever()
    return _multimodal_retriever


def reset_multimodal_retriever():
    """重置全局多模态检索器（测试用）。"""
    global _multimodal_retriever
    with _retriever_lock:
        _multimodal_retriever = None
