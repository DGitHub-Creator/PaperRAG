package auth

import (
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// goldenPath 指向仓库里的 PBKDF2 golden vectors（由 scripts/export_pbkdf2_golden.py 产出，
// 每条期望值都经生产裁判 backend/core/auth.py:verify_password 现算）。
// 从包目录 server/internal/auth 回到仓库根是三层。
var goldenPath = filepath.Join("..", "..", "..", "contracts", "pbkdf2_golden.json")

// goldenPasswordPrefix 是文件里 password_rule 的公开规则：
//
//	password = "ResearchPilot golden vector " + vector_id      （UTF-8，逐字节）
//
// 口令**不写在文件里**，两侧各自按这条规则重建。规则变了，两边必须同时改，
// 所以下面有一条用例专门断言文件里的 password_rule 与本常量仍然对得上。
const goldenPasswordPrefix = "ResearchPilot golden vector "

type goldenVector struct {
	VectorID     string `json:"vector_id"`
	Algorithm    string `json:"algorithm"`
	Rounds       int    `json:"rounds"`
	SaltBytes    int    `json:"salt_bytes"`
	DigestBytes  int    `json:"digest_bytes"`
	B64Variant   string `json:"b64_variant"`
	ExpectVerify bool   `json:"expect_verify"`
	Hash         string `json:"hash"`
	Note         string `json:"note"`
}

type goldenDoc struct {
	SchemaVersion int            `json:"schema_version"`
	Algorithm     string         `json:"algorithm"`
	PasswordRule  string         `json:"password_rule"`
	Warning       string         `json:"warning"`
	Vectors       []goldenVector `json:"vectors"`
}

// loadGolden 读并解析向量文件。**读不到就 Fatal，绝不 Skip**：X5 的判定命令是
// `go test -run TestVerifyLegacyHash`，一旦文件缺失时退化成 skip，那条命令会返回 0，
// 退出标准就成了天然假绿（台账 C17 记的正是这类坑）。
func loadGolden(t *testing.T) goldenDoc {
	t.Helper()
	raw, err := os.ReadFile(goldenPath)
	if err != nil {
		t.Fatalf("读不到 golden vectors（%s）: %v —— 先跑 uv run python scripts/export_pbkdf2_golden.py", goldenPath, err)
	}
	var doc goldenDoc
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("golden vectors 不是合法 JSON: %v", err)
	}
	if len(doc.Vectors) == 0 {
		t.Fatal("golden vectors 是空的：0 条向量的「全部通过」没有意义")
	}
	return doc
}

// TestVerifyLegacyHash 是 X5「旧密码不被锁死」的判据本体（09 的 X5 行点名这个测试名）。
// 逐条吃 contracts/pbkdf2_golden.json，与生产裁判的结论比对：正向必须 true，负向必须 false。
// 负向那几条同样重要——只断言正向的实现，"任何串都返回 true"也能过。
func TestVerifyLegacyHash(t *testing.T) {
	doc := loadGolden(t)

	var positive, negative int
	for _, v := range doc.Vectors {
		password := goldenPasswordPrefix + v.VectorID
		got := VerifyPassword(password, v.Hash)
		if got != v.ExpectVerify {
			t.Errorf("向量 %q：期望 verify=%t（%s），实得 %t；hash=%s",
				v.VectorID, v.ExpectVerify, v.Note, got, v.Hash)
			continue
		}
		if v.ExpectVerify {
			positive++
		} else {
			negative++
		}
	}

	// 覆盖面也要断言，否则"文件被删到只剩一条正向"这种退化看不出来。
	if positive == 0 || negative == 0 {
		t.Errorf("向量集退化：正向 %d 条 / 负向 %d 条，两侧都不能为 0", positive, negative)
	}
	t.Logf("golden vectors 全通过：%d 条（正向 %d / 负向 %d）", len(doc.Vectors), positive, negative)
}

// TestGoldenPasswordRuleUnchanged 把"口令重建规则"钉住：文件里的 password_rule 改了而
// 本包的常量没改，TestVerifyLegacyHash 会**全红**（口令对不上），但红的理由看不出是规则漂移。
// 这条用例让漂移直接报出来。
func TestGoldenPasswordRuleUnchanged(t *testing.T) {
	doc := loadGolden(t)
	if !strings.Contains(doc.PasswordRule, goldenPasswordPrefix) {
		t.Fatalf("文件里的 password_rule 与本包的重建规则不一致：\n  文件: %s\n  本包: %q + vector_id",
			doc.PasswordRule, goldenPasswordPrefix)
	}
	if doc.Algorithm != "pbkdf2_sha256" {
		t.Errorf("算法应是 pbkdf2_sha256，文件写的是 %q", doc.Algorithm)
	}
}

// TestGoldenVectorShapesAreActuallyVaried 断言向量集**真的在变**：盐长、迭代数、b64 变体
// 各有多个取值。这是防"导出器坏了但文件还在"的最后一道——形状不再变化时，
// 逐条通过就不再证明实现与迭代数/盐长无关。
func TestGoldenVectorShapesAreActuallyVaried(t *testing.T) {
	doc := loadGolden(t)
	rounds, salts, variants := map[int]bool{}, map[int]bool{}, map[string]bool{}
	for _, v := range doc.Vectors {
		rounds[v.Rounds] = true
		salts[v.SaltBytes] = true
		variants[v.B64Variant] = true

		// 记录值与哈希串自身也要自洽：串里的 rounds 就是记录的那个 rounds。
		parts := strings.SplitN(v.Hash, "$", 4)
		if len(parts) == 4 && parts[1] != strconv.Itoa(v.Rounds) {
			t.Errorf("向量 %q：串里的 rounds=%s 与记录的 %d 不一致", v.VectorID, parts[1], v.Rounds)
		}
		if v.ExpectVerify && len(parts) == 4 {
			// 正向向量的盐必须真能按记录的变体解开，且长度等于记录值。
			dec := base64.StdEncoding.DecodeString
			if v.B64Variant == "urlsafe" {
				dec = base64.URLEncoding.DecodeString
			}
			salt, err := dec(parts[2])
			if err != nil {
				t.Errorf("向量 %q：盐解不开（%s）: %v", v.VectorID, v.B64Variant, err)
			} else if len(salt) != v.SaltBytes {
				t.Errorf("向量 %q：盐长 %d 与记录的 %d 不一致", v.VectorID, len(salt), v.SaltBytes)
			}
		}
	}
	if len(rounds) < 2 {
		t.Errorf("迭代数只有 %d 种取值，向量集没在变（应覆盖 40000/260000/310000 三档）", len(rounds))
	}
	if len(salts) < 2 {
		t.Errorf("盐长只有 %d 种取值，向量集没在变（应覆盖 8/16/32）", len(salts))
	}
	if !variants["standard"] {
		t.Error("缺标准 base64 变体的向量")
	}
	if !variants["urlsafe"] {
		t.Error("缺 urlsafe base64 变体的向量：04 §风险表点名的第一条差异面没被覆盖")
	}
}

// TestVerifyPasswordRejectsWrongPassword 补一条 golden 文件里没有的情形：
// 形状完全正确、只是口令不对。文件里的 wrong-digest 改的是摘要，这条改的是口令。
func TestVerifyPasswordRejectsWrongPassword(t *testing.T) {
	doc := loadGolden(t)
	for _, v := range doc.Vectors {
		if !v.ExpectVerify {
			continue
		}
		if VerifyPassword(goldenPasswordPrefix+v.VectorID+"-tampered", v.Hash) {
			t.Errorf("向量 %q：口令多了一个后缀却验过了", v.VectorID)
		}
		// 空口令一律 false（Python 的 `if not plain_password` 那一步）。
		if VerifyPassword("", v.Hash) {
			t.Errorf("向量 %q：空口令却验过了", v.VectorID)
		}
	}
}

func TestVerifyPasswordDegenerateInputs(t *testing.T) {
	cases := []struct {
		name   string
		plain  string
		stored string
	}{
		{"两边都空", "", ""},
		{"哈希为空", "whatever", ""},
		{"口令为空", "", "pbkdf2_sha256$40000$c2FsdA==$ZGlnZXN0"},
		{"没有前缀", "whatever", "40000$c2FsdA==$ZGlnZXN0"},
		{"只有前缀", "whatever", "pbkdf2_sha256$"},
		{"少一段", "whatever", "pbkdf2_sha256$40000$c2FsdA=="},
		{"rounds 不是数字", "whatever", "pbkdf2_sha256$abc$c2FsdA==$ZGlnZXN0"},
		{"rounds 为零", "whatever", "pbkdf2_sha256$0$c2FsdA==$ZGlnZXN0"},
		{"rounds 为负", "whatever", "pbkdf2_sha256$-1$c2FsdA==$ZGlnZXN0"},
		{"盐不是合法 base64", "whatever", "pbkdf2_sha256$40000$!!!$ZGlnZXN0"},
		{"摘要不是合法 base64", "whatever", "pbkdf2_sha256$40000$c2FsdA==$!!!"},
		{"bcrypt 族", "whatever", "$2b$12$abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH"},
		{"bcrypt 前缀族", "whatever", "$bcrypt$rounds=12$abcdefghijklmnopqrstuvwxyz"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if VerifyPassword(c.plain, c.stored) {
				t.Errorf("VerifyPassword(%q, %q) 应为 false", c.plain, c.stored)
			}
		})
	}
}

// TestHashFamilyDistinguishesBCrypt 钉住"Go 验不了 bcrypt 族"这件事必须**可见**：
// 登录路径靠 HashFamily 把"密码错"与"这行 Go 根本验不了"分开记日志。
// 若两者混成一个 false，接管 users 时那批人会被静默锁死（台账 C20 的处置前提）。
func TestHashFamilyDistinguishesBCrypt(t *testing.T) {
	cases := map[string]Family{
		"pbkdf2_sha256$40000$c2FsdA==$ZGlnZXN0":               FamilyPBKDF2,
		"$2b$12$abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH": FamilyBCrypt,
		"$2a$10$abcdefghijklmnopqrstuvwxyz0123456789ABCDEF":   FamilyBCrypt,
		"$bcrypt$rounds=12$abcdefghijklmnopqrstuvwxyz":        FamilyBCrypt,
		"":                   FamilyUnknown,
		"plaintext-password": FamilyUnknown,
		"sha256$abcdef":      FamilyUnknown,
	}
	for stored, want := range cases {
		if got := HashFamily(stored); got != want {
			t.Errorf("HashFamily(%q) = %v，期望 %v", stored, got, want)
		}
	}
}

// TestHashPasswordProducesPythonCompatibleFormat 断言 Go 写出的串与
// backend/core/auth.py:get_password_hash 的格式逐段同构：Python 侧要能验它
// （切换窗口内 Go 写的行，Python 仍可能读）。跨语言那一半的实跑证据记在 P0-6 的 note 里，
// 这里锁的是可离线机检的部分：四段、前缀、迭代数原样、盐 16 字节、摘要 32 字节、标准 base64。
func TestHashPasswordProducesPythonCompatibleFormat(t *testing.T) {
	const rounds = 40000
	stored, err := HashPassword("S3cret-golden", rounds)
	if err != nil {
		t.Fatalf("HashPassword 失败: %v", err)
	}

	parts := strings.Split(stored, "$")
	if len(parts) != 4 {
		t.Fatalf("应是 4 段 $ 分隔，实得 %d 段：%s", len(parts), stored)
	}
	if parts[0] != "pbkdf2_sha256" {
		t.Errorf("前缀应是 pbkdf2_sha256，实得 %q", parts[0])
	}
	if parts[1] != strconv.Itoa(rounds) {
		t.Errorf("迭代数应原样写进串里（验证时以串为准），期望 %d 实得 %s", rounds, parts[1])
	}
	salt, err := base64.StdEncoding.DecodeString(parts[2])
	if err != nil {
		t.Fatalf("盐必须是标准 base64（不是 urlsafe）: %v", err)
	}
	if len(salt) != 16 {
		t.Errorf("盐长应是 16 字节（对齐 os.urandom(16)），实得 %d", len(salt))
	}
	digest, err := base64.StdEncoding.DecodeString(parts[3])
	if err != nil {
		t.Fatalf("摘要必须是标准 base64: %v", err)
	}
	if len(digest) != digestLen {
		t.Errorf("摘要应是 %d 字节，实得 %d", digestLen, len(digest))
	}
	if !VerifyPassword("S3cret-golden", stored) {
		t.Error("自己写的哈希自己验不过")
	}
	if VerifyPassword("S3cret-golden2", stored) {
		t.Error("换了口令却验过了")
	}
}

// TestHashPasswordUsesFreshSalt 断言盐是随机的：两次调用不能产出同一串。
// 固定盐的实现会让彩虹表直接可用，而这条从格式上看不出来。
func TestHashPasswordUsesFreshSalt(t *testing.T) {
	a, err := HashPassword("same-password", 40000)
	if err != nil {
		t.Fatal(err)
	}
	b, err := HashPassword("same-password", 40000)
	if err != nil {
		t.Fatal(err)
	}
	if a == b {
		t.Error("同口令两次哈希结果相同 → 盐不是随机的")
	}
	if !VerifyPassword("same-password", a) || !VerifyPassword("same-password", b) {
		t.Error("两串都应能被同口令验过")
	}
}

func TestHashPasswordRejectsDegenerateArguments(t *testing.T) {
	if _, err := HashPassword("", 40000); err == nil {
		t.Error("空口令应报错（Python 是 raise ValueError），不该产出一串能用的哈希")
	}
	if _, err := HashPassword("x", 0); err == nil {
		t.Error("迭代数为 0 应报错")
	}
	if _, err := HashPassword("x", -1); err == nil {
		t.Error("迭代数为负应报错")
	}
}
