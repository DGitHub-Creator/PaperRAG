package auth

import (
	"errors"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// 令牌用途声明，对齐 backend/core/auth.py 的 TOKEN_TYPE_ACCESS / TOKEN_TYPE_REFRESH。
// 历史 access token 不带 type，所以校验时"缺失"等同 "access"（见 ParseAccessToken）。
const (
	TokenTypeAccess  = "access"
	TokenTypeRefresh = "refresh"
)

// AlgorithmHS256 是 Go 侧**唯一**接受的签名算法，而且不给配置口子：
// Python 侧是 JWT_ALGORITHM 可配（默认 HS256），Go 侧把它写死。
// 理由是算法可配就是算法混淆的入口——`alg: none` 与 RS/HS 混用都从"能配"开始。
// 配成别的值时 ValidateAuth 会拒绝启动，两侧因此不会各签各的。
const AlgorithmHS256 = "HS256"

// TokenConfig 是签发与校验令牌所需的最小配置面。
// 不直接收 config.Config：本包不该知道"配置从环境变量来"，单测也才能逐条构造边界值
// （负有效期用来测过期，空密钥用来测 fail-fast）。
type TokenConfig struct {
	// Secret 是 HMAC 密钥。空密钥会被 Issue/Parse 直接拒绝——PyJWT 对空密钥是
	// **静默接受**的，那比可猜测的默认值更危险，所以 Go 侧不给这个口子。
	Secret string
	// ExpireMinutes 是 access token 的有效期，对齐 JWT_EXPIRE_MINUTES（默认 60）。
	ExpireMinutes int
	// RefreshExpireDays 是 refresh token 的有效期，对齐 JWT_REFRESH_EXPIRE_DAYS（默认 30）。
	RefreshExpireDays int
}

// 失败原因分开报，但 HTTP 层一律折叠成同一句 401：对外不泄露"是签名错还是过期"，
// 对内（日志与单测）要能看出是哪条轴失败的——否则"令牌被拒"这个结论证明不了
// 实现真的在校验那条轴。生产侧 backend/core/auth.py 也是这么分的（三条不同的 warning）。
var (
	ErrTokenMalformed = errors.New("令牌格式非法")
	ErrTokenSignature = errors.New("令牌签名不匹配")
	ErrTokenExpired   = errors.New("令牌已过期")
	ErrTokenType      = errors.New("令牌类型不符：需要 access")
	ErrTokenSubject   = errors.New("令牌有效但缺少 sub 字段")
	ErrNoSecret       = errors.New("JWT 密钥未配置")
)

// IssueAccessToken 签发 access token，载荷与 backend/core/auth.py:create_access_token
// 逐字段一致：sub（用户名）、role、type=access、exp。
//
// 字段名与类型都不能改：Python 侧要能验 Go 签的令牌（X4 的另一半），
// 而 PyJWT 认的是 `exp` 这个数字时间戳。
func IssueAccessToken(cfg TokenConfig, username, role string) (string, error) {
	return issue(cfg, username, role, TokenTypeAccess, time.Duration(cfg.ExpireMinutes)*time.Minute)
}

// IssueRefreshToken 签发 refresh token，对齐 create_refresh_token（type=refresh，有效期按天）。
func IssueRefreshToken(cfg TokenConfig, username, role string) (string, error) {
	return issue(cfg, username, role, TokenTypeRefresh, time.Duration(cfg.RefreshExpireDays)*24*time.Hour)
}

func issue(cfg TokenConfig, username, role, tokenType string, ttl time.Duration) (string, error) {
	if cfg.Secret == "" {
		return "", ErrNoSecret
	}
	if username == "" {
		// 生产侧不会走到这里（注册/登录都已校验过用户名非空），
		// 但签一张没有 sub 的令牌等于签一张谁都验不过的令牌，早拒比晚拒好。
		return "", errors.New("用户名不能为空")
	}
	claims := jwt.MapClaims{
		"sub":  username,
		"role": role,
		"type": tokenType,
		"exp":  jwt.NewNumericDate(time.Now().UTC().Add(ttl)),
	}
	return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(cfg.Secret))
}

// ParseAccessToken 校验一枚访问令牌并返回它声称的用户名。
//
// 只做**令牌级**的三项校验，与生产 get_user_from_bearer_token 的分工一致：
//  1. 签名有效且未过期（算法白名单只有 HS256）；
//  2. `sub` 存在且非空；
//  3. `type` 缺失（历史令牌）或为 "access" —— refresh 不能当访问凭证。
//
// 第 4 项"用户是否仍在库里"**不在这里**：本包不碰数据库，由 service 层回库判断。
// 刻意不返回 role——生产代码明确"角色一律取自数据库记录，不采信令牌里的 role 声明"
// （避免降级/改名后旧令牌继续持有旧权限）。这里连取值的机会都不给，比"返回了但注明别用"可靠。
//
// ⚠️ 与 Python 的一处已知分歧（记在 contracts/jwt_golden.json 的 divergences 里）：
// PyJWT 只在 `exp` 存在时校验，缺 exp 的令牌会被接受；这里用
// WithExpirationRequired 一律要求 exp。生产的两个签发函数总会写 exp，所以碰不到真实令牌，
// 方向是更严（拒绝而不是误接受）。
func ParseAccessToken(cfg TokenConfig, tokenStr string) (string, error) {
	if cfg.Secret == "" {
		return "", ErrNoSecret
	}
	if tokenStr == "" {
		return "", ErrTokenMalformed
	}

	token, err := jwt.Parse(tokenStr,
		func(t *jwt.Token) (any, error) {
			// WithValidMethods 已经卡了算法白名单，这里再挡一次是防御性的：
			// keyfunc 是唯一能决定"用哪把钥匙验"的地方，让它自己也不认非 HMAC 的方法，
			// 就不依赖调用方记得传那个 option。
			if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("%w: alg=%v", ErrTokenSignature, t.Header["alg"])
			}
			return []byte(cfg.Secret), nil
		},
		jwt.WithValidMethods([]string{AlgorithmHS256}),
		jwt.WithExpirationRequired(),
		jwt.WithStrictDecoding(),
	)
	if err != nil {
		return "", classifyParseError(err)
	}

	claims, ok := token.Claims.(jwt.MapClaims)
	if !ok || !token.Valid {
		return "", ErrTokenMalformed
	}

	sub, ok := claims["sub"].(string)
	if !ok || sub == "" {
		return "", ErrTokenSubject
	}
	// type 缺失等同 access（历史令牌）；存在则必须是 access。
	if raw, present := claims["type"]; present && raw != nil {
		if tokenType, isString := raw.(string); !isString || tokenType != TokenTypeAccess {
			return "", fmt.Errorf("%w，实际为 %v", ErrTokenType, raw)
		}
	}
	return sub, nil
}

// classifyParseError 把 golang-jwt 的错误翻译成上面那组可判定的哨兵值。
// 分开报是为了单测能断言"这条向量是因为过期被拒的"，而不是笼统的"被拒了"。
func classifyParseError(err error) error {
	switch {
	case errors.Is(err, jwt.ErrTokenExpired):
		return fmt.Errorf("%w: %w", ErrTokenExpired, err)
	case errors.Is(err, jwt.ErrTokenSignatureInvalid):
		return fmt.Errorf("%w: %w", ErrTokenSignature, err)
	case errors.Is(err, jwt.ErrTokenMalformed),
		errors.Is(err, jwt.ErrTokenUnverifiable),
		errors.Is(err, jwt.ErrTokenRequiredClaimMissing):
		// 算法不在白名单（如 alg=HS512 或 alg=none）与缺 exp 都落在这里：
		// 前者由 WithValidMethods 判成 ErrTokenUnverifiable，后者由 WithExpirationRequired
		// 判成 ErrTokenRequiredClaimMissing。对调用方都是"这枚令牌不能用"，归到 malformed。
		return fmt.Errorf("%w: %w", ErrTokenMalformed, err)
	default:
		return fmt.Errorf("%w: %w", ErrTokenMalformed, err)
	}
}
