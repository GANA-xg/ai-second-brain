import hashlib
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, hash_token, verify_password
from app.core.jwt import create_access_token, create_refresh_token, decode_token
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.schemas.auth import RegisterRequest, LoginRequest
from app.services.auth_logger import AuthEventLogger, RequestContext


class AuthService:
    @staticmethod
    def register(
        db: Session,
        data: RegisterRequest,
        ctx: Optional[RequestContext] = None,
    ) -> User:
        start = time.time()

        existing_user = (
            db.query(User)
            .filter(User.email == data.email)
            .first()
        )

        if existing_user:
            if ctx:
                AuthEventLogger.register_failure(ctx, "Email already registered", time.time() - start)
            raise ValueError("Email already registered")

        user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        if ctx:
            AuthEventLogger.register_success(
                ctx, str(user.id), user.email, time.time() - start
            )

        return user

    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> User | None:
        """Authenticate a user with email and password.

        Returns the user object if credentials are valid, None otherwise.
        """
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    def login(
        db: Session,
        data: LoginRequest,
        ctx: Optional[RequestContext] = None,
    ) -> dict:
        """Authenticate user and generate access and refresh tokens.

        Returns a dictionary with access_token, refresh_token, and token_type.
        """
        start = time.time()

        # Check if user exists
        user = db.query(User).filter(User.email == data.email).first()
        if not user:
            if ctx:
                AuthEventLogger.login_invalid_email(ctx, data.email, time.time() - start)
            raise ValueError("Incorrect email or password")

        # Verify password
        if not verify_password(data.password, user.hashed_password):
            if ctx:
                AuthEventLogger.login_invalid_password(ctx, data.email, time.time() - start)
            raise ValueError("Incorrect email or password")

        if not user.is_active:
            if ctx:
                AuthEventLogger.login_failure(ctx, data.email, "Account is inactive", time.time() - start)
            raise ValueError("Account is inactive")

        # Create access token
        access_token = create_access_token(subject=str(user.id))

        # Create refresh token
        refresh_token = create_refresh_token(subject=str(user.id))

        # Hash the refresh token for storage
        refresh_token_hash = hash_token(refresh_token)

        # Store the hashed refresh token in database
        refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )

        db.add(refresh_token_record)
        db.commit()
        db.refresh(refresh_token_record)

        if ctx:
            AuthEventLogger.login_success(
                ctx, str(user.id), user.email, time.time() - start
            )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    @staticmethod
    def refresh_token(
        db: Session,
        refresh_token: str,
        ctx: Optional[RequestContext] = None,
    ) -> dict:
        """Generate new access and refresh tokens using a valid refresh token.

        Implements refresh token rotation for security.
        Returns a dictionary with new access_token, new refresh_token, and token_type.
        """
        start = time.time()

        try:
            # Decode the refresh token to get user ID
            payload = decode_token(refresh_token)
            user_id = payload.get("sub")
            token_type = payload.get("type")

            if token_type != "refresh":
                raise ValueError("Invalid token type")

            if not user_id:
                raise ValueError("Invalid token: missing subject")

        except ValueError as e:
            if ctx:
                AuthEventLogger.refresh_failure(ctx, str(e), time.time() - start)
            raise ValueError(f"Invalid refresh token: {str(e)}")

        # Find the refresh token in database by checking the hash
        token_hash = hash_token(refresh_token)

        stored_token = db.query(RefreshToken).filter(
            and_(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
        ).first()

        if not stored_token:
            # Check if this is a replay attack (token used after revocation)
            revoked_token = db.query(RefreshToken).filter(
                and_(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.revoked_at.isnot(None),
                )
            ).first()

            if revoked_token:
                # Token has been revoked — potential replay attack
                # Revoke all tokens for this user as a security measure
                user_id_from_token = revoked_token.user_id
                if ctx:
                    AuthEventLogger.refresh_replay_attack(
                        ctx, str(user_id_from_token), time.time() - start
                    )
                AuthService._revoke_all_user_tokens(db, user_id_from_token)
                raise ValueError("Refresh token revoked due to suspected replay attack")
            else:
                if ctx:
                    AuthEventLogger.refresh_failure(ctx, "Token not found or expired", time.time() - start)
                raise ValueError("Refresh token not found or expired")

        # Get the user
        user = db.query(User).filter(User.id == stored_token.user_id).first()
        if not user or not user.is_active:
            if ctx:
                AuthEventLogger.refresh_failure(ctx, "User not found or inactive", time.time() - start)
            raise ValueError("User not found or inactive")

        # Rotate the refresh token: mark current token as replaced/revoked
        stored_token.revoked_at = datetime.now(timezone.utc)

        # Create new access token
        new_access_token = create_access_token(subject=str(user.id))

        # Create new refresh token
        new_refresh_token = create_refresh_token(subject=str(user.id))
        new_refresh_token_hash = hash_token(new_refresh_token)

        # Store new refresh token
        new_refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=new_refresh_token_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )

        db.add(new_refresh_token_record)
        db.commit()
        db.refresh(new_refresh_token_record)

        if ctx:
            AuthEventLogger.refresh_success(ctx, str(user.id), time.time() - start)

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        }

    @staticmethod
    def logout(
        db: Session,
        refresh_token: str,
        ctx: Optional[RequestContext] = None,
    ) -> bool:
        """Revoke a refresh token (logout from one device).

        Returns True if successful.
        """
        start = time.time()

        try:
            payload = decode_token(refresh_token)
            token_type = payload.get("type")

            if token_type != "refresh":
                if ctx:
                    AuthEventLogger.logout_failure(
                        ctx, "unknown", "Invalid token type", time.time() - start
                    )
                raise ValueError("Invalid token type")

        except ValueError as e:
            raise ValueError(f"Invalid refresh token: {str(e)}")

        # Find the refresh token in database by checking the hash
        token_hash = hash_token(refresh_token)

        stored_token = db.query(RefreshToken).filter(
            and_(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
        ).first()

        if not stored_token:
            return False  # Token not found or already revoked

        user_id = stored_token.user_id

        # Revoke the token
        stored_token.revoked_at = datetime.now(timezone.utc)
        db.commit()

        if ctx:
            ctx.user_id = str(user_id)
            AuthEventLogger.logout(ctx, str(user_id), time.time() - start)

        return True

    @staticmethod
    def logout_all_devices(
        db: Session,
        user_id: str,
        ctx: Optional[RequestContext] = None,
    ) -> int:
        """Revoke all refresh tokens for a user (logout from all devices).

        Returns the number of tokens revoked.
        """
        start = time.time()

        # Convert string to UUID
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise ValueError("Invalid user ID format")

        # Revoke all active refresh tokens for the user
        result = db.query(RefreshToken).filter(
            and_(
                RefreshToken.user_id == user_uuid,
                RefreshToken.revoked_at.is_(None),
            )
        ).update({RefreshToken.revoked_at: datetime.now(timezone.utc)})

        db.commit()

        if ctx:
            AuthEventLogger.logout_all(ctx, user_id, result, time.time() - start)

        return result

    @staticmethod
    def _revoke_all_user_tokens(db: Session, user_id: uuid.UUID) -> None:
        """Revoke all active refresh tokens for a user."""
        db.query(RefreshToken).filter(
            and_(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
        ).update({RefreshToken.revoked_at: datetime.now(timezone.utc)})
        db.commit()

    @staticmethod
    def forgot_password(
        db: Session,
        email: str,
    ) -> str:
        """Generate a password reset token for the given email.

        In development mode (no SMTP), returns the raw token so it can be
        logged/displayed. In production with SMTP, this would send an email.

        Args:
            db: Database session.
            email: User's email address.

        Returns:
            The raw reset token (for dev email backend).
        """
        user = db.query(User).filter(User.email == email).first()
        if not user:
            # Don't reveal whether the email exists
            return ""

        # Generate a cryptographically secure token
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        # Store hashed token with expiry
        user.password_reset_token_hash = token_hash
        user.password_reset_token_expires_at = datetime.now(timezone.utc) + timedelta(
            hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
        )
        db.commit()

        return raw_token

    @staticmethod
    def reset_password(
        db: Session,
        token: str,
        new_password: str,
    ) -> None:
        """Reset a user's password using a valid reset token.

        Args:
            db: Database session.
            token: The raw reset token.
            new_password: The new password to set.

        Raises:
            ValueError: If the token is invalid, expired, or no user has it.
        """
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        now = datetime.now(timezone.utc)

        user = db.query(User).filter(
            User.password_reset_token_hash == token_hash,
            User.password_reset_token_expires_at > now,
        ).first()

        if not user:
            raise ValueError("Invalid or expired reset token")

        # Update password and clear reset token
        user.hashed_password = hash_password(new_password)
        user.password_reset_token_hash = None
        user.password_reset_token_expires_at = None
        db.commit()
