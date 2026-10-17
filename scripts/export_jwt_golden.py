"""JWT golden tokens 导出（X4「跨语言互验 token」的**令牌半侧**输入件）。

背景（`07` §兼容面表第 115 行）：JWT 这一行原先是"未实现（P0-6 / X4）"。X4 要的是
"Python 签发的 token 能被 Go 校验，Go 签发的能被 Python 校验"。本脚本产出前半段所需的
输入件：**Python 签发的 token 清单 + 每条的期望结论**，Go 侧 `internal/auth/jwt_test.go`
逐条吃它。

与 `export_pbkdf2_golden.py` 同构的三条规矩：

  1. **Python 是裁判。** 每条的 `expect_accept` 都等于生产函数
     `backend/core/auth.py:get_user_from_bearer_token` 的返回值（用桩 db 跑真函数，
     不是重写一份判断逻辑），裁判结论与标注不一致就拒绝导出。
  2. **不含真凭据。** `secret` 是合成的、写死在本文件里的公开值，不是任何环境的
     `JWT_SECRET_KEY`；用户名也是合成的。生产密钥只经环境变量，永不入仓库。
  3. **覆盖面不是自封的。** `07` 点名的三件事（`type` 语义、过期、错误 secret）各有向量，
     另外补了历史令牌（缺 `type`）、缺 `sub`、用户已不在库里、签名被改四种。

⚠️ **本文件不能像 pbkdf2_golden.json 那样逐字节重建**，这是两者的本质差别，必须说清：
token 的 `exp` 是"签发时刻 + 有效期"，所以每次导出都不一样。处理办法是两条：
  - 正向向量的有效期钉成 **10 年**（`POSITIVE_EXPIRE_MINUTES`），文件在 2036 年前都有效；
  - `--check` 因此改成**语义校验**而不是字节比对：把文件里每条 token 重新交给生产裁判，
    结论必须仍等于文件记的 `expect_accept`，且 token 里的 claims 必须与文件记的一致。
    这比字节比对更强——它能抓出"文件被手改过""正向 token 已经过期""裁判语义变了"三件事。
    正向 token 真过期时 `--check` 会红，那时重新导出并提交即可。

用法：
    uv run python scripts/export_jwt_golden.py            # 写 contracts/jwt_golden.json
    uv run python scripts/export_jwt_golden.py --check    # 重判已提交的文件，漂移则 exit 1（门禁用）
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contracts" / "jwt_golden.json"
SCHEMA_VERSION = 1
ALGORITHM = "HS256"

# 合成密钥。写进文件是**故意的**：它是公开的、只用于本清单，拿到它只能验通一批
# 指向不存在用户的令牌。真密钥永不入仓库（AGENTS.md §7）。
SECRET = "ResearchPilot golden jwt secret public-only"
WRONG_SECRET = SECRET + "-wrong"

# 桩库里唯一的用户。"token 有效但用户已不在库里"那条向量靠它判出来。
KNOWN_USER = "golden-user"
UNKNOWN_USER = "not-in-the-stub-db"

# 正向向量的有效期（分钟）。10 年：够长，文件不会在下一轮开发里过期；
# 又不是"永不过期"，`--check` 仍能证明过期这条轴真的在起作用。
POSITIVE_EXPIRE_MINUTES = 5256000

# 文件里的 claims 一律按这个顺序记录，导出可重复（Python 3.7+ 的 dict 保序，json.dumps 不排序）。
DIVERGENCES = [
    {
        "axis": "缺 exp 的令牌",
        "python": "PyJWT 只在 exp 存在时校验，所以缺 exp 的令牌会被**接受**"
        "（get_user_from_bearer_token 也不额外要求 exp）",
        "go": "一律要求 exp（jwt.WithExpirationRequired），缺 exp 即拒绝",
        "why_not_in_vectors": "两侧结论相反的向量放进同一份清单，会让「逐条一致」这个判据自相矛盾。"
        "生产 create_access_token / create_refresh_token **总会**写 exp，所以这条分歧碰不到真实令牌；"
        "方向是 Go 更严（拒绝而不是误接受）。Go 侧由 jwt_test.go 单独钉住。",
    },
    {
        "axis": "alg 白名单",
        "python": "jwt.decode(..., algorithms=[JWT_ALGORITHM])，白名单来自配置",
        "go": "白名单硬编码为 HS256 一项；JWT_ALGORITHM 配成别的值时 ValidateAuth 拒绝启动",
        "why_not_in_vectors": "两侧都拒绝 alg 混淆，只是 Go 更严（连配置口子都不给）。"
        "Go 侧由 jwt_test.go 用 alg=none 与 alg=HS512 两条自造令牌钉住。",
    },
]


# 负向量由哪一层拒绝。"token" = 生产函数四项校验的前三项（签名/过期、sub、type），
# Go 侧对应 internal/auth.ParseAccessToken；"database" = 第四项（用户是否仍在库里），
# Go 侧对应 service 层的回库查询。两侧的单测各自按这个字段认领自己要断言的向量。
REJECTED_BY = {
    "refresh-as-access": "token",
    "expired-access": "token",
    "wrong-secret": "token",
    "missing-sub": "token",
    "tampered-signature": "token",
    "unknown-user": "database",
}


class _StubUser:
    """桩用户：生产函数只读 `.username` 与 `.role`（含那行 debug 日志）。"""

    def __init__(self, username: str, role: str) -> None:
        self.username = username
        self.role = role
        self.id = 1


class _StubQuery:
    def __init__(self, users: dict[str, _StubUser]) -> None:
        self._users = users
        self._username: str | None = None

    def filter(self, criterion: Any) -> _StubQuery:
        # criterion 是 SQLAlchemy 的 `User.username == <值>`；右值是 BindParameter。
        # 这里读的是 SQLAlchemy 内部属性，属于测试桩的既定代价：它一旦变形，
        # 用例会**报错**而不是静默通过（静默通过才是真危险）。
        self._username = criterion.right.value
        return self

    def first(self) -> _StubUser | None:
        return self._users.get(self._username or "")


class _StubDB:
    """只认一个用户的桩 db，形状对得上 `db.query(User).filter(...).first()`。"""

    def __init__(self, users: dict[str, _StubUser] | None = None) -> None:
        self._users = users if users is not None else {KNOWN_USER: _StubUser(KNOWN_USER, "user")}

    def query(self, model: Any) -> _StubQuery:
        return _StubQuery(self._users)


@contextmanager
def _production_auth(secret: str = SECRET, expire_minutes: int = POSITIVE_EXPIRE_MINUTES):
    """把生产模块的配置换成合成值，退出时**逐字还原**。

    换的是 `backend.core.auth` 自己命名空间里的那几个名字（它是 `from ... import` 进来的），
    所以只影响本进程内的这个模块，不动 `backend.core.config`。
    """
    from backend.core import auth as production

    saved = (
        production.JWT_SECRET_KEY,
        production.JWT_ALGORITHM,
        production.JWT_EXPIRE_MINUTES,
        production.JWT_REFRESH_EXPIRE_DAYS,
    )
    production.JWT_SECRET_KEY = secret
    production.JWT_ALGORITHM = ALGORITHM
    production.JWT_EXPIRE_MINUTES = expire_minutes
    # refresh 的有效期也钉长，理由同 POSITIVE_EXPIRE_MINUTES
    production.JWT_REFRESH_EXPIRE_DAYS = 3650
    try:
        yield production
    finally:
        (
            production.JWT_SECRET_KEY,
            production.JWT_ALGORITHM,
            production.JWT_EXPIRE_MINUTES,
            production.JWT_REFRESH_EXPIRE_DAYS,
        ) = saved


def judge(token: str) -> bool:
    """用**生产函数**判这条 token 能不能当访问凭证。

    桩库里只有 KNOWN_USER，所以"用户已不在库里"这条轴也走的是真代码路径
    （get_user_from_bearer_token 的第 4 项校验），不是我另写的一份判断。
    """
    with _production_auth() as production:
        return production.get_user_from_bearer_token(token, _StubDB()) is not None


def _claims(token: str) -> dict[str, Any]:
    """不验签地取出 claims，只为把它们记进文件（Go 侧要逐字段对上）。"""
    import jwt

    payload = jwt.decode(token, options={"verify_signature": False})
    return {
        "sub": payload.get("sub"),
        "role": payload.get("role"),
        "type": payload.get("type"),
        "exp": payload.get("exp"),
    }


def _issue(kind: str, username: str, role: str, secret: str = SECRET,
           expire_minutes: int = POSITIVE_EXPIRE_MINUTES) -> str:
    with _production_auth(secret=secret, expire_minutes=expire_minutes) as production:
        if kind == "access":
            return production.create_access_token(username=username, role=role)
        if kind == "refresh":
            return production.create_refresh_token(username=username, role=role)
    raise ValueError(f"未知的令牌种类: {kind}")


def _raw_encode(payload: dict[str, Any], secret: str = SECRET) -> str:
    """直接调 PyJWT 签发。只用于生产函数**发不出来的形状**（缺 type、缺 sub）——
    这两条恰恰是历史令牌与攻击面，必须有向量，但不能假装是生产函数产的：
    `produced_by` 字段如实写 raw_encode。
    """
    import jwt

    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def _tamper_signature(token: str) -> str:
    """把签名段的**第一个**字符换成另一个合法的 base64url 字符。

    两处刻意，都是本机实跑踩出来的：

      1. 保持字符集合法：要测的是"签名对不上"，不是"base64 解不开"——后者会被解析层挡掉，
         断言就落错了地方（与 pbkdf2 那份 truncated-digest 的用意相同）。
      2. 动**首字符**而不是末字符：HS256 的签名是 32 字节 → base64url 43 字符，
         末字符只承载 4 个有效位，低 2 位是填充位。把末字符按字母表挪一位
         （例如 `A`→`B`，000000→000001）改的正好是填充位，**解出来的签名字节一个都没变**，
         PyJWT 于是照常接受。第一版就是这么写的，被生产裁判顶了回来
         （"期望 False，实得 True"）——这条向量当时测的是"我会不会改错地方"，不是"签名校验有没有效"。
    """
    head, payload, signature = token.rsplit(".", 2)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    first = signature[0]
    replacement = alphabet[(alphabet.index(first) + 1) % len(alphabet)] if first in alphabet else "A"
    return f"{head}.{payload}.{replacement}{signature[1:]}"


def build_vectors() -> list[dict[str, Any]]:
    """造出向量集。每条都由生产裁判判过，标注与裁判不一致就抛出去（不写文件）。

    `rejected_by` 标的是**哪一层**拒的，这个字段不是装饰：生产函数
    `get_user_from_bearer_token` 的四项校验里，前三项（签名/过期、sub、type）是令牌级的，
    第四项（用户是否仍在库里）要回库。Go 侧对应地分成两处实现——`ParseAccessToken` 只管
    前三项，回库那步在 service 层。没有这个字段，Go 的单测就无从知道某条负向量
    该在哪一层断言，只能笼统地"反正被拒了"，那样令牌层与库层的分工就没人守着。
    """
    legacy_payload = {
        "sub": KNOWN_USER,
        "role": "user",
        # 故意不带 type：历史 access token 就是这个形状，生产代码把"缺失"等同 "access"
        "exp": datetime.now(UTC) + timedelta(minutes=POSITIVE_EXPIRE_MINUTES),
    }
    missing_sub_payload = {
        "role": "user",
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=POSITIVE_EXPIRE_MINUTES),
    }

    access_user = _issue("access", KNOWN_USER, "user")
    specs: list[dict[str, Any]] = [
        {
            "vector_id": "access-user",
            "token": access_user,
            "produced_by": "create_access_token",
            "signed_with": "secret",
            "expire_minutes": POSITIVE_EXPIRE_MINUTES,
            "expect_accept": True,
            "note": "今天生产签发的形状：sub/role/type=access/exp 四项齐全，Python 与 Go 都必须接受",
        },
        {
            "vector_id": "access-admin",
            "token": _issue("access", KNOWN_USER, "admin"),
            "produced_by": "create_access_token",
            "signed_with": "secret",
            "expire_minutes": POSITIVE_EXPIRE_MINUTES,
            "expect_accept": True,
            "note": "令牌级校验与 role 无关。⚠️ 但 role **不得**从令牌采信：生产代码一律回库取角色"
            "（避免降级/改名后旧令牌继续持有旧权限），Go 侧 service 层同样回库，jwt_test.go 钉这条",
        },
        {
            "vector_id": "refresh-as-access",
            "token": _issue("refresh", KNOWN_USER, "user"),
            "produced_by": "create_refresh_token",
            "signed_with": "secret",
            "expire_minutes": POSITIVE_EXPIRE_MINUTES,
            "expect_accept": False,
            "note": "07 点名的「type 语义」：refresh 不能当访问凭证用。签名与 exp 都合法，"
            "唯一的差别是 type=refresh——只验签名的实现会在这里放过",
        },
        {
            "vector_id": "no-type-legacy",
            "token": _raw_encode(legacy_payload),
            "produced_by": "raw_encode",
            "signed_with": "secret",
            "expire_minutes": POSITIVE_EXPIRE_MINUTES,
            "expect_accept": True,
            "note": "历史令牌不带 type，生产代码把「缺失」等同「access」。这条是**正向**的："
            "Go 若严格要求 type 存在，这批老令牌会全部失效。生产函数发不出这个形状，故 produced_by=raw_encode",
        },
        {
            "vector_id": "expired-access",
            "token": _issue("access", KNOWN_USER, "user", expire_minutes=-1),
            "produced_by": "create_access_token",
            "signed_with": "secret",
            "expire_minutes": -1,
            "expect_accept": False,
            "note": "07 点名的「过期」：签名完全合法，只是 exp 已过。有效期用 -1 分钟，"
            "由生产函数签发（不是手改 exp），所以这条同时证明了裁判真的在校验 exp",
        },
        {
            "vector_id": "wrong-secret",
            "token": _issue("access", KNOWN_USER, "user", secret=WRONG_SECRET),
            "produced_by": "create_access_token",
            "signed_with": "secret-wrong",
            "expire_minutes": POSITIVE_EXPIRE_MINUTES,
            "expect_accept": False,
            "note": "07 点名的「错误 secret」：形状、type、exp 全对，只有签名密钥不同。"
            "校验时一律用文件里的 secret，本条必然验不过",
        },
        {
            "vector_id": "missing-sub",
            "token": _raw_encode(missing_sub_payload),
            "produced_by": "raw_encode",
            "signed_with": "secret",
            "expire_minutes": POSITIVE_EXPIRE_MINUTES,
            "expect_accept": False,
            "note": "签名合法但缺 sub：生产代码显式拒绝（没有用户名就无从回库取角色）",
        },
        {
            "vector_id": "unknown-user",
            "token": _issue("access", UNKNOWN_USER, "user"),
            "produced_by": "create_access_token",
            "signed_with": "secret",
            "expire_minutes": POSITIVE_EXPIRE_MINUTES,
            "expect_accept": False,
            "note": "令牌合法但用户已不在库里（注销/改名）。这一条走的是生产函数的**第 4 项**校验"
            "（回库查用户），所以它同时钉住了「Go 不能只验签名就放行」——me 路径必须回库",
        },
        {
            "vector_id": "tampered-signature",
            "token": _tamper_signature(access_user),
            "produced_by": "create_access_token+篡改签名段首字符",
            "signed_with": "secret",
            "expire_minutes": POSITIVE_EXPIRE_MINUTES,
            "expect_accept": False,
            "note": "claims 与 access-user 逐字相同，只有签名首字符被换成另一个合法 base64url 字符。"
            "两处刻意：保持字符集合法（测「签名对不上」而不是「base64 解不开」）、动首字符而不是末字符"
            "（末字符低 2 位是填充位，挪一位解出来的签名字节不变，PyJWT 会照常接受——"
            "第一版就这么写错了，被生产裁判顶回来）",
        },
    ]

    rejected: list[str] = []
    for spec in specs:
        actual = judge(spec["token"])
        if actual is not spec["expect_accept"]:
            rejected.append(
                f"{spec['vector_id']}: 期望生产裁判={spec['expect_accept']}，实得 {actual}"
            )
        spec["claims"] = _claims(spec["token"])
        # 负向量必须说明是哪一层拒的；漏了映射就 KeyError（响一声，别静默填 None）
        spec["rejected_by"] = None if spec["expect_accept"] else REJECTED_BY[spec["vector_id"]]
    if rejected:
        raise SystemExit("[jwt] 生产裁判与标注不一致，拒绝导出：\n  " + "\n  ".join(rejected))
    return specs


def build_document() -> dict[str, Any]:
    vectors = build_vectors()
    accepted = [v for v in vectors if v["expect_accept"]]
    if not accepted or len(accepted) == len(vectors):
        raise SystemExit(
            f"[jwt] 向量集退化：{len(vectors)} 条里正向 {len(accepted)} 条，两侧都不能为 0"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "secret": SECRET,
        "secret_rule": f'secret = "{SECRET}"（合成值，公开写在文件里）；'
        f'signed_with="secret-wrong" 的那条用 "{WRONG_SECRET}" 签发，校验时一律用 secret',
        "warning": "本文件的 secret 与用户名都是合成的，不是任何环境的凭据；"
        "生产 JWT_SECRET_KEY 只经环境变量，永不入仓库（AGENTS.md §7）。",
        "judge": "backend.core.auth.get_user_from_bearer_token（生产函数本体，用只认 "
        f'"{KNOWN_USER}" 一个用户的桩 db 跑），expect_accept 就是它是否返回非 None。'
        "四项校验（签名/过期、sub 存在、type 语义、用户仍在库里）因此都在判据里。",
        "reproducibility": "token 的 exp = 签发时刻 + expire_minutes，所以**本文件不能逐字节重建**"
        "（与 pbkdf2_golden.json 不同，那份的盐由 vector_id 派生，可逐字重建）。"
        "--check 因此是语义校验：把每条已提交的 token 重新交给生产裁判，"
        "结论与 claims 都必须仍与文件一致。正向向量的有效期钉成 10 年，到期前不必重导。",
        "known_user": KNOWN_USER,
        "unknown_user": UNKNOWN_USER,
        "vectors": vectors,
        "divergences": DIVERGENCES,
    }


def check_shipped(path: Path, doc: dict[str, Any]) -> list[str]:
    """语义校验已提交的文件：不比对字节，而是**重判每条 token**。

    这样能抓出三件字节比对抓不到或抓不准的事：文件被手改过（claims 对不上）、
    正向 token 已经过期（裁判结论翻转）、生产裁判的语义变了（结论翻转）。
    """
    problems: list[str] = []
    if not path.is_file():
        return [f"{path} 不存在，--check 无从比对"]
    try:
        shipped = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path} 不是合法 JSON: {exc}"]

    shipped_vectors = {v["vector_id"]: v for v in shipped.get("vectors", [])}
    fresh_vectors = {v["vector_id"]: v for v in doc["vectors"]}

    for vid in sorted(set(shipped_vectors) ^ set(fresh_vectors)):
        side = "只在文件里" if vid in shipped_vectors else "只在生成器里"
        problems.append(f"向量 {vid} {side}：改过 VECTORS 就得重新导出并提交")

    for vid, fresh in sorted(fresh_vectors.items()):
        old = shipped_vectors.get(vid)
        if not old:
            continue
        token = old.get("token", "")
        # ① 已提交的 token 现在仍被生产裁判判成文件里记的结论吗？
        if judge(token) is not old.get("expect_accept"):
            problems.append(
                f"向量 {vid}：生产裁判对已提交 token 的结论与文件记的 "
                f"{old.get('expect_accept')} 不一致（正向 token 过期了？文件被手改了？）"
            )
        # ② token 里的 claims 与文件记的一致吗？（防"记录是旧的、token 是新的"）
        actual_claims = _claims(token) if token.count(".") == 2 else None
        if actual_claims != old.get("claims"):
            problems.append(f"向量 {vid}：文件记的 claims 与 token 里的不一致")
        # ③ 结构性字段有没有被改动
        for field in ("expect_accept", "rejected_by", "signed_with", "produced_by", "expire_minutes"):
            if old.get(field) != fresh.get(field):
                problems.append(f"向量 {vid}：{field} 文件记 {old.get(field)!r}、生成器是 {fresh.get(field)!r}")
        # ④ 重新签发一条同形状的，裁判结论必须相同（防生成器与文件同时漂移到错的一侧）
        if judge(fresh["token"]) is not fresh["expect_accept"]:
            problems.append(f"向量 {vid}：生成器新签的 token 与标注不一致")

    for field in ("algorithm", "secret", "known_user", "unknown_user"):
        if shipped.get(field) != doc.get(field):
            problems.append(f"顶层 {field}：文件是 {shipped.get(field)!r}、生成器是 {doc.get(field)!r}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="JWT golden tokens 导出")
    ap.add_argument("--check", action="store_true", help="重判已提交的文件，不写盘（门禁用）")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    doc = build_document()
    out = Path(args.out)

    if args.check:
        problems = check_shipped(out, doc)
        if problems:
            print("[jwt] --check 未通过：")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(f"[jwt] --check 通过：{out} 的 {len(doc['vectors'])} 条 token 仍被生产裁判判成文件记的结论")
        return 0

    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")
    positive = len([v for v in doc["vectors"] if v["expect_accept"]])
    print(f"[jwt] 已写出 {out}（{len(doc['vectors'])} 条向量，正向 {positive} / "
          f"负向 {len(doc['vectors']) - positive}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
