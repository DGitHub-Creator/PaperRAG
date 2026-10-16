"""ORM 与真库列定义的比较；缺少 DEFAULT 本身不是漂移。"""

import re


def orm_column_specs() -> dict:
    from sqlalchemy import Integer
    from sqlalchemy.dialects import postgresql
    from backend.core.database import Base
    import backend.core.models  # noqa: F401

    dialect = postgresql.dialect()
    return {
        table.name: {
            column.name: {
                "type": str(column.type.compile(dialect=dialect)),
                "length": getattr(column.type, "length", None),
                "nullable": column.nullable,
                "default": str(column.server_default.arg) if column.server_default is not None else None,
                "serial": column.primary_key and isinstance(column.type, Integer) and column.autoincrement in (True, "auto") and not column.foreign_keys,
            }
            for column in table.columns
        }
        for table in Base.metadata.sorted_tables
    }


def _type(value):
    value = re.sub(r"\s*\(.*?\)", "", value).strip().lower()
    return {"character varying": "varchar", "timestamp without time zone": "timestamp", "timestamp with time zone": "timestamptz", "double precision": "float8"}.get(value, value)


def _default(value):
    if value is None:
        return None
    value = re.sub(r"::(?:character varying|timestamp without time zone|text|jsonb?|integer|bigint|boolean)", "", str(value), flags=re.I).strip()
    return "now()" if value.lower() in {"current_timestamp", "now()"} else value


def diff_columns(live_columns: list[dict], declared: dict) -> list[dict]:
    actual = {}
    for row in live_columns:
        actual.setdefault(row["table_name"], {})[row["column_name"]] = row
    differences = []
    for table in sorted(set(actual) | set(declared)):
        live, model = actual.get(table, {}), declared.get(table, {})
        for name in sorted(set(live) | set(model)):
            if name not in live or name not in model:
                differences.append({"table": table, "column": name, "kind": "only_in_orm" if name not in live else "only_in_db"})
                continue
            row, spec = live[name], model[name]
            pairs = {
                "type": (_type(row["data_type"]), _type(spec["type"])),
                "length": (row.get("character_maximum_length"), spec["length"]),
                "nullable": (row["is_nullable"] == "YES", spec["nullable"]),
            }
            if not (spec["serial"] and str(row.get("column_default", "")).startswith("nextval(")):
                pairs["default"] = (_default(row.get("column_default")), _default(spec["default"]))
            for kind, (got, wanted) in pairs.items():
                if got != wanted:
                    differences.append({"table": table, "column": name, "kind": kind, "db": got, "orm": wanted})
    return differences
