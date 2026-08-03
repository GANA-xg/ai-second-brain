import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.services.auth_logger import AuthEventLogger, RequestContext
from app.core.dependencies import get_current_active_user
from app.core.logging import get_logger
from app.core.rate_limiter import (
    login_limiter,
    register_limiter,
    refresh_limiter,
    logout_limiter,
)
from app.models.user import User

router = APIRouter(tags=["Authentication"])


def _build_request_context(request: Request) -> RequestContext:
    """Build a RequestContext from a FastAPI Request.

    Extracts client_ip from X-Forwarded-For header (when behind a reverse
    proxy) or falls back to request.client.host.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else "unknown")
    )
    return RequestContext(
        request_id=getattr(request.state, "request_id", "unknown"),
        client_ip=client_ip,
        user_agent=request.headers.get("User-Agent", ""),
        endpoint=f"{request.method} {request.url.path}",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: Request,
    data: RegisterRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(register_limiter),
):
    ctx = _build_request_context(request)
    try:
        return AuthService.register(db, data, ctx=ctx)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def login(
    request: Request,
    data: LoginRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(login_limiter),
):
    ctx = _build_request_context(request)
    try:
        return AuthService.login(db, data, ctx=ctx)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def refresh_token(
    request: Request,
    data: RefreshTokenRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(refresh_limiter),
):
    ctx = _build_request_context(request)
    try:
        return AuthService.refresh_token(db, data.refresh_token, ctx=ctx)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
def logout(
    request: Request,
    data: RefreshTokenRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(logout_limiter),
):
    ctx = _build_request_context(request)
    try:
        success = AuthService.logout(db, data.refresh_token, ctx=ctx)
        if success:
            return {"message": "Successfully logged out"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid refresh token",
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )


@router.post(
    "/logout-all",
    status_code=status.HTTP_200_OK,
)
def logout_all_devices(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    _: bool = Depends(logout_limiter),
):
    ctx = _build_request_context(request)
    try:
        user_id = str(current_user.id)
        count = AuthService.logout_all_devices(db, user_id, ctx=ctx)
        return {"message": f"Successfully logged out from {count} devices"}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
)
def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """Request a password reset token.

    In development mode (no SMTP), the token is returned in the response
    so it can be displayed to the user / logged. In production, this
    endpoint would always return a generic success message to prevent
    email enumeration.
    """
    raw_token = AuthService.forgot_password(db, data.email)
    logger = get_logger("auth.forgot_password")
    if raw_token:
        reset_link = f"{settings.APP_BASE_URL}/reset-password?token={raw_token}"
        logger.info(
            "Password reset requested",
            extra={"email": data.email, "reset_link": reset_link},
        )
        # Dev mode: return the token/link for easy testing
        return {
            "message": "If the email exists, a reset link has been sent.",
            "reset_link": reset_link,
            "token": raw_token,
        }
    logger.info(
        "Password reset requested for non-existent email",
        extra={"email": data.email},
    )
    return {
        "message": "If the email exists, a reset link has been sent.",
    }


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
)
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """Reset a user's password using a valid reset token."""
    try:
        AuthService.reset_password(db, data.token, data.new_password)
        return {"message": "Password has been reset successfully."}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_profile(
    current_user: User = Depends(get_current_active_user),
):
    """Get the current user's profile."""
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
)
def update_profile(
    data: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update the current user's profile."""
    if data.username is not None and data.username != current_user.username:
        existing = db.query(User).filter(
            User.username == data.username,
            User.id != current_user.id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )
        current_user.username = data.username
    if data.full_name is not None:
        current_user.full_name = data.full_name
    if data.bio is not None:
        current_user.bio = data.bio
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url

    db.commit()
    db.refresh(current_user)
    return current_user
