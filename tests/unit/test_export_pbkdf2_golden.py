"""`scripts/export_pbkdf2_golden.py` 的判定单测（X5 的 mock 级证据）。

X5 要的是"Go 逐条通过 golden vectors"，那是 P0-6 的 `TestVerifyLegacyHash`。
这里管的是**导出件本身可信不可信**，三件事：

  1. 裁判绑定：每条向量都由生产代码 `backend/core/auth.py:verify_password` 判过，
     期望值就是它的返回值。裁判不过的向量不能进文件——否则 Go 通过了一份"两边都不认"的
     清单，X5 全绿却什么都证明不了。
  2. 不含凭据：文件里不许出现任何明文口令；真库的 `password_hash` 也不许出现
     （离线可爆破），只允许形状统计。
  3. 覆盖面不是自封的：`coverage_check` 必须能指出"库里有 rounds=200000 而向量没覆盖"，
     以及"库里还有 bcrypt 族"——后者是 Go 接管 `users` 时会把真人锁死的场景。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.export_pbkdf2_golden import (  # noqa: E402
    ALGORITHM,
    OUT,
    PASSWORD_PREFIX,
    URLSAFE_SALT,
    build_document,
    build_hash,
    coverage_check,
    VECTORS,
)

from backend.core.auth import verify_password  # noqa: E402  —— 这就是裁判本身


@pytest.fixture(scope="module")
def doc():
    return build_document()


class TestOracleBinding:
    def test_every_vector_is_decided_by_production_verify_password(self, doc):
        """期望值必须等于生产裁判的返回值，而不是我手写的布尔。"""
        for v in doc["vectors"]:
            password = PASSWORD_PREFIX + v["vector_id"]
            assert verify_password(password, v["hash"]) is v["expect_verify"], v["vector_id"]

    def test_positive_and_negative_vectors_both_exist(self, doc):
        """只有正向向量的清单证明不了 Go 会拒绝；负向是另一半。"""
        assert len([v for v in doc["vectors"] if v["expect_verify"]]) >= 5
        assert len([v for v in doc["vectors"] if not v["expect_verify"]]) >= 3

    def test_negative_vectors_differ_from_a_valid_hash_only_where_they_should(self, doc):
        """摘要截断那条：除了 digest 段，其它段与 baseline 完全一致。

        否则它测的是"格式不同"，而不是"长度不足要拒绝"，断言就落错了地方。
        """
        good = next(v for v in doc["vectors"] if v["vector_id"] == "baseline")["hash"]
        short = next(v for v in doc["vectors"] if v["vector_id"] == "truncated-digest")["hash"]
        assert good.split("$")[:2] == short.split("$")[:2]
        assert len(short.split("$")[3]) < len(good.split("$")[3])

    def test_malformed_segment_count_is_not_mistaken_for_a_hash(self, doc):
        bad = next(v for v in doc["vectors"] if v["vector_id"] == "malformed-segments")
        assert bad["hash"].count("$") == 2
        assert bad["digest_bytes"] == 0


class TestShapeCoverage:
    def test_rounds_and_salt_lengths_actually_vary(self, doc):
        """一份只有一个形状的清单等于没做——04 §风险表点名的就是这三轴。"""
        assert len({v["rounds"] for v in doc["vectors"]}) >= 3
        assert len({v["salt_bytes"] for v in doc["vectors"]}) >= 3
        assert {v["b64_variant"] for v in doc["vectors"]} == {"standard", "urlsafe"}

    def test_production_rounds_value_is_present(self, doc):
        """310000 是 `core/config/auth.py` 的默认值；没有它，向量集与生产无关。"""
        assert any(v["rounds"] == 310000 for v in doc["vectors"])

    def test_urlsafe_vector_really_cannot_be_read_as_standard_b64(self):
        """这条向量的意义在于"标准解码器读不出同一份盐"，所以盐串必须含 urlsafe 专属字符。"""
        spec = next(s for s in VECTORS if s["vector_id"] == "urlsafe-salt")
        salt_b64 = build_hash(spec).split("$")[2]
        assert set("-_") & set(salt_b64), salt_b64
        assert URLSAFE_SALT == bytes([0xFB, 0xFF] * 8)

    def test_algorithm_prefix_is_the_stored_one(self, doc):
        assert all(v["hash"].startswith(f"{ALGORITHM}$") for v in doc["vectors"])
        assert all(v["algorithm"] == ALGORITHM for v in doc["vectors"])

    def test_generation_is_deterministic(self, doc):
        """CI 上重跑必须逐字相同，否则 --check 门禁每天都在报假漂移。"""
        assert build_document() == doc


class TestNoCredentials:
    def test_no_plaintext_password_appears_anywhere_in_the_document(self, doc):
        """逐条把 `password_rule` 现算成口令，再确认这条口令不在文件里。

        `password_rule` 字段本身必然含前缀字面量（它就是给 Go 用的规则），所以扫描范围
        要排除它——排除之后仍然逐条查得到"重建口令不出现在别处"，才是这条断言的内容。
        """
        text = json.dumps({k: v for k, v in doc.items() if k != "password_rule"}, ensure_ascii=False)
        assert PASSWORD_PREFIX not in text
        for v in doc["vectors"]:
            assert (PASSWORD_PREFIX + v["vector_id"]) not in text

    def test_document_has_no_live_shape_by_default(self, doc):
        """真库摘要只在显式 --from-db 时才统计，而且永远只以形状出现，不进文件。"""
        assert "live_shape" not in doc


class TestCoverageCheck:
    def test_uncovered_rounds_and_salt_are_reported(self, doc):
        shape = {"rounds": {"200000": "12"}, "salt_bytes": {"12": "3"}, "families": {}}
        problems = coverage_check(doc, shape)
        assert any("rounds=200000" in p for p in problems)
        assert any("盐长 12" in p for p in problems)

    def test_leftover_bcrypt_hashes_are_flagged_as_a_lockout_risk(self, doc):
        """Go 不支持 bcrypt 时，接管 users 会把这批人挡在门外——必须显式处置，不能默默绿。"""
        shape = {"rounds": {}, "salt_bytes": {}, "families": {"bcrypt": 7}}
        problems = coverage_check(doc, shape)
        assert len(problems) == 1
        assert "锁死" in problems[0]

    def test_matching_shape_produces_no_complaints(self, doc):
        shape = {"rounds": {"40000": "9", "260000": "1"}, "salt_bytes": {"16": "9", "8": "1"}, "families": {}}
        assert coverage_check(doc, shape) == []


def test_shipped_file_matches_the_generator(doc):
    """提交进仓库的导出件必须能由生成器逐字重建（`--check` 的等价断言）。

    复用模块级 fixture：再跑一次 `build_document()` 就是再跑一遍全套 PBKDF2，
    那 2 秒花在最慢的 unit 用例上没有意义。
    """
    assert OUT.read_text(encoding="utf-8") == json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
