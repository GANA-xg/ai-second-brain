"""
Structured authentication event logging.

Logs all authentication events with consistent structure for audit trails,
security monitoring, and incident response.

Events logged:
- Registration (success / failure)
- Login (success / failure)
- Login failure by reason (invalid email, invalid password)
- Access token validation failure
- Token refresh (success / failure)
- Refresh replay attack detection
- Logout (single / all devices)
- Revoked token usage
- Unauthorized access attempts
- Expired token usage

Never logs: passwords, JWT tokens, refresh tokens, or secrets.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.core.logging import get_logger

logger = get_logger("auth")


@dataclass
class RequestContext:
    """Request context extracted from an incoming HTTP request.

    Passed through to the auth service and logger to enrich audit events.
    Never contains secrets, tokens, or passwords.
    """

    request_id: str
    client_ip: str
    user_agent: str
    endpoint: str
    user_id: Optional[str] = None
    email: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "endpoint": self.endpoint,
            "user_id": self.user_id,
            "email": self.email,
        }


class AuthEventLogger:
    """Structured auth event logger.

    Usage:
        AuthEventLogger.login_success(ctx, user_id="uuid", email="a@b.com", latency=0.05)
    """

    EVENT_REGISTER = "auth.register"
    EVENT_LOGIN = "auth.login"
    EVENT_REFRESH = "auth.refresh"
    EVENT_LOGOUT = "auth.logout"
    EVENT_LOGOUT_ALL = "auth.logout_all"
    EVENT_REPLAY = "auth.replay_attack"
    EVENT_REVOKED = "auth.revoked_token"
    EVENT_UNAUTHORIZED = "auth.unauthorized"
    EVENT_EXPIRED = "auth.expired_token"

    @staticmethod
    def _log(
        event: str,
        outcome: str,
        ctx: RequestContext,
        extra: Optional[Dict[str, Any]] = None,
        latency: Optional[float] = None,
    ) -> None:
        """Emit a structured log entry for an auth event.

        Args:
            event: Event identifier (e.g. 'auth.login').
            outcome: One of 'success', 'failure', 'blocked', 'attack_blocked'.
            ctx: Request context with request_id, client_ip, user_agent, etc.
            extra: Additional event-specific key-value data (no secrets).
            latency: Request processing time in seconds.
        """
        data: Dict[str, Any] = {
            "outcome": outcome,
            "request_id": ctx.request_id,
            "client_ip": ctx.client_ip,
            "user_agent": ctx.user_agent,
            "endpoint": ctx.endpoint,
        }

        if ctx.user_id:
            data["user_id"] = ctx.user_id
        if ctx.email:
            data["email"] = ctx.email
        if extra:
            # Defensive: ensure no secrets leak through extra
            blocked_keys = {"password", "token", "secret", "jwt", "hash"}
            for k, v in extra.items():
                if k.lower() not in blocked_keys:
                    data[k] = v
        if latency is not None:
            data["latency_ms"] = round(latency * 1000, 2)

        if outcome == "success":
            logger.info(event, **data)
        elif outcome in ("failure", "blocked"):
            logger.warning(event, **data)
        else:  # attack_blocked, error
            logger.error(event, **data)

    # -- Registration --

    @classmethod
    def register_success(cls, ctx: RequestContext, user_id: str, email: str, latency: float) -> None:
        ctx.user_id = user_id
        ctx.email = email
        cls._log(cls.EVENT_REGISTER, "success", ctx, latency=latency)

    @classmethod
    def register_failure(cls, ctx: RequestContext, reason: str, latency: float) -> None:
        cls._log(cls.EVENT_REGISTER, "failure", ctx, extra={"reason": reason}, latency=latency)

    # -- Login --

    @classmethod
    def login_success(cls, ctx: RequestContext, user_id: str, email: str, latency: float) -> None:
        ctx.user_id = user_id
        ctx.email = email
        cls._log(cls.EVENT_LOGIN, "success", ctx, latency=latency)

    @classmethod
    def login_failure(cls, ctx: RequestContext, email: str, reason: str, latency: float) -> None:
        ctx.email = email
        cls._log(cls.EVENT_LOGIN, "failure", ctx, extra={"reason": reason, "email": email}, latency=latency)

    @classmethod
    def login_invalid_email(cls, ctx: RequestContext, email: str, latency: float) -> None:
        ctx.email = email
        cls._log(cls.EVENT_LOGIN, "failure", ctx, extra={"reason": "invalid_email", "email": email}, latency=latency)

    @classmethod
    def login_invalid_password(cls, ctx: RequestContext, email: str, latency: float) -> None:
        ctx.email = email
        cls._log(cls.EVENT_LOGIN, "failure", ctx, extra={"reason": "invalid_password", "email": email}, latency=latency)

    # -- Token refresh --

    @classmethod
    def refresh_success(cls, ctx: RequestContext, user_id: str, latency: float) -> None:
        ctx.user_id = user_id
        cls._log(cls.EVENT_REFRESH, "success", ctx, latency=latency)

    @classmethod
    def refresh_failure(cls, ctx: RequestContext, reason: str, latency: float) -> None:
        cls._log(cls.EVENT_REFRESH, "failure", ctx, extra={"reason": reason}, latency=latency)

    @classmethod
    def refresh_replay_attack(cls, ctx: RequestContext, user_id: str, latency: float) -> None:
        ctx.user_id = user_id
        cls._log(cls.EVENT_REPLAY, "attack_blocked", ctx, extra={"user_id": user_id}, latency=latency)

    # -- Logout --

    @classmethod
    def logout(cls, ctx: RequestContext, user_id: str, latency: float) -> None:
        ctx.user_id = user_id
        cls._log(cls.EVENT_LOGOUT, "success", ctx, latency=latency)

    @classmethod
    def logout_failure(cls, ctx: RequestContext, user_id: str, reason: str, latency: float) -> None:
        ctx.user_id = user_id
        cls._log(cls.EVENT_LOGOUT, "failure", ctx, extra={"reason": reason}, latency=latency)

    @classmethod
    def logout_all(cls, ctx: RequestContext, user_id: str, count: int, latency: float) -> None:
        ctx.user_id = user_id
        cls._log(cls.EVENT_LOGOUT_ALL, "success", ctx, extra={"tokens_revoked": count}, latency=latency)

    # -- Security events --

    @classmethod
    def unauthorized_access(cls, ctx: RequestContext, reason: str) -> None:
        cls._log(cls.EVENT_UNAUTHORIZED, "blocked", ctx, extra={"reason": reason})

    @classmethod
    def expired_token(cls, ctx: RequestContext, reason: str) -> None:
        cls._log(cls.EVENT_EXPIRED, "blocked", ctx, extra={"reason": reason})

    @classmethod
    def revoked_token_usage(cls, ctx: RequestContext, reason: str) -> None:
        cls._log(cls.EVENT_REVOKED, "blocked", ctx, extra={"reason": reason})

    @classmethod
    def access_token_validation_failure(cls, ctx: RequestContext, reason: str) -> None:
        cls._log(cls.EVENT_UNAUTHORIZED, "blocked", ctx, extra={"reason": f"access_token: {reason}"})
