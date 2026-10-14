// Package httpapi 是 go-api 的 HTTP 门面：Chi 路由、中间件与错误信封。
package httpapi

import (
	"encoding/json"
	"log/slog"
	"net/http"
)

// 错误信封与 Python 侧保持一致：非 2xx 一律 {"detail": ...}（01 §6）。
// 具体文案沿用 FastAPI/Starlette 的现状，形状由 P0-4 的 contracts/error-codes.md 正式锁定，
// 这里不提前发明更丰富的错误体——那会让跨语言契约测试各验一套。

// 两句要在多个业务包里复用的对外文案，唯一副本放在信封的归属层。
// 同一个服务里出现两种 500 文案正是 `01 §6.3` 记过的坑（台账 C23），
// 所以 internal/auth 与后面的每个接管包都从这里取，而不是各写一遍字面量。
const (
	DetailInternalError    = "Internal server error"
	DetailNotAuthenticated = "Not authenticated"
)

// WriteJSON 输出响应体。编码失败只可能发生在连接已断时，记 debug 后忽略。
func WriteJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(body); err != nil {
		slog.Debug("响应编码失败", "error", err)
	}
}

// WriteError 输出 {"detail": detail}。detail 可以是字符串，也可以是结构化对象。
func WriteError(w http.ResponseWriter, status int, detail any) {
	WriteJSON(w, status, struct {
		Detail any `json:"detail"`
	}{Detail: detail})
}

// NotFound 给 Chi 当 NotFoundHandler，保证 404 也带信封。
func NotFound(w http.ResponseWriter, _ *http.Request) {
	WriteError(w, http.StatusNotFound, "Not Found")
}

// MethodNotAllowed 给 Chi 当 MethodNotAllowedHandler。
func MethodNotAllowed(w http.ResponseWriter, _ *http.Request) {
	WriteError(w, http.StatusMethodNotAllowed, "Method Not Allowed")
}
