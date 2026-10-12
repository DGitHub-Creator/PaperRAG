"""`scripts/export_jwt_golden.py` 的判定单测（X4 令牌半侧的 mock 级证据）。

X4 要的是"Python/Go 签发的 token 双向可校验"，Go 那一半在
`server/internal/auth/jwt_test.go` 的 `TestParseGoldenTokens`。这里管的是
**导出件本身可信不可信**，四件事：

  1. 裁判绑定：每条向量的 `expect_accept` 都等于生产函数
     `get_user_from_bearer_token` 的返回值，不是我手写的布尔。
  2. 分层归属如实：`rejected_by="database"` 那条必须**真的**是回库那一步拒的
     （令牌层三项全过），否则 Go 侧就会按错的层次去断言，两边各验一套。
  3. 不含真凭据：文件里的 secret 是合成的那个常量，且必须与本机环境里的
     `JWT_SECRET_KEY`（如果有）不同——否则就是把真密钥提交进仓库。
  4. 边界声明还在：两侧结论**不同**的那条轴（缺 exp）必须写在 `divergences` 里。
     边界声明消失，读文件的人会以为"逐条一致"覆盖了全部情形。

与 `test_export_pbkdf2_golden.py` 的一处结构性差别：那份文件可逐字节重建
（盐由 vector_id 派生），所以门禁是 `--check` 比对字节；**这份不行**——token 的
`exp` 是"签发时刻 + 有效期"。所以这里的"文件与生成器一致"改成语义校验：
把已提交的 token 重新交给生产裁判，结论与 claims 都必须仍与文件一致。
"""

import base64
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.export_jwt_golden import (  # noqa: E402
    ALGORITHM,
    KNOWN_USER,
    OUT,
    POSITIVE_EXPIRE_MINUTES,
    REJECTED_BY,
    SECRET,
    UNKNOWN_USER,
    WRONG_SECRET,
    build_document,
    check_shipped,
    judge,
)

from backend.core.auth import get_user_from_bearer_token  # noqa: E402  —— 裁判本身

B64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


@pytest.fixture(scope="module")
def doc():
    return build_document()


def vector(doc, vid):
    return next(v for v in doc["vectors"] if v["vector_id"] == vid)


class TestOracleBinding:
    def test_every_vector_is_decided_by_the_production_function(self, doc):
        """期望值必须等于生产函数的返回值。

        这条是整个导出件的地基：裁判不过的向量进了文件，Go 逐条通过就等于
        两边一起验了一份错清单，X4 全绿而什么都证明不了。
        """
        for v in doc["vectors"]:
            assert judge(v["token"]) is v["expect_accept"], v["vector_id"]

    def test_judge_is_the_real_function_not_a_reimplementation(self, doc):
        """裁判必须就是 `get_user_from_bearer_token` 本体。

        用桩 db 跑真函数，而不是在导出脚本里另写一份 sub/type 判断——
        另写的那份会与生产代码各自漂移，而漂移是静默的。
        """
        from scripts.export_jwt_golden import _StubDB, _production_auth

        with _production_auth() as production:
            assert production.get_user_from_bearer_token is get_user_from_bearer_token
            assert production.get_user_from_bearer_token(vector(doc, "access-user")["token"], _StubDB()) is not None

    def test_positive_and_negative_vectors_both_exist(self, doc):
        """只有正向的清单证明不了 Go 会拒绝；只有负向的清单证明不了 Go 会放行。"""
        assert len([v for v in doc["vectors"] if v["expect_accept"]]) >= 3
        assert len([v for v in doc["vectors"] if not v["expect_accept"]]) >= 5

    def test_the_three_axes_named_by_doc_07_are_covered(self, doc):
        """`07` §兼容面表点名了三件事：type 语义、过期、错误 secret。逐条落实。"""
        ids = {v["vector_id"] for v in doc["vectors"]}
        assert "refresh-as-access" in ids, "type 语义没有向量"
        assert "expired-access" in ids, "过期没有向量"
        assert "wrong-secret" in ids, "错误 secret 没有向量"

    def test_expired_vector_is_genuinely_expired(self, doc):
        """过期那条必须是"签发时就已过期"，而不是"等到跑测试时才过期"。

        后者会让用例在下个月悄悄变红，排查方向完全错。
        """
        exp = vector(doc, "expired-access")["claims"]["exp"]
        assert exp < datetime.now(UTC).timestamp(), "过期向量的 exp 竟然还在未来"

    def test_positive_vectors_stay_valid_for_years(self, doc):
        """正向向量的有效期钉成 10 年，否则文件下一轮开发就过期了。

        这是"本文件不能逐字节重建"的补偿措施：既然不能靠重导保证新鲜，
        就得让已提交的 token 活得够久。
        """
        horizon = datetime.now(UTC).timestamp() + POSITIVE_EXPIRE_MINUTES * 60 * 0.9
        for v in doc["vectors"]:
            if not v["expect_accept"]:
                continue
            assert v["claims"]["exp"] > horizon, f"{v['vector_id']} 的有效期不够长"

    def test_wrong_secret_vector_really_uses_the_other_secret(self, doc):
        """"错误 secret"那条必须真是另一把钥匙签的，而不是别的原因导致验不过。

        否则它测的是"某种失败"，不是"密钥不匹配"。
        """
        from jose import JWTError, jwt

        token = vector(doc, "wrong-secret")["token"]
        # 用文件里的 secret 验 → 失败
        with pytest.raises(JWTError):
            jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        # 用那把"错的"钥匙验 → 成功（证明差别只在密钥）
        claims = jwt.decode(token, WRONG_SECRET, algorithms=[ALGORITHM])
        assert claims["sub"] == KNOWN_USER


class TestLayerAttribution:
    def test_every_negative_vector_says_which_layer_rejects_it(self, doc):
        for v in doc["vectors"]:
            if v["expect_accept"]:
                assert v["rejected_by"] is None, v["vector_id"]
            else:
                assert v["rejected_by"] in {"token", "database"}, v["vector_id"]

    def test_rejected_by_map_covers_exactly_the_negative_vectors(self, doc):
        """映射表与向量集不能各说各话：漏了会 KeyError，多了是僵尸条目。"""
        negatives = {v["vector_id"] for v in doc["vectors"] if not v["expect_accept"]}
        assert set(REJECTED_BY) == negatives

    def test_the_database_layer_vector_passes_all_token_level_checks(self, doc):
        """`rejected_by="database"` 必须名副其实。

        这条是分层归属的**证明**而不是标注：unknown-user 那枚令牌签名有效、未过期、
        带 sub、type=access，令牌层三项全过；它被拒只因为桩库里没有这个用户。
        Go 侧据此把它交给 service 层用例断言，而不是塞进 ParseAccessToken 的用例里。
        """
        from jose import jwt

        from scripts.export_jwt_golden import _production_auth

        v = vector(doc, "unknown-user")
        assert v["rejected_by"] == "database"
        with _production_auth() as production:
            payload = jwt.decode(v["token"], production.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == UNKNOWN_USER
        assert payload["type"] == "access"
        assert payload["exp"] > datetime.now(UTC).timestamp()
        # 而整体裁判仍然拒绝它
        assert judge(v["token"]) is False

    def test_exactly_one_vector_covers_the_database_layer(self, doc):
        """回库那一层至少要有向量，且不能只靠令牌层的向量假装覆盖。"""
        db_layer = [v["vector_id"] for v in doc["vectors"] if v["rejected_by"] == "database"]
        assert db_layer == ["unknown-user"]


class TestClaimsRecorded:
    def test_claims_match_the_token_payload(self, doc):
        """文件记的 claims 必须与 token 里的逐字一致，否则 Go 侧对的是错的参照。"""
        from jose import jwt

        for v in doc["vectors"]:
            actual = jwt.get_unverified_claims(v["token"])
            for key in ("sub", "role", "type", "exp"):
                assert v["claims"][key] == actual.get(key), f"{v['vector_id']}.{key}"

    def test_access_vectors_carry_the_four_production_claims(self, doc):
        """生产 create_access_token 的载荷就是 sub/role/type/exp 四项，一项不多。

        多出来的字段 Python 侧读不到，只会让两侧形状漂移而没人发现。
        """
        v = vector(doc, "access-user")
        assert set(v["claims"]) == {"sub", "role", "type", "exp"}
        assert v["claims"]["type"] == "access"
        assert v["claims"]["sub"] == KNOWN_USER

    def test_legacy_vector_really_has_no_type_claim(self, doc):
        """"历史令牌不带 type"那条必须真的不带——带了就测不到 None 等同 access 这条规则。"""
        from jose import jwt

        payload = jwt.get_unverified_claims(vector(doc, "no-type-legacy")["token"])
        assert "type" not in payload
        assert vector(doc, "no-type-legacy")["expect_accept"] is True

    def test_tampered_vector_differs_from_baseline_only_in_signature(self, doc):
        """篡改那条：header 与 payload 与 access-user 逐字相同，只有签名段不同。

        否则它测的是"形状不同"，而不是"签名对不上"，断言就落错了地方
        （与 pbkdf2 那份 truncated-digest 的用意相同）。
        """
        good = vector(doc, "access-user")["token"]
        bad = vector(doc, "tampered-signature")["token"]
        assert good.split(".")[:2] == bad.split(".")[:2]
        assert good.split(".")[2] != bad.split(".")[2]


class TestNoRealCredentials:
    def test_secret_is_the_synthetic_constant(self, doc):
        assert doc["secret"] == SECRET
        assert doc["algorithm"] == ALGORITHM

    def test_secret_is_not_the_machine_secret(self, doc):
        """文件里的 secret 不能就是本机/CI 环境里的那个 JWT_SECRET_KEY。

        合成 secret 写进仓库是安全的（它只能验通一批指向不存在用户的令牌）；
        真密钥写进仓库就是泄露。这条用例把两者的界线钉住。
        """
        real = os.environ.get("JWT_SECRET_KEY", "")
        if real:
            assert doc["secret"] != real, "导出件里的 secret 与本机 JWT_SECRET_KEY 相同"

    def test_warning_states_the_secret_is_synthetic(self, doc):
        assert "合成" in doc["warning"]
        assert "永不入仓库" in doc["warning"]

    def test_no_password_hash_shape_in_the_file(self, doc):
        """这份文件不该出现 pbkdf2 哈希串——两份 golden 各管一件事，混了就会有人
        以为 JWT 文件里也能找到口令摘要。"""
        raw = json.dumps(doc, ensure_ascii=False)
        assert "pbkdf2_sha256$" not in raw


class TestDivergences:
    def test_the_exp_axis_is_declared(self, doc):
        """缺 exp 是两侧结论**相反**的那条轴，必须写在文件里。

        2026-10-12 两侧实跑核对过：同一枚缺 exp 的令牌，Python 的生产函数接受
        （python-jose 只在 exp 存在时校验），Go 拒绝（WithExpirationRequired）。
        """
        axes = " ".join(d["axis"] for d in doc["divergences"])
        assert "exp" in axes
        exp_axis = next(d for d in doc["divergences"] if "exp" in d["axis"])
        assert "接受" in exp_axis["python"] and "拒" in exp_axis["go"]
        assert exp_axis["why_not_in_vectors"], "必须说明为什么这条不做成向量"

    def test_divergent_axes_are_not_smuggled_in_as_vectors(self, doc):
        """结论相反的轴不能混进 vectors：那会让"逐条一致"这个判据自相矛盾。"""
        for v in doc["vectors"]:
            assert "exp" in v["claims"], f"{v['vector_id']} 缺 exp，它属于 divergences 而不是 vectors"

    def test_the_algorithm_axis_is_declared(self, doc):
        axes = " ".join(d["axis"] for d in doc["divergences"])
        assert "alg" in axes


class TestSignaturePaddingBitsAgreeWithGo:
    """HS256 签名 32 字节 → base64url 43 字符，末字符只承载 4 个有效位，低 2 位是填充位。

    只改填充位，解出来的签名字节一个都没变，于是**两侧都照常接受**。这不是漏洞，
    是 base64 的正常语义。2026-10-12 两侧实跑核对过（Go 侧对应用例
    `TestNonCanonicalSignatureTrailingBits`），这里把 Python 那一半也钉住，
    免得将来有人以为"Go 太宽松"而去改它。

    踩过的坑值得留在代码里：导出脚本的第一版把 tampered-signature 造成
    "末字符按字母表挪一位"，结果生产裁判判它**通过**、导出被顶回来——
    一个自以为在测"签名校验有效"的向量，实际测的是"我会不会改错地方"。
    """

    def variant(self, token: str, delta: int) -> str:
        head, payload, signature = token.split(".")
        idx = B64URL_ALPHABET.index(signature[-1])
        assert idx & 3 == 0, "规范编码下末字符的低 2 位应是 0（填充位）"
        return f"{head}.{payload}.{signature[:-1]}{B64URL_ALPHABET[idx ^ delta]}"

    def test_padding_bit_only_changes_are_accepted(self, doc):
        token = vector(doc, "access-user")["token"]
        for delta in (1, 2, 3):
            assert judge(self.variant(token, delta)) is True, f"末字符 ^{delta} 只动填充位，应被接受"

    def test_significant_bit_changes_are_rejected(self, doc):
        token = vector(doc, "access-user")["token"]
        for delta in (4, 8, 16):
            assert judge(self.variant(token, delta)) is False, f"末字符 ^{delta} 动到有效位，应被拒绝"


class TestShippedFile:
    def test_shipped_file_is_still_judged_as_recorded(self):
        """已提交的文件必须仍被生产裁判判成它自己记的结论（语义版的一致性门禁）。

        与 pbkdf2 那份的字节比对不同，这里比的是"重判结果 + claims + 结构性字段"。
        能抓出三件字节比对抓不到的事：文件被手改过、正向 token 已经过期、
        生产裁判的语义变了。
        """
        if not OUT.is_file():
            pytest.fail(f"{OUT} 不存在：先跑 uv run python scripts/export_jwt_golden.py")
        problems = check_shipped(OUT, build_document())
        assert problems == [], "\n".join(problems)

    def test_shipped_file_declares_its_reproducibility_limit(self):
        """文件必须自己说明"不能逐字节重建"，否则下一个人会以为 --check 是字节比对。"""
        shipped = json.loads(OUT.read_text(encoding="utf-8"))
        assert "不能逐字节重建" in shipped["reproducibility"]
        assert "语义校验" in shipped["reproducibility"]

    def test_shipped_file_names_its_judge(self):
        shipped = json.loads(OUT.read_text(encoding="utf-8"))
        assert "get_user_from_bearer_token" in shipped["judge"]
        assert shipped["known_user"] == KNOWN_USER
        assert shipped["unknown_user"] == UNKNOWN_USER

    def test_check_catches_a_flipped_expectation(self, tmp_path):
        """门禁会红而不是恒过：把一条负向向量的期望翻过来，check_shipped 必须报出来。"""
        doc = build_document()
        tampered = json.loads(json.dumps(doc, ensure_ascii=False))
        for v in tampered["vectors"]:
            if v["vector_id"] == "refresh-as-access":
                v["expect_accept"] = True
        path = tmp_path / "jwt_golden.json"
        path.write_text(json.dumps(tampered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

        problems = check_shipped(path, build_document())
        assert any("refresh-as-access" in p for p in problems), problems

    def test_check_catches_a_dropped_vector(self, tmp_path):
        doc = build_document()
        tampered = json.loads(json.dumps(doc, ensure_ascii=False))
        tampered["vectors"] = [v for v in tampered["vectors"] if v["vector_id"] != "expired-access"]
        path = tmp_path / "jwt_golden.json"
        path.write_text(json.dumps(tampered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

        problems = check_shipped(path, build_document())
        assert any("expired-access" in p for p in problems), problems

    def test_check_catches_a_missing_file(self, tmp_path):
        problems = check_shipped(tmp_path / "nope.json", build_document())
        assert problems and "不存在" in problems[0]

    def test_exported_claims_are_json_serialisable(self, doc):
        """exp 必须是数字（python-jose 会把 datetime 转成 int 时间戳），
        否则 Go 侧解出来是字符串，两侧对同一个 claim 的类型理解就不同了。"""
        for v in doc["vectors"]:
            assert isinstance(v["claims"]["exp"], int), v["vector_id"]
            json.dumps(v["claims"])


def test_base64url_decode_of_signature_is_32_bytes(doc):
    """签名段解出来必须是 32 字节（SHA256 输出）——顺便把"43 字符"这个前提钉住，
    上面那组填充位用例依赖它。"""
    signature = vector(doc, "access-user")["token"].split(".")[2]
    assert len(signature) == 43
    padding = "=" * (-len(signature) % 4)
    assert len(base64.urlsafe_b64decode(signature + padding)) == 32
