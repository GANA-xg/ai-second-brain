"""
Authentication request/response schemas.

Uses a custom email type that skips DNS deliverability checks so
development, CI, and testing with reserved domains (example.com,
test.test) are not blocked.  The underlying email-validator library
still validates syntax (format, dot-atom, quoting, etc.).
"""
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from uuid import UUID


def _email_no_deliverability(v: str) -> str:
    """Validate email syntax without DNS deliverability check."""
    try:
        result = validate_email(v, check_deliverability=False)
        return result.email
    except EmailNotValidError as exc:
        raise ValueError(str(exc))


# Email field that validates syntax but skips MX/SPF lookup.
# Safe for development, test, and offline environments.
EmailField = Annotated[str, AfterValidator(_email_no_deliverability)]


class RegisterRequest(BaseModel):
    email: EmailField
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailField
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    is_active: bool


class ForgotPasswordRequest(BaseModel):
    email: EmailField


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
