package auth

import (
	"errors"
	"net/http"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/httpapi"
)

// RequireIdentity 把 Authorization 头换成 *Identity；失败时**响应已经写好**，调用方直接 return。
//
// 两段 401 的文案不同是生产侧现状（handler.go 顶上那张实测表记的）：缺头或方案不是 bearer
// 都是 "Not authenticated"，令牌本身有问题（签名错/过期/用户已不在库里）才是
// "无效或过期的认证令牌"。收成一个函数不是省事，而是这段前奏之后每接管一条用户面都要走一遍，
// 各抄各的就会漂出四种版本——而它是安全语义，漂不起。
//
// 已有的四个 auth handler 仍保留各自的内联前奏：它们的错误分支与各自的业务错误交织
// （比如偏好面那条 writePreferencesError），改动超出本次接管范围（原则④）。
func RequireIdentity(s *Service, w http.ResponseWriter, r *http.Request) (*Identity, bool) {
	token, ok := bearerToken(r.Header.Get("Authorization"))
	if !ok {
		writeUnauthorized(w, detailNotAuthenticated)
		return nil, false
	}
	identity, err := s.CurrentUser(r.Context(), token)
	if err != nil {
		if errors.Is(err, ErrUnauthenticated) {
			writeUnauthorized(w, detailInvalidToken)
			return nil, false
		}
		// 到这里是查库本身失败，不是身份有问题：对外不给细节，但也不假装 401
		httpapi.WriteError(w, http.StatusInternalServerError, detailInternalError)
		return nil, false
	}
	return identity, true
}
