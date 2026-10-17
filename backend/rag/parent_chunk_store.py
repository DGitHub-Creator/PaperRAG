"""父级分块正文只读写 PostgreSQL，避免跨进程缓存和事务回滚产生脏读。"""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from backend.core.database import SessionLocal
from backend.core.models import ParentChunk, utc_now_naive


class ParentChunkStore:
    """为 Auto-merging Retriever 提供已提交的 L1/L2 父块。"""

    @staticmethod
    def _to_dict(item: ParentChunk) -> dict:
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

    def upsert_documents(self, docs: list[dict]) -> int:
        """一个事务写入全部父块，任何一条非法记录都使整批失败。"""
        if not docs:
            return 0
        now = utc_now_naive()
        # 顺序执行保证重复 chunk_id 的最后一个值生效，且不产生并发 SELECT/INSERT 竞争。
        with SessionLocal() as db, db.begin():
            for doc in docs:
                chunk_id = (doc.get("chunk_id") or "").strip()
                if not chunk_id:
                    raise ValueError("父块缺少 chunk_id")
                payload = {
                    "chunk_id": chunk_id,
                    "text": doc.get("text", ""),
                    "filename": doc.get("filename", ""),
                    "file_type": doc.get("file_type", ""),
                    "file_path": doc.get("file_path", ""),
                    "page_number": int(doc.get("page_number", 0) or 0),
                    "parent_chunk_id": doc.get("parent_chunk_id", ""),
                    "root_chunk_id": doc.get("root_chunk_id", ""),
                    "chunk_level": int(doc.get("chunk_level", 0) or 0),
                    "chunk_idx": int(doc.get("chunk_idx", 0) or 0),
                    "updated_at": now,
                }
                statement = insert(ParentChunk).values(**payload)
                db.execute(statement.on_conflict_do_update(
                    index_elements=[ParentChunk.chunk_id],
                    set_={key: value for key, value in payload.items() if key != "chunk_id"},
                ))
        return len(docs)

    def get_documents_by_ids(self, chunk_ids: list[str]) -> list[dict]:
        """批量读取已提交正文，保留输入顺序和重复项，跳过不存在的键。"""
        if not chunk_ids:
            return []
        with SessionLocal() as db:
            rows = db.scalars(select(ParentChunk).where(ParentChunk.chunk_id.in_(chunk_ids))).all()
            by_id = {row.chunk_id: self._to_dict(row) for row in rows}
        return [by_id[key] for key in chunk_ids if key in by_id]

    def delete_by_filename(self, filename: str) -> int:
        """一个事务删除文件的父块，不存在时返回零。"""
        if not filename:
            return 0
        with SessionLocal() as db, db.begin():
            result = db.execute(delete(ParentChunk).where(ParentChunk.filename == filename))
            return result.rowcount
