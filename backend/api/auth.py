"""Authentication HTTP routes."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.core.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_db,
    get_password_hash,
    resolve_role,
)
from backend.core.config import JWT_ALGORITHM, JWT_SECRET_KEY, MIN_PASSWORD_LENGTH
from backend.core.logging_config import get_logger
from backend.core.models import User
from backend.core.rate_limit import limiter
from backend.schemas.schemas import (
    AuthResponse,
    CurrentUserResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
)

router = APIRouter()
logger = get_logger(__name__)


@router.post("/auth/register", response_model=AuthResponse)
@limiter.limit("10/minute")
async def register(
    request: Request, response: Response, body: RegisterRequest, db: Session = Depends(get_db)
):
    # `request` / `response` 这两个名字是 slowapi 的硬要求（它按 kwargs 取注入对象，
    # headers_enabled=True 时要往 response 上写 X-RateLimit-*），请求体因此只能叫 `body`。
    # 形状由 tests/unit/test_rate_limit_signatures.py 机检——名字写错时合法请求会全 500，
    # 而 body 不合法的用例反而在 422 阶段就返回，测不出来。
    username = (body.username or "").strip()
    password = (body.password or "").strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    if MIN_PASSWORD_LENGTH > 0 and len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )

    categories = sum(
        [
            bool(re.search(r"[a-z]", password)),
            bool(re.search(r"[A-Z]", password)),
            bool(re.search(r"\d", password)),
        ]
    )
    if MIN_PASSWORD_LENGTH > 0 and categories < 2:
        raise HTTPException(
            status_code=400,
            detail="Password must include at least two of lowercase, uppercase, and digits",
        )

    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(status_code=409, detail="Username already exists")

    role = resolve_role(body.role, body.admin_code)
    user = User(username=username, password_hash=get_password_hash(password), role=role)
    db.add(user)
    db.commit()

    access_token = create_access_token(username=username, role=role)
    refresh_token = create_refresh_token(username=username, role=role)
    logger.info("User registered: username=%s, role=%s", username, role)
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        username=username,
        role=role,
    )


@router.post("/auth/login", response_model=AuthResponse)
@limiter.limit("20/minute")
async def login(request: Request, response: Response, body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token = create_access_token(username=user.username, role=user.role)
    refresh_token = create_refresh_token(username=user.username, role=user.role)
    logger.info("User logged in: username=%s", user.username)
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        username=user.username,
        role=user.role,
    )


@router.get("/auth/me", response_model=CurrentUserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return CurrentUserResponse(username=current_user.username, role=current_user.role)


@router.post("/auth/refresh", response_model=AuthResponse)
@limiter.limit("20/minute")
async def refresh_token(
    request: Request, response: Response, body: RefreshTokenRequest, db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = jwt.decode(body.refresh_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if claims.get("type") != "refresh":
            logger.warning("Refresh token type mismatch: %s", claims.get("type"))
            raise credentials_exception
        username: str | None = claims.get("sub")
        role: str | None = claims.get("role")
        if not username or not role:
            logger.warning("Refresh token is missing sub or role")
            raise credentials_exception
    except JWTError:
        logger.warning("Refresh token decode failed or token expired")
        raise credentials_exception from None

    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.warning("Refresh token user does not exist: %s", username)
        raise credentials_exception

    new_access = create_access_token(username=user.username, role=user.role)
    new_refresh = create_refresh_token(username=user.username, role=user.role)
    logger.info("Token refreshed: username=%s", user.username)
    return AuthResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        username=user.username,
        role=user.role,
    )
