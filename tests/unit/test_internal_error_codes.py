"""内部错误码表必须与契约表逐码一致（`contracts/error-codes.md` §1）。

Go 的重试器只读 `retryable`、只按 HTTP 状态映射，所以 Python 侧这张表的每一列都是契约。
不一致时这里变红，而不是等 Go 把一个不可重试的错误重试到烧完预算。
"""

import json
import re
from pathlib import Path

import pytest

from backend.internal_api.codes import ERROR_CODES

_ROOT = Path(__file__).resolve().parents[2]
_TABLE_RE = re.compile(r"^\|\s*`([A-Z_]+)`\s*\|\s*(true|false)\s*\|\s*(\d{3})\s*\|")

pytestmark = pytest.mark.unit


def contract_table() -> dict[str, tuple[bool, int]]:
    rows: dict[str, tuple[bool, int]] = {}
    text = (_ROOT / "contracts" / "error-codes.md").read_text(encoding="utf-8")
    section = text.split("## 1. 内部错误码", 1)[1].split("## 2.", 1)[0]
    for line in section.splitlines():
        m = _TABLE_RE.match(line.strip())
        if m:
            rows[m.group(1)] = (m.group(2) == "true", int(m.group(3)))
    return rows


def test_python_table_matches_contract_table():
    expected = contract_table()
    assert set(expected) == set(ERROR_CODES), "错误码集合与契约表不一致"
    for code, (retryable, http) in expected.items():
        spec = ERROR_CODES[code]
        assert (spec.retryable, spec.http) == (retryable, http), f"{code} 的 retryable/http 与契约表不符"


def test_codes_match_schema_enum():
    schema = json.loads((_ROOT / "contracts" / "ai-execution.schema.json").read_text(encoding="utf-8"))
    assert set(schema["$defs"]["ErrorCode"]["enum"]) == set(ERROR_CODES)
