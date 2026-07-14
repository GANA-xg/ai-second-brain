import hashlib

from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)


def hash_password(password: str) -> str:
    """
    Hash a plain-text password using bcrypt.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against its bcrypt hash.
    """
    return pwd_context.verify(plain_password, hashed_password)


def hash_token(token: str) -> str:
    """Deterministic SHA-256 hash of a token string.

    Unlike ``hash_password`` (bcrypt, salted, non-deterministic), this
    function always produces the same output for the same input, making
    it suitable for looking up stored tokens by their hash.

    Used for refresh-token storage and lookup.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
