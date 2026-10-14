package auth

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/db"
	"github.com/DGitHub-Creator/ResearchPilot/server/internal/httpapi"
)

// 偏好面（设置页的「偏好设置」「外观·主题」）。放在本包而不是新开一个包，
// 是因为它要复用的两样东西都在这里且**不适合搬走**：令牌校验（CurrentUser）
// 与请求体解码（decodeJSONObject/stringField 那套 pydantic 同构文案）。
// 为它单独建包就意味着要么导出这些内部件、要么抄一份 JSON 解码——两条都比
// 「把 /me/* 这类用户自助面与 /auth/* 放一起」更贵。路由前缀也印证了这层归属：
// /api/v1/auth/me 与 /api/v1/me/preferences 是同一个"我自己的账号"面。

// PrefsStore 是偏好读写面，由 *db.Queries 实现（emit_interface: false，故在消费方定义）。
type PrefsStore interface {
	GetUserPreferences(ctx context.Context, userID int32) (db.UserPreference, error)
	UpsertUserPreferences(ctx context.Context, arg db.UpsertUserPreferencesParams) (db.UserPreference, error)
}

// 主题是闭集，三处同值：000003_user_preferences 的 CHECK、本文件的常量、
// contracts/openapi.yaml 的 enum。改一处必须同改另两处。
const (
	ThemeLight  = "light"
	ThemeDark   = "dark"
	ThemeSystem = "system"
)

// DefaultStartView 与库里 `DEFAULT 'chat'` 同值：没有行时返回它。
const DefaultStartView = "chat"

var (
	// ErrInvalidTheme 对应 PUT 的 400：主题不在闭集内。
	ErrInvalidTheme = errors.New("主题取值不在允许集合内")
	// ErrInvalidStartView 对应 PUT 的 400：默认页不是合法 slug。
	ErrInvalidStartView = errors.New("默认页取值不合法")
	// ErrPrefsUnavailable 表示服务装配时没塞 Prefs（单测与不面向浏览器的进程）。
	ErrPrefsUnavailable = errors.New("偏好读写面未装配")
)

// startViewRE 只校验**形状**（小写 slug），不把前端的路由名抄进 Go。
// 路由表归前端（frontend/src/router/index.ts），抄一份会随产品增长而漂；
// 不认识的名字由前端在跳转时回退到 chat（见 14 §19 的分工：展示归前端）。
var startViewRE = regexp.MustCompile(`^[a-z][a-z0-9_-]{0,31}$`)

// Preferences 是对外的形状，对应契约的 UserPreferences。
type Preferences struct {
	Theme     string `json:"theme"`
	StartView string `json:"start_view"`
}

// GetPreferences 读当前用户偏好。**库里没有行是正常路径**（用户从没改过），
// 回默认值而不是 404——"还没设置"与"设置页打不开"是两回事。
func (s *Service) GetPreferences(ctx context.Context, bearerToken string) (*Preferences, error) {
	identity, err := s.CurrentUser(ctx, bearerToken)
	if err != nil {
		return nil, err
	}
	if s.Prefs == nil {
		return nil, ErrPrefsUnavailable
	}
	row, err := s.Prefs.GetUserPreferences(ctx, identity.ID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return &Preferences{Theme: ThemeSystem, StartView: DefaultStartView}, nil
		}
		return nil, fmt.Errorf("读取用户偏好失败: %w", err)
	}
	return &Preferences{Theme: row.Theme, StartView: row.StartView}, nil
}

// PutPreferences 整行覆盖当前用户偏好（两个字段都是闭集/短 slug，不存在部分更新语义）。
//
// created_at 与 updated_at 都由这里显式给 UTC 值：库里两列没有 DEFAULT（000003 的口径），
// upsert 的冲突分支只用 updated_at，created_at 仅在首插时落库。
func (s *Service) PutPreferences(ctx context.Context, bearerToken, theme, startView string) (*Preferences, error) {
	identity, err := s.CurrentUser(ctx, bearerToken)
	if err != nil {
		return nil, err
	}
	if s.Prefs == nil {
		return nil, ErrPrefsUnavailable
	}
	if !validTheme(theme) {
		return nil, ErrInvalidTheme
	}
	if !startViewRE.MatchString(startView) {
		return nil, ErrInvalidStartView
	}

	now := time.Now().UTC()
	row, err := s.Prefs.UpsertUserPreferences(ctx, db.UpsertUserPreferencesParams{
		UserID:    identity.ID,
		Theme:     theme,
		StartView: startView,
		CreatedAt: pgtype.Timestamptz{Time: now, Valid: true},
		UpdatedAt: pgtype.Timestamptz{Time: now, Valid: true},
	})
	if err != nil {
		return nil, fmt.Errorf("写入用户偏好失败: %w", err)
	}
	s.Logger.Info("用户偏好已更新", "user_id", identity.ID, "theme", row.Theme, "start_view", row.StartView)
	return &Preferences{Theme: row.Theme, StartView: row.StartView}, nil
}

func validTheme(theme string) bool {
	switch theme {
	case ThemeLight, ThemeDark, ThemeSystem:
		return true
	default:
		return false
	}
}

// GetPreferencesHandler 处理 GET /api/v1/me/preferences。
func GetPreferencesHandler(s *Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		token, ok := bearerToken(r.Header.Get("Authorization"))
		if !ok {
			writeUnauthorized(w, detailNotAuthenticated)
			return
		}
		prefs, err := s.GetPreferences(r.Context(), token)
		if err != nil {
			writePreferencesError(w, err)
			return
		}
		httpapi.WriteJSON(w, http.StatusOK, prefs)
	}
}

// PutPreferencesHandler 处理 PUT /api/v1/me/preferences。
func PutPreferencesHandler(s *Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		token, ok := bearerToken(r.Header.Get("Authorization"))
		if !ok {
			writeUnauthorized(w, detailNotAuthenticated)
			return
		}
		fields, problem := decodeJSONObject(r)
		if problem != "" {
			httpapi.WriteError(w, http.StatusBadRequest, problem)
			return
		}
		var problems []string
		theme, _, p := stringField(fields, "theme", true)
		problems = appendIf(problems, p)
		startView, _, p := stringField(fields, "start_view", true)
		problems = appendIf(problems, p)
		if len(problems) > 0 {
			httpapi.WriteError(w, http.StatusBadRequest, strings.Join(problems, "; "))
			return
		}

		prefs, err := s.PutPreferences(r.Context(), token, theme, startView)
		if err != nil {
			writePreferencesError(w, err)
			return
		}
		httpapi.WriteJSON(w, http.StatusOK, prefs)
	}
}

func writePreferencesError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, ErrUnauthenticated):
		writeUnauthorized(w, detailInvalidToken)
	case errors.Is(err, ErrInvalidTheme):
		httpapi.WriteError(w, http.StatusBadRequest, detailInvalidTheme)
	case errors.Is(err, ErrInvalidStartView):
		httpapi.WriteError(w, http.StatusBadRequest, detailInvalidStartView)
	default:
		httpapi.WriteError(w, http.StatusInternalServerError, detailInternalError)
	}
}
