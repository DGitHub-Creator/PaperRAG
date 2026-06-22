"""父级分块文档存储（PostgreSQL + Redis 缓存旁路）—— 用于 Auto-merging Retriever。

存储策略:
    - L1/L2 父级分块写入 PostgreSQL（持久化）
    - Redis 缓存热点父块，读取时优先命中缓存（缓存旁路模式）
    - 删除时同步清理 PostgreSQL 和 Redis

缓存旁路模式（Cache-Aside）:
    读: Redis 查询 → 命中返回 / 未命中查 PG → 回填 Redis
    写: 写 PG + 更新 Redis
    删: 删 PG + 删除对应 Redis key

使用示例:
    >>> from backend.rag.parent_chunk_store import ParentChunkStore
    >>> store = ParentChunkStore()
    >>> store.upsert_documents(parent_docs)
"""

from datetime import UTC, datetime

from backend.core.database import SessionLocal
from backend.core.logging_config import get_logger
from backend.core.models import ParentChunk
from backend.services.cache import cache

logger = get_logger(__name__)


class ParentChunkStore:
    """基于 PostgreSQL + Redis 的父级分块存储。

    为 Auto-merging Retriever 提供父块回取能力:
    - 检索命中 L3 叶子块 → 通过 parent_chunk_id 查找 L2 父块
    - 检索命中 L2 子块 → 通过 parent_chunk_id 查找 L1 根块
    """

    @staticmethod
    def _to_dict(item: ParentChunk) -> dict:
        """将 ORM 模型转换为 dict（用于缓存和返回）。"""
        return {
            "text": item.text,
            "filename": item.filename,
            "file_type": item.file_type,
            "file_path": item.file_path,
            "page_number": item.page_number,
            "chunk_id": item.chunk_id,
            "parent_chunk_id": item.parent_chunk_id,
            "root_chunk_id": item.root_chunk_id,
            "chunk_level": item.chunk_level,
            "chunk_idx": item.chunk_idx,
        }

    @staticmethod
    def _cache_key(chunk_id: str) -> str:
        """生成 Redis 缓存键。"""
        return f"parent_chunk:{chunk_id}"

    def upsert_documents(self, docs: list[dict]) -> int:
        """写入或更新父级分块（存在则更新，不存在则插入）。

        每条记录同时写入 PostgreSQL 和 Redis 缓存。

        Args:
            docs: 父级分块数据列表，每个 dict 需含 chunk_id、text、filename 等字段。

        Returns:
            实际写入的条数。
        """
        if not docs:
            return 0

        db = SessionLocal()
        upserted = 0
        try:
            for doc in docs:
                chunk_id = (doc.get("chunk_id") or "").strip()
                if not chunk_id:
                    continue

                # 构建负载：区分 PG 字段和缓存字段
                record = db.query(ParentChunk).filter(
                    ParentChunk.chunk_id == chunk_id
                ).first()

                payload = {
                    "text": doc.get("text", ""),
                    "filename": doc.get("filename", ""),
                    "file_type": doc.get("file_type", ""),
                    "file_path": doc.get("file_path", ""),
                    "page_number": int(doc.get("page_number", 0) or 0),
                    "parent_chunk_id": doc.get("parent_chunk_id", ""),
                    "root_chunk_id": doc.get("root_chunk_id", ""),
                    "chunk_level": int(doc.get("chunk_level", 0) or 0),
                    "chunk_idx": int(doc.get("chunk_idx", 0) or 0),
                    "updated_at": datetime.now(UTC),
                }
                cache_payload = {
                    "chunk_id": chunk_id,
                    "text": payload["text"],
                    "filename": payload["filename"],
                    "file_type": payload["file_type"],
                    "file_path": payload["file_path"],
                    "page_number": payload["page_number"],
                    "parent_chunk_id": payload["parent_chunk_id"],
                    "root_chunk_id": payload["root_chunk_id"],
                    "chunk_level": payload["chunk_level"],
                    "chunk_idx": payload["chunk_idx"],
                }

                # PG upsert
                if record:
                    for key, value in payload.items():
                        setattr(record, key, value)
                else:
                    db.add(ParentChunk(chunk_id=chunk_id, **payload))

                # Redis 缓存回填
                cache.set_json(self._cache_key(chunk_id), cache_payload)
                upserted += 1

            db.commit()
            logger.info("父块入库完成: %d 条", upserted)
        except Exception:
            db.rollback()
            logger.exception("父块入库失败")
            raise
        finally:
            db.close()

        return upserted

    def get_documents_by_ids(self, chunk_ids: list[str]) -> list[dict]:
        """根据 chunk_id 列表批量查询父块。

        缓存旁路: Redis 先查 → 缺失的从 PostgreSQL 补查 → 回填 Redis。

        Args:
            chunk_ids: chunk_id 字符串列表。

        Returns:
            按输入顺序排列的文档 dict 列表（缺失的跳过）。
        """
        if not chunk_ids:
            return []

        ordered_results: dict[str, dict] = {}
        missing_ids: list[str] = []

        # 第一趟: Redis 查询
        for chunk_id in chunk_ids:
            key = (chunk_id or "").strip()
            if not key:
                continue
            cached = cache.get_json(self._cache_key(key))
            if cached:
                ordered_results[key] = cached
            else:
                missing_ids.append(key)

        # 第二趟: PostgreSQL 补查未命中的
        if missing_ids:
            db = SessionLocal()
            try:
                rows = db.query(ParentChunk).filter(
                    ParentChunk.chunk_id.in_(missing_ids)
                ).all()
                for row in rows:
                    payload = self._to_dict(row)
                    ordered_results[row.chunk_id] = payload
                    # 回填 Redis
                    cache.set_json(self._cache_key(row.chunk_id), payload)
                logger.debug(
                    "父块查询: %d/%d Redis命中, %d PG补查",
                    len(chunk_ids) - len(missing_ids), len(chunk_ids), len(rows),
                )
            finally:
                db.close()

        return [ordered_results[item] for item in chunk_ids if item in ordered_results]

    def delete_by_filename(self, filename: str) -> int:
        """按文件名删除所有关联的父级分块（PG + Redis 同步清理）。

        Args:
            filename: 文件名（与入库时一致）。

        Returns:
            实际删除的条数。
        """
        if not filename:
            return 0

        db = SessionLocal()
        try:
            rows = db.query(ParentChunk).filter(
                ParentChunk.filename == filename
            ).all()
            chunk_ids = [row.chunk_id for row in rows]
            deleted = len(chunk_ids)

            if deleted > 0:
                # PostgreSQL 批量删除
                db.query(ParentChunk).filter(
                    ParentChunk.filename == filename
                ).delete(synchronize_session=False)
                db.commit()

                # Redis 缓存失效
                for chunk_id in chunk_ids:
                    cache.delete(self._cache_key(chunk_id))

                logger.info("父块删除: %s → %d 条", filename, deleted)
            return deleted
        except Exception:
            db.rollback()
            logger.exception("父块删除失败: %s", filename)
            raise
        finally:
            db.close()
