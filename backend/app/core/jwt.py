

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import uuid4

from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = settings.ALGORITHM
SECRET_KEY = settings.SECRET_KEY


def _create_token(data: Dict[str, Any], expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": uuid4().hex,
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(subject: str) -> str:
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(
        {
            "sub": subject,
            "type": "access",
        },
        expires,
    )


def create_refresh_token(subject: str) -> str:
    expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _create_token(
        {
            "sub": subject,
            "type": "refresh",
        },
        expires,
    )


def decode_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc