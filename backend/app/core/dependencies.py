import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, ExpiredSignatureError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.jwt import decode_token
from app.models.user import User
from app.core.exceptions import CredentialsException
from app.services.auth_logger import AuthEventLogger, RequestContext

# Security scheme
security = HTTPBearer()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Dependency to get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Build request context for audit logging
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else "unknown")
    )
    ctx = RequestContext(
        request_id=getattr(request.state, "request_id", "unknown"),
        client_ip=client_ip,
        user_agent=request.headers.get("User-Agent", ""),
        endpoint=f"{request.method} {request.url.path}",
    )

    try:
        token = credentials.credentials
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        if user_id is None or token_type != "access":
            AuthEventLogger.unauthorized_access(ctx, "Missing subject or invalid token type")
            raise credentials_exception

    except ValueError:
        # Token expired or invalid
        AuthEventLogger.access_token_validation_failure(ctx, "Token expired or invalid")
        raise credentials_exception
    except Exception:
        AuthEventLogger.unauthorized_access(ctx, "Token validation failed")
        raise credentials_exception

    user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if user is None:
        AuthEventLogger.unauthorized_access(ctx, "User not found")
        raise credentials_exception

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency to get the current active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    return current_user
