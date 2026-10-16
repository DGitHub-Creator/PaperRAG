"""已有 ai_executions 表的生产存储；DDL 仍由 Go 迁移命令管理。"""

from dataclasses import asdict
from threading import Lock

from sqlalchemy import MetaData, Table, null, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from backend.core.database import SessionLocal
from backend.internal_api.executions import Execution, ExecutionStore, new_execution
from backend.internal_api.schemas import ErrorDetail, Usage


def _decode(record) -> Execution:
    values = dict(record)
    for field in ("run_id", "trace_id", "lease_token"):
        values[field] = values[field] or None
    values["usage"] = Usage.model_validate(values["usage"]) if values["usage"] is not None else None
    values["errors"] = [ErrorDetail.model_validate(error) for error in values["errors"]]
    return Execution(**values)


def _encode(row: Execution) -> dict:
    values = asdict(row)
    for field in ("run_id", "trace_id", "lease_token"):
        values[field] = values[field] or ""
    values["usage"] = row.usage.model_dump(mode="json") if row.usage is not None else None
    values["errors"] = [error.model_dump(mode="json") for error in row.errors]
    if row.result is None:
        values["result"] = null()
    return values


class PostgresExecutionStore(ExecutionStore):
    def __init__(self, session_factory=None):
        self._session_factory = session_factory
        self._table = None
        self._schema_lock = Lock()

    def _session(self):
        return (self._session_factory or SessionLocal)()

    def _get_table(self, db):
        if self._table is None:
            with self._schema_lock:
                if self._table is None:
                    # 反射实际迁移结果，禁止 ORM 静默 create_all 或在这里复制一套 DDL。
                    self._table = Table("ai_executions", MetaData(), autoload_with=db.connection())
        return self._table

    def reset(self):
        raise RuntimeError("生产执行记录不能通过测试 reset 清空")

    def submit(self, req):
        with self._session() as db, db.begin():
            table = self._get_table(db)
            row = new_execution(req)
            statement = insert(table).values(**_encode(row)).on_conflict_do_nothing().returning(table)
            inserted = db.execute(statement).mappings().first()
            if inserted is not None:
                return _decode(inserted), False
            existing = db.execute(select(table).where(or_(
                table.c.task_id == req.task_id,
                (table.c.run_id == (req.run_id or "")) & (table.c.idempotency_key == req.idempotency_key),
            ))).mappings().all()
            if len(existing) != 1:
                raise ValueError("task_id 与幂等键指向不同执行")
            return _decode(existing[0]), True

    def _mutate(self, execution_id, change):
        with self._session() as db, db.begin():
            table = self._get_table(db)
            record = db.execute(select(table).where(table.c.execution_id == execution_id).with_for_update()).mappings().first()
            if record is None:
                return None
            row = _decode(record)
            before = _encode(row)
            result = change(row)
            after = _encode(row)
            if after != before:
                db.execute(update(table).where(table.c.execution_id == execution_id).values(**after))
            return result
