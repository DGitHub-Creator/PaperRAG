"""认证接口的请求与响应模型。"""

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    """用户注册请求。

    Fields:
        username: 用户名（必填，非空）。
        password: 密码（必填，非空）。
        role: 可选角色，默认为 "user"。可通过 admin_code 升级为 "admin"。
        admin_code: 管理员邀请码，匹配 ADMIN_INVITE_CODE 时角色设为 admin。
    """
    username: str
    password: str
    role: str | None = "user"
    admin_code: str | None = None



class LoginRequest(BaseModel):
    """用户登录请求。

    Fields:
        username: 用户名。
        password: 密码。
    """
    username: str
    password: str



class AuthResponse(BaseModel):
    """认证成功响应（注册/登录通用）。

    Fields:
        access_token: JWT 访问令牌。
        refresh_token: JWT 刷新令牌。
        token_type: 令牌类型，固定为 "bearer"。
        username: 用户名。
        role: 用户角色（"user" 或 "admin"）。
    """
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    username: str
    role: str



class RefreshTokenRequest(BaseModel):
    """刷新令牌请求。

    Fields:
        refresh_token: 有效的 Refresh Token。
    """
    refresh_token: str



class CurrentUserResponse(BaseModel):
    """当前登录用户信息响应。

    Fields:
        username: 用户名。
        role: 用户角色。
    """
    username: str
    role: str

