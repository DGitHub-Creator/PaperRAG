"""Authentication HTTP routes."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
async def register(request: RegisterRequest, request_obj: Request, db: Session = Depends(get_db)):
    username = (request.username or "").strip()
    password = (request.password or "").strip()
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

    role = resolve_role(request.role, request.admin_code)
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
async def login(request: LoginRequest, request_obj: Request, db: Session = Depends(get_db)):
    user = authenticate_user(db, request.username, request.password)
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
    request: RefreshTokenRequest, request_obj: Request, db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(request.refresh_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            logger.warning("Refresh token type mismatch: %s", payload.get("type"))
            raise credentials_exception
        username: str | None = payload.get("sub")
        role: str | None = payload.get("role")
        if not username or not role:
            logger.warning("Refresh token is missing sub or role")
            raise credentials_exception
    except JWTError:
        logger.warning("Refresh token decode failed or token expired")
        raise credentials_exception

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
