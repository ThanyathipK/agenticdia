"""
Authentication and Authorization Module.

Provides JWT-based authentication with:
- Token creation and verification
- User dependency injection for routes
- Project ownership validation
- Role-based access control helpers
"""
import logging
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from jose import JWTError, jwt

from app.config import settings
from app.database import get_db
from app.models import ProjectModel, UserModel
from app.repositories.base import as_uuid
from app.repositories.user import UserRepository, normalize_email

logger = logging.getLogger("app.auth")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Development-only fallback secret (never used once backend/.env sets a real
# JWT_SECRET_KEY — unfilled placeholders count as unset; see resolver below).
DEV_JWT_SECRET = "dev-secret-change-in-production-2026-agenticdia"


def _resolve_jwt_secret() -> str:
    """
    Resolve the JWT signing secret from settings (backend/.env).

    Empty values and unfilled template placeholders fall back to the
    development secret with a loud warning so local development still boots,
    while a real (but weak) secret is honored with a hardening warning.
    """
    configured = (settings.JWT_SECRET_KEY or "").strip()
    if not configured or configured.startswith("[YOUR_"):
        warnings.warn(
            "JWT_SECRET_KEY is unset (or still a template placeholder). "
            "Falling back to the development secret — set a strong "
            "JWT_SECRET_KEY in backend/.env for anything beyond local dev.",
            RuntimeWarning,
            stacklevel=2,
        )
        logger.warning(
            "JWT_SECRET_KEY is unset or a placeholder. Set a strong "
            "JWT_SECRET_KEY in backend/.env for production."
        )
        return DEV_JWT_SECRET
    if len(configured) < 32:
        warnings.warn(
            "JWT_SECRET_KEY is shorter than 32 characters. "
            "Use e.g. `openssl rand -hex 32` for production.",
            RuntimeWarning,
            stacklevel=2,
        )
        logger.warning(
            "JWT_SECRET_KEY is weak (< 32 chars). Strengthen it for production."
        )
    return configured


JWT_SECRET_KEY = _resolve_jwt_secret()
JWT_ALGORITHM = "HS256"
# backend/.env exposes the TTL as JWT_EXPIRATION_MINUTES (the previously-read
# ACCESS_TOKEN_EXPIRE_MINUTES name was never wired to .env).
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_EXPIRATION_MINUTES

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)

security_scheme = HTTPBearer()

# ---------------------------------------------------------------------------
# Password Handling
# ---------------------------------------------------------------------------


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Returns ``False`` (instead of raising) when the stored hash is empty or
    not a recognizable bcrypt hash — e.g. rows seeded before the
    ``password_hash`` column existed carry an empty string, and passlib raises
    ``UnknownHashError``/``ValueError`` for anything malformed.
    """
    if not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        logger.warning("Stored password hash is not a valid bcrypt hash")
        return False


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def password_hash_is_usable(hashed_password: Optional[str]) -> bool:
    """Return True when *hashed_password* is a non-empty stored hash.

    Used by the bootstrap seeder and the login route to tell "this account has
    no password yet" (unusable, must be provisioned) apart from "the supplied
    password is wrong" (a real 401), so operators get an actionable log line
    instead of a permanent, unexplainable 401.
    """
    return bool((hashed_password or "").strip())


async def change_password(
    user_id: str,
    old_password: str,
    new_password: str,
    session: AsyncSession,
) -> None:
    """
    Change a user's password after verifying the old password.

    Args:
        user_id: ID of the user whose password is being changed.
        old_password: Current plaintext password (must verify).
        new_password: New plaintext password (stored bcrypt-hashed).
        session: Active database session (committed on success).

    Raises:
        HTTPException 400: If the user does not exist or the old
            password is incorrect.
    """
    user = await UserRepository.get_by_id(user_id, session)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found",
        )

    if not verify_password(old_password, user.password_hash):
        logger.warning(
            "Failed password change (wrong old password) for user %s", user_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect",
        )

    await UserRepository.set_password_hash(user, get_password_hash(new_password), session)
    await session.commit()
    logger.info("Password changed for user: %s", user.email)


async def authenticate_user(
    email: str,
    password: str,
    session: AsyncSession,
) -> UserModel:
    """Verify credentials against the ``users`` table.

    The single login path: resolves the account (case-insensitive,
    whitespace-trimmed email) and verifies the bcrypt hash. Raises a generic
    401 for both "unknown account" and "wrong password" so the endpoint never
    confirms which emails exist, while logging the distinction for operators.

    A row with an EMPTY ``password_hash`` (the pre-0013 seeded shape) is
    reported as a provisioning problem rather than a bad password — otherwise
    the bootstrap account would be permanently un-loginable with no clue why.

    Raises:
        HTTPException 401: If the account does not exist, has no password
            provisioned, or the password does not verify.
    """
    normalized = normalize_email(email)
    user = await UserRepository.get_by_email(normalized, session)

    if user is None:
        logger.warning("Login attempt for non-existent user: %s", normalized)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not password_hash_is_usable(user.password_hash):
        logger.error(
            "Account %s has no password hash provisioned in the database. "
            "Set SYSTEM_USER_PASSWORD in backend/.env (the startup seeder "
            "back-fills the bootstrap account) or register/rotate a password "
            "for this account.",
            user.email,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(password, user.password_hash):
        logger.warning("Failed login attempt for user: %s", user.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# ---------------------------------------------------------------------------
# JWT Token Handling
# ---------------------------------------------------------------------------


class TokenData(BaseModel):
    """Data embedded in a JWT token."""
    user_id: str
    email: str
    role: str
    exp: Optional[datetime] = None


class AuthenticatedUser(BaseModel):
    """Represents an authenticated user derived from a JWT token."""
    id: str
    email: str
    full_name: str
    role: str

    class Config:
        from_attributes = True


def create_access_token(
    user_id: str,
    email: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a new JWT access token for a user."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


# ---------------------------------------------------------------------------
# Token Verification
# ---------------------------------------------------------------------------


def verify_token(token: str) -> TokenData:
    """Verify and decode a JWT token, returning the TokenData payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        role: str = payload.get("role")
        if user_id is None or email is None or role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return TokenData(user_id=user_id, email=email, role=role)
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# Dependency Injection — Get Current User
# ---------------------------------------------------------------------------


def to_authenticated_user(user: UserModel) -> AuthenticatedUser:
    """Project a :class:`UserModel` row onto the public auth identity.

    Single conversion point so ``password_hash`` (and any future sensitive
    column) can never leak into the token-derived identity used by routes.
    """
    return AuthenticatedUser(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    session: AsyncSession = Depends(get_db),
) -> AuthenticatedUser:
    """
    Dependency that extracts and validates the JWT Bearer token from the
    Authorization header, then fetches the corresponding user from the DB.

    Returns an :class:`AuthenticatedUser` — the safe public projection of
    the user row — for the authenticated caller.

    The database is the source of truth: a token whose signature is valid but
    whose ``sub`` no longer resolves to a row (deleted account, wrong
    environment's secret, truncated ``sub``) is rejected with 401 rather than
    trusted on the token's own claims.

    Note: the users table currently has no ``is_active`` column, so no
    disabled-account check is performed here. Re-add one (plus a migration)
    if account suspension is introduced.
    """
    token_data = verify_token(credentials.credentials)

    user = await UserRepository.get_by_id(token_data.user_id, session)

    if user is None:
        logger.warning(
            "Rejected token for unknown user id: %s", token_data.user_id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return to_authenticated_user(user)


# ---------------------------------------------------------------------------
# Optional Auth (for routes that allow anonymous access but support auth)
# ---------------------------------------------------------------------------


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_db),
) -> Optional[AuthenticatedUser]:
    """
    Optional authentication dependency. Returns an :class:`AuthenticatedUser`
    if a valid token is provided, or None if no token/invalid token.
    """
    if credentials is None:
        return None

    try:
        token_data = verify_token(credentials.credentials)
    except HTTPException:
        return None

    user = await UserRepository.get_by_id(token_data.user_id, session)
    if user is None:
        return None

    return to_authenticated_user(user)


# ---------------------------------------------------------------------------
# User Response Schemas
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Public user information returned by auth endpoints."""
    id: str
    email: str
    full_name: str
    role: str
    # The users table has no ``is_active`` column yet; default keeps the
    # schema stable until account suspension is actually introduced.
    is_active: bool = True
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserMinimalResponse(BaseModel):
    """Minimal user info (e.g., for project ownership references)."""
    id: str
    email: str
    full_name: str
    
    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Project Ownership Helpers
# ---------------------------------------------------------------------------


async def require_project_owner(
    project_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AuthenticatedUser:
    """
    Dependency that verifies the current user owns the specified project.
    Raises 403 if the user does not own the project.
    """
    try:
        project_key = as_uuid(project_id)
    except (AttributeError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    result = await session.execute(
        select(ProjectModel).where(ProjectModel.id == project_key)
    )
    project = result.scalar_one_or_none()
    
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    
    if str(project.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this project",
        )
    
    return current_user
