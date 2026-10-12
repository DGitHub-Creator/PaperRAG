"""PBKDF2 golden vectors 导出（X5「旧密码不被锁死」的输入件）。

背景（`00` §密码哈希、`04` §风险表）：库里现在存的是

    pbkdf2_sha256$<rounds>$<标准 base64 盐>$<标准 base64 摘要>

Go 要接管 `users`，必须能验**同一串**旧哈希。最容易出事的是编码细节：标准 base64
与 urlsafe base64、盐长度、迭代数、口令的 UTF-8 编码、`$` 分段数。所以 X5 要求先有
golden vectors，Go 逐条通过之后才允许接管（`09` P0-6 的规模/风险行就是这么写的）。

**导出不含口令明文，也不含真库的 password_hash。** 这条口径来自 `07` §兼容面表
（"导出物不含密码与盐明文"）。要说明白它**不是**保密措施：口令由 `vector_id` 按下述
公开规则推导，拿到文件就能重算，所以它防的是两件别的事：

  1. **真实凭据永远不进仓库。** 向量一律是合成口令，仓库里不存在任何一份"某个人能用"的
     口令-哈希配对；一旦开了"把口令写进向量文件"的先例，下一步就是把真人导出来。
  2. **文件的形状与将来是否会变。** Go 侧读的是 `vector_id + hash + expect_verify`，
     口令从哪来由 `password_rule` 决定；规则写在文件里而不是只写在本脚本里，
     两边就不会各说各话。

         password = "ResearchPilot golden vector " + vector_id      # UTF-8，逐字节

     `TestVerifyLegacyHash` 必须用同一条规则重建口令再调它的验证函数。

真库那侧：`--from-db` 从 `users.password_hash` **只取形状**（迭代数分布、盐长度分布、
摘要长度、是否还残留 bcrypt 族），用它回答"合成向量有没有覆盖生产实际存在过的格式"，
不把任何一份摘要带出来——提交的仓库里放全库口令摘要，等于给每个拿到仓库的人一台
离线爆破机，而这批摘要对本卡的目的（比 Go 与 Python 的一致性）毫无增量。

向量集不是随机生成的：每条都对应一个会被踩到的差异面（见 `VECTORS` 里每条的 `note`），
并且每条都要过一遍 `backend.core.auth.verify_password`——**Python 是裁判**，
Go 只需要和裁判一致。这样 golden vectors 本身是可证伪的：裁判不过，导出就失败。

用法：
    uv run python scripts/export_pbkdf2_golden.py            # 写 contracts/pbkdf2_golden.json
    uv run python scripts/export_pbkdf2_golden.py --check    # 只比对，漂移则 exit 1（门禁用）
    uv run python scripts/export_pbkdf2_golden.py --from-db  # 额外从真库取形状（需 DATABASE_URL，只读）
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contracts" / "pbkdf2_golden.json"
SCHEMA_VERSION = 1
ALGORITHM = "pbkdf2_sha256"
PASSWORD_RULE = 'password = "ResearchPilot golden vector " + vector_id, encoded as UTF-8'
PASSWORD_PREFIX = "ResearchPilot golden vector "

# 每条向量的形状。rounds 用 40000 这个量级：够覆盖"迭代数参与格式"这件事，
# 又不至于让 Go/Python 两边的测试各花几十秒（生产是 310000，见最后一个向量）。
# salt/digest 的字节长度、b64 变体、分段数是刻意变化的维度，note 写清了每条在钉什么。
VECTORS: list[dict[str, Any]] = [
    {"vector_id": "baseline", "rounds": 40000, "salt_bytes": 16, "b64": "standard",
     "note": "今天生产写入的形状：16 字节盐 + 标准 base64，Python 与 Go 都必须接受"},
    {"vector_id": "legacy-260000", "rounds": 260000, "salt_bytes": 16, "b64": "standard",
     "note": "旧迭代数（260000 曾在测试里出现过），格式解析必须与迭代数无关"},
    {"vector_id": "short-salt", "rounds": 40000, "salt_bytes": 8, "b64": "standard",
     "note": "盐长度不是常量：按 16 硬编码的实现会在这里露出来"},
    {"vector_id": "long-salt", "rounds": 40000, "salt_bytes": 32, "b64": "standard",
     "note": "同上，另一侧"},
    {"vector_id": "urlsafe-salt", "rounds": 40000, "salt_bytes": 16, "b64": "urlsafe",
     "digest_bytes": 32, "force_variant": True, "expect_verify": False,
     "note": "04 §风险表点名的第一条：标准 vs urlsafe。固定 salt 字节含 0xFB 0xFF，保证标准编码里的 "
             "`+/` 在 urlsafe 里变成 `-_`。实测 Python 自己**验不过**这条（b64decode 要么抛异常要么把 "
             "`-_` 当非法字符丢掉），所以库里不可能存在这种串——它是负向向量：Go 若宽容到把 urlsafe "
             "也接了，就会在这里返回 true，与裁判不一致，而那正是「旧密码被误接受」的方向"},
    {"vector_id": "中文🔒", "rounds": 40000, "salt_bytes": 16, "b64": "standard",
     "note": "口令必须按 UTF-8 字节进 KDF。这条故意把 vector_id 本身写成非 ASCII——"
             "按上面的规则重建口令时，Go 拿到的就是含多字节字符的串，"
             "按 Latin-1 展开或先做 NFC 归一化的实现会在这里与裁判分道"},
    {"vector_id": "production-rounds", "rounds": 310000, "salt_bytes": 16, "b64": "standard",
     "note": "生产真实迭代数（core/config/auth.py 的默认值），只 1 条，避免测试变慢"},
    # 负向：Go 不能"任何串都返回 true"。这三条 expect_verify=false，验的是拒绝路径。
    {"vector_id": "wrong-digest", "rounds": 40000, "salt_bytes": 16, "b64": "standard",
     "corrupt": "digest", "expect_verify": False,
     "note": "摘要改一个 bit 必须验不过"},
    {"vector_id": "truncated-digest", "rounds": 40000, "salt_bytes": 16, "b64": "standard",
     "corrupt": "truncate", "expect_verify": False,
     "note": "摘要长度不足（截到 16 字节）必须验不过，不能左对齐补零后放过"},
    {"vector_id": "malformed-segments", "rounds": 40000, "salt_bytes": 16, "b64": "standard",
     "corrupt": "segments", "expect_verify": False,
     "note": "少一段的字符串不是本格式，必须拒绝而不是抛异常"},
]

URLSAFE_SALT = bytes([0xFB, 0xFF] * 8)  # 16 字节：标准 b64 里有 +/，urlsafe 里变成 -_


def _b64(data: bytes, variant: str) -> str:
    if variant == "urlsafe":
        return base64.urlsafe_b64encode(data).decode("ascii")
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str, variant: str) -> bytes:
    data = text.encode("ascii")
    return base64.urlsafe_b64decode(data) if variant == "urlsafe" else base64.b64decode(data)


def _salt(spec: dict[str, Any]) -> bytes:
    if spec.get("force_variant"):
        return URLSAFE_SALT
    # 由 vector_id 派生：导出可重复，且盐不来自随机源，CI 上两次生成必须逐字相同。
    return hashlib.sha256(f"salt|{spec['vector_id']}".encode("utf-8")).digest()[: spec["salt_bytes"]]


def _password(spec: dict[str, Any]) -> str:
    """按 `password_rule` 重建口令——这也是 Go 侧唯一的重建途径，两条实现必须逐字同构。"""
    return PASSWORD_PREFIX + spec["vector_id"]


def build_hash(spec: dict[str, Any]) -> str:
    """按 `backend/core/auth.py` 的存储格式算出哈希串（负向向量在这里破坏形状）。

    KDF 参数与 Python 侧逐字一致：SHA256、UTF-8 口令、bytes 盐、rounds、dklen=32。
    裁判仍然是 `verify_password`——本函数错了它会把整批导出顶回去。
    """
    digest = hashlib.pbkdf2_hmac("sha256", _password(spec).encode("utf-8"), _salt(spec), spec["rounds"])
    digest_len = spec.get("digest_bytes", 32)
    digest = digest[:digest_len]
    salt_b64 = _b64(_salt(spec), spec["b64"])
    digest_b64 = _b64(digest, spec["b64"])

    corrupt = spec.get("corrupt")
    if corrupt == "digest":
        raw = bytearray(_unb64(digest_b64, spec["b64"]))
        raw[0] ^= 0x01
        digest_b64 = _b64(bytes(raw), spec["b64"])
    elif corrupt == "truncate":
        digest_b64 = _b64(_unb64(digest_b64, spec["b64"])[:16], spec["b64"])
    elif corrupt == "segments":
        return f"{ALGORITHM}${spec['rounds']}${salt_b64}"
    return f"{ALGORITHM}${spec['rounds']}${salt_b64}${digest_b64}"


def build_document() -> dict[str, Any]:
    """生成 vectors 文件内容；每条都要过 Python 的 `verify_password`。"""
    sys.path.insert(0, str(ROOT))
    from backend.core.auth import verify_password  # 裁判：Go 要复刻的是它的行为，不是我的重写

    vectors = []
    rejected: list[str] = []
    for spec in VECTORS:
        password = _password(spec)
        expected = spec.get("expect_verify", True)
        hash_str = build_hash(spec)
        # verify_password 在"格式不认识"时也返回 False，所以 False 要分两种：
        # 真验不过（口令对但摘要错）与形状不认。malformed 那条本来就该落到后者。
        actual = verify_password(password, hash_str)
        if actual is not expected:
            rejected.append(f"{spec['vector_id']}: 期望 verify_password={expected}，实得 {actual}")
        parts = hash_str.split("$")
        digest_bytes = len(_unb64(parts[3], spec["b64"])) if len(parts) == 4 else 0
        vectors.append(
            {
                "vector_id": spec["vector_id"],
                "algorithm": ALGORITHM,
                "rounds": spec["rounds"],
                "salt_bytes": len(_salt(spec)),
                "digest_bytes": digest_bytes,
                "b64_variant": spec["b64"],
                "expect_verify": expected,
                "hash": hash_str,
                "note": spec["note"],
            }
        )
    if rejected:
        raise SystemExit("[pbkdf2] 生成器与 Python 裁判不一致，拒绝导出：\n  " + "\n  ".join(rejected))

    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "password_rule": PASSWORD_RULE,
        "warning": "本文件的 hash 字段是合成口令的摘要，不是任何真实用户的凭据；"
        "真库的 password_hash 有意不导出（可离线爆破），只以 live_shape 的形式记录形状。",
        "vectors": vectors,
    }


LIVE_SHAPE_SQL = """
SELECT password_hash FROM users
"""


def live_shape(database_url: str) -> dict[str, Any]:
    """只读地统计生产里**实际存在**的哈希形状。不取用户名、不取口令、不把摘要写进文件。"""
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    families: dict[str, int] = {}
    rounds: dict[str, int] = {}
    salt_lengths: dict[str, int] = {}
    digest_lengths: dict[str, int] = {}
    total = 0
    with engine.connect() as conn:
        for (hash_str,) in conn.execute(text(LIVE_SHAPE_SQL)):
            total += 1
            head = hash_str.split("$", 1)[0] if hash_str else "empty"
            if hash_str.startswith("pbkdf2_sha256$"):
                parts = hash_str.split("$")
                families["pbkdf2_sha256"] = families.get("pbkdf2_sha256", 0) + 1
                if len(parts) == 4:
                    rounds[parts[1]] = rounds.get(parts[1], 0) + 1
                    try:
                        salt_lengths[str(len(base64.b64decode(parts[2])))] = (
                            salt_lengths.get(str(len(base64.b64decode(parts[2]))), 0) + 1
                        )
                        digest_lengths[str(len(base64.b64decode(parts[3])))] = (
                            digest_lengths.get(str(len(base64.b64decode(parts[3]))), 0) + 1
                        )
                    except Exception:
                        families["undecodable_b64"] = families.get("undecodable_b64", 0) + 1
                else:
                    families["wrong_segment_count"] = families.get("wrong_segment_count", 0) + 1
            elif head in {"2b", "2a", "2y"} or hash_str.startswith("$2"):
                families["bcrypt"] = families.get("bcrypt", 0) + 1
            else:
                families[head[:24] or "empty"] = families.get(head[:24] or "empty", 0) + 1

    return {
        "source": "users.password_hash（只读统计，未导出任何摘要）",
        "rows": total,
        "families": families,
        "rounds": rounds,
        "salt_bytes": salt_lengths,
        "digest_bytes": digest_lengths,
    }


def coverage_check(doc: dict[str, Any], shape: dict[str, Any] | None) -> list[str]:
    """合成向量集合是否覆盖了库里真实出现过的形状。覆盖不到就报出来，别假装绿。"""
    problems: list[str] = []
    rounds_covered = {v["rounds"] for v in doc["vectors"]}
    salts_covered = {v["salt_bytes"] for v in doc["vectors"]}
    if shape:
        for r, n in (shape["rounds"] or {}).items():
            if int(r) not in rounds_covered:
                problems.append(f"库里有 {n} 行用 rounds={r}，golden vectors 没覆盖")
        for s, n in (shape["salt_bytes"] or {}).items():
            if int(s) not in salts_covered:
                problems.append(f"库里有 {n} 行盐长 {s} 字节，golden vectors 没覆盖")
        if (shape["families"] or {}).get("bcrypt"):
            problems.append(
                f"库里还有 {shape['families']['bcrypt']} 行 bcrypt 族哈希——Go 若不支持 bcrypt，"
                "接管 users 时这些人会被锁死，必须在 P0-6 里显式处置（强制改密或 Go 侧支持）"
            )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="PBKDF2 golden vectors 导出")
    ap.add_argument("--check", action="store_true", help="只与已提交的文件比对，不写盘")
    ap.add_argument("--from-db", action="store_true", help="附带真库形状统计（需 DATABASE_URL）")
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    doc = build_document()

    if args.from_db:
        url = args.database_url or os.environ.get("DATABASE_URL")
        if not url:
            print("[pbkdf2] --from-db 需要 DATABASE_URL；没有真库时请只跑默认模式，"
                  "形状统计缺失会让 X5 的覆盖面判不出来")
            return 2
        doc["live_shape"] = live_shape(url)
        for p in coverage_check(doc, doc["live_shape"]):
            print(f"[pbkdf2] 覆盖缺口：{p}")
    else:
        problems = coverage_check(doc, None)
        if problems:
            for p in problems:
                print(f"[pbkdf2] 覆盖缺口：{p}")
            return 1

    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    out = Path(args.out)
    if args.check:
        if not out.is_file():
            print(f"[pbkdf2] {out} 不存在，--check 无从比对")
            return 1
        if out.read_text(encoding="utf-8") != text:
            print(f"[pbkdf2] {out} 与生成器不一致：改过 VECTORS 就得重新导出并提交")
            return 1
        print(f"[pbkdf2] --check 通过：{out} 与生成器一致（{len(doc['vectors'])} 条向量）")
        return 0

    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"[pbkdf2] 已写出 {out}（{len(doc['vectors'])} 条向量，"
          f"正向 {len([v for v in doc['vectors'] if v['expect_verify']])} / "
          f"负向 {len([v for v in doc['vectors'] if not v['expect_verify']])}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
