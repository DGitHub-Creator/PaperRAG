// Package auth 是 P0-6 的认证垂直切片：Go 侧的 register / login / me。
//
// 本包的每一条语义都以 Python 现状为**裁判**，不自创更"合理"的版本：
// 密码哈希对齐 backend/core/auth.py:verify_password / get_password_hash，
// 令牌对齐同文件的 create_access_token / create_refresh_token / get_user_from_bearer_token，
// HTTP 文案对齐 backend/api/auth.py。理由很实际——切换窗口内两侧同时在跑，
// 任何一处"Go 更严格/更宽松"都会变成用户登录时好时坏，而这种 bug 只在真实数据上出现。
//
// 裁判一致性由两份 golden 文件机检，不靠人读代码比对：
// contracts/pbkdf2_golden.json（X5）与 contracts/jwt_golden.json（X4 的令牌半侧）。
package auth

import (
	"crypto/hmac"
	"crypto/pbkdf2"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"fmt"
	"strconv"
	"strings"
)

// hashPrefix 是库里 password_hash 的格式头：pbkdf2_sha256$<rounds>$<盐 b64>$<摘要 b64>。
const hashPrefix = "pbkdf2_sha256"

// digestLen 固定 32：Python 侧 hashlib.pbkdf2_hmac("sha256", ...) 不传 dklen，
// 默认就是 SHA256 的输出长度。写死在这里而不是从哈希串推导，正是为了让
// "摘要被截短"的串验不过（hmac.Equal 对长度不同一律 false）。
const digestLen = 32

// saltLen 是**新写入**哈希的盐长度，对齐 get_password_hash 的 os.urandom(16)。
// 验证时不用它：盐长从串里解出来是多少就是多少（golden vectors 覆盖 8/16/32）。
const saltLen = 16

// Family 是库里 password_hash 的哈希族。分开报而不是只返回 bool，
// 是为了让"Go 验不了这批人"这件事可见——见 FamilyBCrypt 的说明。
type Family int

const (
	// FamilyUnknown 是空串与不认识的前缀。verify_password 对它们返回 False，Go 同。
	FamilyUnknown Family = iota
	// FamilyPBKDF2 是 Go 能验的族。
	FamilyPBKDF2
	// FamilyBCrypt 是 passlib 时代留下的 $2*/$bcrypt* 串。Python 侧装了 passlib 就能验，
	// **Go 侧不实现**：本机原真库已随 Docker 数据卷消失（台账 C20），"库里到底还有没有这类行"
	// 已无法核查，引一个 bcrypt 依赖去验一批可能不存在的行就是死代码（原则④）。
	// 代价必须写明：若接管 users 时库里仍有这类行，这些人会被锁死。
	// 所以 P1 接管前的前置动作是跑 `export_pbkdf2_golden.py --from-db` 看 families 里有没有 bcrypt，
	// 有就先强制改密（把哈希重签成 pbkdf2_sha256）再切写者。
	FamilyBCrypt
)

// String 让日志里出现的是 `family=bcrypt` 而不是 `family=1`。
// 这不是美观问题：那条日志是"这批人会被锁死"唯一的线索（见 FamilyBCrypt 的说明），
// 而一个数字枚举值在告警里等于没有信息。
func (f Family) String() string {
	switch f {
	case FamilyPBKDF2:
		return "pbkdf2_sha256"
	case FamilyBCrypt:
		return "bcrypt"
	default:
		return "unknown"
	}
}

// HashFamily 报告 stored 属于哪一族。登录路径用它把"密码错"与"这行 Go 根本验不了"分开记日志：
// 两者对外都是同一句 401（不泄露区别），但对运维是完全不同的两件事。
func HashFamily(stored string) Family {
	switch {
	case strings.HasPrefix(stored, hashPrefix+"$"):
		return FamilyPBKDF2
	case strings.HasPrefix(stored, "$2"), strings.HasPrefix(stored, "$bcrypt"):
		return FamilyBCrypt
	default:
		return FamilyUnknown
	}
}

// VerifyPassword 判断明文口令与库里的哈希串是否匹配，语义逐条对齐
// backend/core/auth.py:verify_password（生产裁判）。返回 false 的情形：
// 空口令、空哈希、非 pbkdf2_sha256 前缀、分段数不对、rounds 非正整数、
// base64 解不开、摘要长度或内容不符。**任何失败都是 false，不返回 error**——
// 裁判的签名就是 bool，而"格式不认识"与"密码错"对调用方是同一件事。
//
// 两处与 Python 的已知分歧，方向都是"更严"（只会拒绝，不会误接受）：
//
//  1. base64 解码：Python 的 b64decode 默认 validate=False，会**先丢掉**非标准字母表的字符
//     再解码；Go 的 StdEncoding 严格拒绝。对 golden vectors 里的 urlsafe 串两者结论相同
//     （Python 丢掉 `-_` 后长度非法而抛异常），只有"杂字符混进第 4 段"这种手工改库才可能分歧。
//     生产 get_password_hash 只产标准字母表，所以这条分歧碰不到真实数据。
//  2. rounds 解析：Python 的 int() 还接受空格、下划线（"40_000"）这类写法，strconv.Atoi 不接受。
//     同样只可能出现在手工改库的串上。
func VerifyPassword(plain, stored string) bool {
	if plain == "" || stored == "" {
		return false
	}
	if HashFamily(stored) != FamilyPBKDF2 {
		return false
	}

	// Python 是 `_, rounds, salt_b64, digest_b64 = password_hash.split("$", 3)`：
	// maxsplit=3 → 最多 4 段，**不足 4 段解包直接抛异常**（被 except 吞成 False），
	// 多于 4 段时最后一段会带着剩下的 `$`（随后在 b64decode 处失败）。
	// SplitN 的上界取 4 与之等价：len != 4 就是"少一段"，第 4 段带 `$` 则解码失败。
	parts := strings.SplitN(stored, "$", 4)
	if len(parts) != 4 {
		return false
	}

	rounds, err := strconv.Atoi(parts[1])
	if err != nil || rounds <= 0 {
		// rounds <= 0：Python 那边是 hashlib.pbkdf2_hmac 抛 ValueError，同样落到 False。
		return false
	}
	salt, err := base64.StdEncoding.DecodeString(parts[2])
	if err != nil {
		return false
	}
	expected, err := base64.StdEncoding.DecodeString(parts[3])
	if err != nil {
		return false
	}

	calculated, err := pbkdf2.Key(sha256.New, plain, salt, rounds, digestLen)
	if err != nil {
		return false
	}
	// 常量时间比对，对齐 hmac.compare_digest；长度不同直接 false（截短的摘要不能补零放过）。
	return hmac.Equal(calculated, expected)
}

// HashPassword 产出与 backend/core/auth.py:get_password_hash **同格式**的哈希串：
// 16 字节随机盐、SHA256、dklen 32、标准 base64（带 `=` 填充）、四段 `$` 分隔。
// 同格式是硬要求：切换窗口内 Go 写入的行，Python 侧仍可能要验（单写者原则约束的是
// "同一接口只有一边写"，不是"只有一边读"）。
//
// rounds 由调用方给（config.PasswordPBKDF2Rounds），不在这里读环境变量——
// 与 config 包的规矩一致：只在进程入口读一次环境变量。
func HashPassword(plain string, rounds int) (string, error) {
	if plain == "" {
		// Python 是 raise ValueError("密码不能为空")；空口令不是"验不过"而是"不该进来"。
		return "", errors.New("密码不能为空")
	}
	if rounds <= 0 {
		return "", fmt.Errorf("PBKDF2 迭代数必须为正，得到 %d", rounds)
	}
	salt := make([]byte, saltLen)
	if _, err := rand.Read(salt); err != nil {
		return "", fmt.Errorf("生成盐失败: %w", err)
	}
	digest, err := pbkdf2.Key(sha256.New, plain, salt, rounds, digestLen)
	if err != nil {
		return "", fmt.Errorf("PBKDF2 派生失败: %w", err)
	}
	return fmt.Sprintf("%s$%d$%s$%s",
		hashPrefix, rounds,
		base64.StdEncoding.EncodeToString(salt),
		base64.StdEncoding.EncodeToString(digest),
	), nil
}
