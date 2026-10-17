package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/sha512"
	"encoding/base64"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

var jwtGoldenPath = filepath.Join("..", "..", "..", "contracts", "jwt_golden.json")

type jwtGoldenVector struct {
	VectorID      string         `json:"vector_id"`
	Token         string         `json:"token"`
	ProducedBy    string         `json:"produced_by"`
	SignedWith    string         `json:"signed_with"`
	ExpireMinutes int            `json:"expire_minutes"`
	ExpectAccept  bool           `json:"expect_accept"`
	RejectedBy    *string        `json:"rejected_by"`
	Claims        map[string]any `json:"claims"`
	Note          string         `json:"note"`
}

type jwtGoldenDoc struct {
	SchemaVersion int                 `json:"schema_version"`
	Algorithm     string              `json:"algorithm"`
	Secret        string              `json:"secret"`
	SecretRule    string              `json:"secret_rule"`
	Judge         string              `json:"judge"`
	KnownUser     string              `json:"known_user"`
	UnknownUser   string              `json:"unknown_user"`
	Vectors       []jwtGoldenVector   `json:"vectors"`
	Divergences   []map[string]string `json:"divergences"`
}

// loadJWTGolden 读不到就 Fatal，绝不 Skip——理由与 loadGolden 相同（台账 C17：
// 选择器落空时"没有测试"必须表现为失败，不能表现为通过）。
func loadJWTGolden(t *testing.T) jwtGoldenDoc {
	t.Helper()
	raw, err := os.ReadFile(jwtGoldenPath)
	if err != nil {
		t.Fatalf("读不到 JWT golden tokens（%s）: %v —— 先跑 uv run python scripts/export_jwt_golden.py",
			jwtGoldenPath, err)
	}
	var doc jwtGoldenDoc
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("jwt_golden.json 不是合法 JSON: %v", err)
	}
	if len(doc.Vectors) == 0 {
		t.Fatal("jwt_golden.json 里没有向量：0 条的「逐条通过」没有意义")
	}
	if doc.Secret == "" {
		t.Fatal("jwt_golden.json 没有 secret 字段，Go 侧无从校验签名")
	}
	return doc
}

// goldenTokenAxis 把每条**令牌层**负向量钉在它该失败的那条轴上。
// 只断言"被拒了"是不够的：一个把所有令牌都拒掉的实现同样能让负向量全绿，
// 而正向向量会红——但红的原因看不出来是"过期没实现"还是"type 没实现"。
var goldenTokenAxis = map[string]error{
	"refresh-as-access":  ErrTokenType,
	"expired-access":     ErrTokenExpired,
	"wrong-secret":       ErrTokenSignature,
	"missing-sub":        ErrTokenSubject,
	"tampered-signature": ErrTokenSignature,
}

// TestParseGoldenTokens 是 X4 的令牌半侧判据：Python 签发 → Go 校验。
// 每条向量的期望值来自生产函数 get_user_from_bearer_token（见文件里的 judge 字段）。
func TestParseGoldenTokens(t *testing.T) {
	doc := loadJWTGolden(t)
	cfg := TokenConfig{Secret: doc.Secret, ExpireMinutes: 60, RefreshExpireDays: 30}

	var accepted, rejectedByToken, rejectedByDatabase int
	for _, v := range doc.Vectors {
		username, err := ParseAccessToken(cfg, v.Token)
		layer := ""
		if v.RejectedBy != nil {
			layer = *v.RejectedBy
		}

		switch {
		case v.ExpectAccept:
			if err != nil {
				t.Errorf("向量 %q：生产裁判接受，Go 却拒了: %v（%s）", v.VectorID, err, v.Note)
				continue
			}
			// 返回的用户名必须等于 token 里 sub 那一项，也就是文件记录的 claims.sub。
			if want, _ := v.Claims["sub"].(string); username != want {
				t.Errorf("向量 %q：解析出的用户名 %q 与 claims.sub %q 不一致", v.VectorID, username, want)
			}
			accepted++

		case layer == "database":
			// 这条向量的拒绝发生在**回库**那一步，令牌层应当放行。
			// 断言"令牌层放行"同样重要：它守住了 ParseAccessToken 不越权去管库里有没有人，
			// 而"必须回库"由 service 层的 TestCurrentUserRejectsVanishedUser 断言。
			if err != nil {
				t.Errorf("向量 %q 是回库那一步拒的（rejected_by=database），令牌层不该拒: %v", v.VectorID, err)
				continue
			}
			if username != doc.UnknownUser {
				t.Errorf("向量 %q：应原样返回 sub=%q，实得 %q", v.VectorID, doc.UnknownUser, username)
			}
			rejectedByDatabase++

		default: // layer == "token"
			want, ok := goldenTokenAxis[v.VectorID]
			if !ok {
				t.Fatalf("向量 %q 标了 rejected_by=token，但 goldenTokenAxis 里没有它对应的轴；"+
					"补上映射再跑，别让它退化成「反正被拒了就算过」", v.VectorID)
			}
			if !errors.Is(err, want) {
				t.Errorf("向量 %q：期望因 %v 被拒，实得 %v（%s）", v.VectorID, want, err, v.Note)
				continue
			}
			rejectedByToken++
		}
	}

	if accepted == 0 {
		t.Error("没有一条正向向量：全拒的实现也能让负向量绿，这份清单就废了")
	}
	if rejectedByToken == 0 || rejectedByDatabase == 0 {
		t.Errorf("向量集退化：令牌层拒绝 %d 条 / 回库拒绝 %d 条，两侧都不能为 0",
			rejectedByToken, rejectedByDatabase)
	}
	t.Logf("golden tokens 逐条对上：接受 %d / 令牌层拒 %d / 回库拒 %d", accepted, rejectedByToken, rejectedByDatabase)
}

// TestGoldenAxisTableMatchesFile 防两件事：文件里新增了 rejected_by=token 的向量而
// goldenTokenAxis 没跟上（上面那条用例会 Fatal，但这里给出更清楚的清单差异），
// 以及映射表里留着已经不在文件里的僵尸条目。
func TestGoldenAxisTableMatchesFile(t *testing.T) {
	doc := loadJWTGolden(t)
	inFile := map[string]bool{}
	for _, v := range doc.Vectors {
		if v.RejectedBy != nil && *v.RejectedBy == "token" {
			inFile[v.VectorID] = true
		}
	}
	for id := range inFile {
		if _, ok := goldenTokenAxis[id]; !ok {
			t.Errorf("文件里的令牌层负向量 %q 在 goldenTokenAxis 里没有对应断言", id)
		}
	}
	for id := range goldenTokenAxis {
		if !inFile[id] {
			t.Errorf("goldenTokenAxis 里的 %q 已不在文件的令牌层负向量里（僵尸条目）", id)
		}
	}
}

// TestGoldenFileKeepsItsHonestySection 钉住 divergences 段不被悄悄删掉。
// 那一段记的是两侧**结论不同**的轴（缺 exp：Python 收、Go 拒），是这份清单的边界声明；
// 边界声明消失，读文件的人就会以为"逐条一致"覆盖了全部情形。
func TestGoldenFileKeepsItsHonestySection(t *testing.T) {
	doc := loadJWTGolden(t)
	if len(doc.Divergences) == 0 {
		t.Fatal("jwt_golden.json 的 divergences 段空了：两侧已知的结论差异必须写在文件里")
	}
	joined := ""
	for _, d := range doc.Divergences {
		joined += d["axis"] + " "
	}
	if !strings.Contains(joined, "exp") {
		t.Errorf("divergences 里应记着「缺 exp」这条（Python 收、Go 拒），实得: %s", joined)
	}
}

// TestIssueAndParseRoundTrip 是 Go 自签自验。它**不能**替代 golden tokens
// （自签自验对"两侧编码不一致"是盲的），但它管住签发侧的形状。
func TestIssueAndParseRoundTrip(t *testing.T) {
	cfg := TokenConfig{Secret: "round-trip-secret", ExpireMinutes: 60, RefreshExpireDays: 30}

	access, err := IssueAccessToken(cfg, "alice", "user")
	if err != nil {
		t.Fatalf("签发 access 失败: %v", err)
	}
	username, err := ParseAccessToken(cfg, access)
	if err != nil {
		t.Fatalf("自己签的令牌自己验不过: %v", err)
	}
	if username != "alice" {
		t.Errorf("用户名应是 alice，实得 %q", username)
	}

	refresh, err := IssueRefreshToken(cfg, "alice", "user")
	if err != nil {
		t.Fatalf("签发 refresh 失败: %v", err)
	}
	if _, err := ParseAccessToken(cfg, refresh); !errors.Is(err, ErrTokenType) {
		t.Errorf("refresh 当 access 用应因 %v 被拒，实得 %v", ErrTokenType, err)
	}
}

// TestIssuedClaimsMatchPythonShape 逐字段对齐 create_access_token 的载荷：
// sub / role / type / exp 四项，exp 是数字时间戳（PyJWT 使用同一 JWT 数字时间戳）。
// 多一项少一项都会让 Python 侧验不过或读不到角色。
func TestIssuedClaimsMatchPythonShape(t *testing.T) {
	cfg := TokenConfig{Secret: "shape-secret", ExpireMinutes: 60, RefreshExpireDays: 30}
	before := time.Now().UTC()
	token, err := IssueAccessToken(cfg, "bob", "admin")
	if err != nil {
		t.Fatal(err)
	}

	parsed, _, err := jwt.NewParser().ParseUnverified(token, jwt.MapClaims{})
	if err != nil {
		t.Fatalf("解不开自己签的令牌: %v", err)
	}
	claims, ok := parsed.Claims.(jwt.MapClaims)
	if !ok {
		t.Fatalf("claims 类型不对: %T", parsed.Claims)
	}

	if got := claims["sub"]; got != "bob" {
		t.Errorf("sub 应是 bob，实得 %v", got)
	}
	if got := claims["role"]; got != "admin" {
		t.Errorf("role 应是 admin，实得 %v", got)
	}
	if got := claims["type"]; got != TokenTypeAccess {
		t.Errorf("type 应是 access，实得 %v", got)
	}
	exp, ok := claims["exp"].(float64)
	if !ok {
		t.Fatalf("exp 应是数字时间戳（Python 侧 datetime 被 PyJWT 转成 int），实得 %T=%v", claims["exp"], claims["exp"])
	}
	gotExp := time.Unix(int64(exp), 0).UTC()
	wantExp := before.Add(60 * time.Minute)
	if gotExp.Before(wantExp.Add(-2*time.Minute)) || gotExp.After(wantExp.Add(2*time.Minute)) {
		t.Errorf("exp 应是签发时刻 + 60 分钟：期望约 %s，实得 %s", wantExp.Format(time.RFC3339), gotExp.Format(time.RFC3339))
	}
	if len(claims) != 4 {
		t.Errorf("载荷应恰好是 sub/role/type/exp 四项（多出来的字段 Python 侧读不到，只会让两侧形状漂移），实得 %d 项: %v",
			len(claims), claims)
	}

	if alg := parsed.Header["alg"]; alg != AlgorithmHS256 {
		t.Errorf("alg 应是 HS256，实得 %v", alg)
	}
}

// TestExpiredTokenIsRejected 用负有效期直接造一枚过期令牌。
// golden 文件里也有 expired-access 那条（由生产函数签发），这条补的是 Go 自己的签发路径：
// 有效期算错（比如把分钟当秒）会让所有令牌一签出来就过期，而那在正向用例里看不出来。
func TestExpiredTokenIsRejected(t *testing.T) {
	cfg := TokenConfig{Secret: "expired-secret", ExpireMinutes: -1, RefreshExpireDays: 30}
	token, err := IssueAccessToken(cfg, "carol", "user")
	if err != nil {
		t.Fatal(err)
	}
	cfgNormal := TokenConfig{Secret: "expired-secret", ExpireMinutes: 60}
	if _, err := ParseAccessToken(cfgNormal, token); !errors.Is(err, ErrTokenExpired) {
		t.Errorf("过期令牌应因 %v 被拒，实得 %v", ErrTokenExpired, err)
	}

	refreshCfg := TokenConfig{Secret: "expired-secret", ExpireMinutes: 60, RefreshExpireDays: -1}
	refresh, err := IssueRefreshToken(refreshCfg, "carol", "user")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ParseAccessToken(cfgNormal, refresh); err == nil {
		t.Error("过期的 refresh 也不该被当访问凭证接受")
	}
}

// TestRejectsAlgorithmConfusion 钉住算法白名单。两条都是真实的攻击面：
// alg=none 是"干脆不签"，alg=HS512 是"换一种 HMAC 让白名单失效"。
// Python 侧用 algorithms=[JWT_ALGORITHM] 同样拒绝（2026-10-12 实跑核对：两者皆拒），
// 差别只在 Go 连"配成别的算法"这个口子都不给（见 jwt_golden.json 的 divergences 第 2 条）。
func TestRejectsAlgorithmConfusion(t *testing.T) {
	const secret = "alg-confusion-secret"
	cfg := TokenConfig{Secret: secret, ExpireMinutes: 60}
	claimsJSON := `{"sub":"dave","role":"user","type":"access","exp":4102444800}`

	t.Run("alg=none", func(t *testing.T) {
		unsigned := b64url([]byte(`{"alg":"none","typ":"JWT"}`)) + "." + b64url([]byte(claimsJSON)) + "."
		if _, err := ParseAccessToken(cfg, unsigned); err == nil {
			t.Error("alg=none 的令牌被接受了")
		} else if !errors.Is(err, ErrTokenSignature) {
			t.Errorf("alg=none 应归到 %v，实得 %v", ErrTokenSignature, err)
		}
	})

	t.Run("alg=HS512", func(t *testing.T) {
		signingInput := b64url([]byte(`{"alg":"HS512","typ":"JWT"}`)) + "." + b64url([]byte(claimsJSON))
		mac := hmac.New(sha512.New, []byte(secret))
		mac.Write([]byte(signingInput))
		token := signingInput + "." + b64url(mac.Sum(nil))
		if _, err := ParseAccessToken(cfg, token); err == nil {
			t.Error("alg=HS512 的令牌被接受了：白名单没生效")
		}
	})

	t.Run("alg 大小写", func(t *testing.T) {
		signingInput := b64url([]byte(`{"alg":"hs256","typ":"JWT"}`)) + "." + b64url([]byte(claimsJSON))
		mac := hmac.New(sha256.New, []byte(secret))
		mac.Write([]byte(signingInput))
		token := signingInput + "." + b64url(mac.Sum(nil))
		if _, err := ParseAccessToken(cfg, token); err == nil {
			t.Error("alg=hs256（小写）被接受了：白名单应逐字比对")
		}
	})
}

// TestRequiresExpClaim 是 jwt_golden.json 的 divergences 第 1 条的 Go 侧那一半。
// 2026-10-12 两侧实跑核对过：同一枚缺 exp 的令牌，Python 的生产函数**接受**
// （PyJWT 只在 exp 存在时校验），Go 拒绝。方向是更严，且生产签发函数总会写 exp，
// 所以碰不到真实令牌——但这条分歧必须写下来，否则将来有人拿 Python 的行为当基准，
// 会以为 Go 这边坏了。
func TestRequiresExpClaim(t *testing.T) {
	const secret = "no-exp-secret"
	signingInput := b64url([]byte(`{"alg":"HS256","typ":"JWT"}`)) + "." +
		b64url([]byte(`{"sub":"erin","role":"user","type":"access"}`))
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(signingInput))
	token := signingInput + "." + b64url(mac.Sum(nil))

	_, err := ParseAccessToken(TokenConfig{Secret: secret, ExpireMinutes: 60}, token)
	if !errors.Is(err, ErrTokenMalformed) {
		t.Errorf("缺 exp 的令牌应因 %v 被拒（WithExpirationRequired），实得 %v", ErrTokenMalformed, err)
	}
}

// TestNonCanonicalSignatureTrailingBits verifies strict base64url decoding in both runtimes.
func TestNonCanonicalSignatureTrailingBits(t *testing.T) {
	doc := loadJWTGolden(t)
	cfg := TokenConfig{Secret: doc.Secret, ExpireMinutes: 60}

	var token string
	for _, v := range doc.Vectors {
		if v.VectorID == "access-user" {
			token = v.Token
		}
	}
	if token == "" {
		t.Fatal("golden 文件里没有 access-user 向量")
	}
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		t.Fatalf("令牌应是三段，实得 %d 段", len(parts))
	}
	signature := parts[2]
	if len(signature) != 43 {
		t.Fatalf("HS256 签名的 base64url 长度应是 43，实得 %d", len(signature))
	}

	const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
	last := strings.IndexByte(alphabet, signature[len(signature)-1])
	if last < 0 {
		t.Fatalf("签名末字符 %q 不在 base64url 字母表里", signature[len(signature)-1])
	}
	if last&3 != 0 {
		t.Fatalf("规范编码下末字符的低 2 位应是 0（填充位），实得 %d", last&3)
	}

	replaceLast := func(idx int) string {
		return parts[0] + "." + parts[1] + "." + signature[:len(signature)-1] + string(alphabet[idx])
	}
	// 非零填充位也是非规范编码，与 PyJWT 一致拒绝。
	for _, delta := range []int{1, 2, 3} {
		if _, err := ParseAccessToken(cfg, replaceLast(last^delta)); err == nil {
			t.Errorf("非规范填充位（末字符 ^%d）应被拒: %v", delta, err)
		}
	}
	// 动到有效位（第 3 位起）→ 签名字节变了 → 拒绝
	for _, delta := range []int{4, 8, 16} {
		if _, err := ParseAccessToken(cfg, replaceLast(last^delta)); err == nil {
			t.Errorf("改了有效位（末字符 ^%d）却被接受了：签名校验没生效", delta)
		}
	}
}

func TestParseAccessTokenRejectsDegenerateInputs(t *testing.T) {
	cfg := TokenConfig{Secret: "degenerate-secret", ExpireMinutes: 60}
	for name, token := range map[string]string{
		"空串":        "",
		"只有一段":      "abcdef",
		"两段":        "abcdef.ghijkl",
		"四段":        "a.b.c.d",
		"不是 base64": "!!!.@@@.###",
		"Bearer 前缀": "Bearer " + mustIssue(t, cfg, "frank"),
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := ParseAccessToken(cfg, token); err == nil {
				t.Errorf("ParseAccessToken(%q) 应报错", token)
			}
		})
	}
}

// TestEmptySecretIsRefusedOnBothEnds 钉住"空密钥"这条路：缺失签名密钥没有安全兜底，
// 那比可猜测的默认值更危险（backend/core/config/__init__.py:validate_runtime_security 的注释
// 就是这么写的），所以 Go 侧签发与校验都不给这个口子。
func TestEmptySecretIsRefusedOnBothEnds(t *testing.T) {
	cfg := TokenConfig{Secret: "", ExpireMinutes: 60}
	if _, err := IssueAccessToken(cfg, "grace", "user"); !errors.Is(err, ErrNoSecret) {
		t.Errorf("空密钥签发应因 %v 被拒，实得 %v", ErrNoSecret, err)
	}
	if _, err := IssueRefreshToken(cfg, "grace", "user"); !errors.Is(err, ErrNoSecret) {
		t.Errorf("空密钥签发 refresh 应因 %v 被拒，实得 %v", ErrNoSecret, err)
	}
	if _, err := ParseAccessToken(cfg, "whatever.whatever.whatever"); !errors.Is(err, ErrNoSecret) {
		t.Errorf("空密钥校验应因 %v 被拒，实得 %v", ErrNoSecret, err)
	}
}

func TestIssueAccessTokenRejectsEmptyUsername(t *testing.T) {
	cfg := TokenConfig{Secret: "no-sub-secret", ExpireMinutes: 60}
	if _, err := IssueAccessToken(cfg, "", "user"); err == nil {
		t.Error("空用户名不该能签出令牌：没有 sub 的令牌谁都验不过")
	}
}

func mustIssue(t *testing.T, cfg TokenConfig, username string) string {
	t.Helper()
	token, err := IssueAccessToken(cfg, username, "user")
	if err != nil {
		t.Fatalf("签发失败: %v", err)
	}
	return token
}

func b64url(raw []byte) string {
	return base64.RawURLEncoding.EncodeToString(raw)
}
