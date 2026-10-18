package session

import (
	"errors"
	"net/http"

	"github.com/go-chi/chi/v5"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/auth"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/httpapi"
)

// detailSessionMissing 逐字取自 backend/api/sessions.py:60——前端按这句做提示，
// 换措辞就是跨语言分歧（同 C23 那条 500 文案的教训）。
const detailSessionMissing = "Session does not exist"

// ListHandler 处理 GET /api/v1/sessions。
func ListHandler(svc *Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		identity, ok := auth.RequireIdentity(svc.Auth, w, r)
		if !ok {
			return
		}
		out, err := svc.List(r.Context(), identity)
		if err != nil {
			writeServiceError(svc, w, r, err)
			return
		}
		httpapi.WriteJSON(w, http.StatusOK, out)
	}
}

// DetailHandler 处理 GET /api/v1/sessions/{session_id}。
//
// 鉴权与列表同序：先验令牌再解路径参数，没登录时不会因为 URL 里带了别人的会话号而先给出
// 任何可区分信号（这里连 404 都不给，见 Service.Detail 的注释）。
func DetailHandler(svc *Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		identity, ok := auth.RequireIdentity(svc.Auth, w, r)
		if !ok {
			return
		}
		out, err := svc.Detail(r.Context(), identity, chi.URLParam(r, "session_id"))
		if err != nil {
			writeServiceError(svc, w, r, err)
			return
		}
		httpapi.WriteJSON(w, http.StatusOK, out)
	}
}

// DeleteHandler 处理 DELETE /api/v1/sessions/{session_id}。
//
// 先验令牌再取路径参数：没登录时不该因为"URL 里带了个别人的会话号"而先回 404，
// 那等于把"这个会话存在"泄露给一个没有身份的请求（与 Python 侧同一层考虑）。
func DeleteHandler(svc *Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		identity, ok := auth.RequireIdentity(svc.Auth, w, r)
		if !ok {
			return
		}
		sessionID := chi.URLParam(r, "session_id")
		deleted, err := svc.Delete(r.Context(), identity, sessionID)
		if err != nil {
			writeServiceError(svc, w, r, err)
			return
		}
		if !deleted {
			httpapi.WriteError(w, http.StatusNotFound, detailSessionMissing)
			return
		}
		httpapi.WriteJSON(w, http.StatusOK, DeleteResponse{SessionID: sessionID, Message: deletedMessage})
	}
}

func writeServiceError(svc *Service, w http.ResponseWriter, r *http.Request, err error) {
	// 未装配 Store 是配置问题，值得单独一条：它会被误报成"数据库坏了"，而两者排查方向完全不同
	if errors.Is(err, ErrStoreUnavailable) {
		svc.Logger.Error("会话面未装配", "path", r.URL.Path, "error", err)
	} else {
		svc.Logger.Error("会话请求失败", "path", r.URL.Path, "error", err)
	}
	httpapi.WriteError(w, http.StatusInternalServerError, httpapi.DetailInternalError)
}
