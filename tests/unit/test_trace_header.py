"""追踪头 `X-Trace-Id` 的接受集合（契约 components.parameters.TraceId，台账 C38）。

这条规则跨三种语言实现（契约 / Go / Python），所以单测的职责不是"证明正则会写"，
而是钉住**取值集合**：哪些入站值被沿用、哪些被换成新生成的 id。
两侧漂移的表现是日志关联悄悄断掉——请求在 Go 换一个号、Python 再换一个，
排障时看不出是同一个请求。三方字面量一致性另有 `test_check_contracts.py` 核对。
"""

import re

import pytest

from backend.core.logging_config import TRACE_ID_HEADER, TRACE_ID_RULE, sanitize_trace_id

HEX32 = re.compile(r"^[0-9a-f]{32}$")


def test_header_name_is_the_documented_one():
    assert TRACE_ID_HEADER == "X-Trace-Id"
    assert TRACE_ID_RULE == r"^[A-Za-z0-9._-]{1,128}$"


@pytest.mark.parametrize(
    "inbound",
    [
        "a",
        "0",
        "abc-DEF_1.2",
        "a" * 128,
        "deadbeefdeadbeef",
        "00000000000000000000000000000001",
    ],
)
def test_legal_values_are_carried_through(inbound):
    assert sanitize_trace_id(inbound) == inbound


@pytest.mark.parametrize(
    ("label", "inbound"),
    [
        ("缺失", None),
        ("空串", ""),
        ("超长", "a" * 129),
        ("含空格", "abc def"),
        ("含换行", "abc\n"),
        ("含 CR", "abc\r\n"),
        ("非 ASCII", "追踪"),
        ("含冒号", "a:b"),
        ("含斜杠", "a/b"),
        ("含逗号", "a,b"),
        ("带方括号的复合值", "['abcdef', 'fedcba']"),
        ("含引号", '"abc"'),
    ],
)
def test_illegal_values_are_replaced_not_echoed(label, inbound):
    """非法入站值必须换成新 id，且**不回显**——不回显是 §8 写死的口径。"""
    out = sanitize_trace_id(inbound)
    assert out != inbound, f"{label}：非法值被原样沿用了"
    assert re.fullmatch(TRACE_ID_RULE, out), f"{label}：生成值不符合契约形状 {out!r}"
    assert HEX32.fullmatch(out), f"Python 直连时的生成形态是 32 位十六进制，实得 {out!r}"


def test_generated_ids_are_not_repeated():
    assert len({sanitize_trace_id(None) for _ in range(50)}) == 50


def test_comma_joined_duplicate_header_is_rejected():
    """中间层把两个值并成一个 `a,b` 时，那已经不是任何一个入站 id，必须整体作废。"""
    out = sanitize_trace_id("abcdef,fedcba")
    assert out != "abcdef,fedcba"
