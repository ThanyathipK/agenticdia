"""
Authentication Routes.

Endpoints for user login, logout, token management, and password changes.

Every handler resolves accounts through
:class:`app.repositories.user.UserRepository` and verifies credentials through
:func:`app.auth.authenticate_user`, so the database is the single source of
truth for identity (no in-memory users, no token-claim-only trust).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    get_password_hash,
    change_password as auth_change_password,
    authenticate_user,
    AuthenticatedUser,
    get_current_user,
    UserResponse,
)
from app.config import settings
from app.database import get_db
from app.repositories.user import UserRepository, normalize_email

logger = logging.getLogger("app.routes.auth")

router = APIRouter()

# Minimum password length enforced by registration and password change. Kept in
# one constant so the two paths (and their error messages) cannot drift apart.
MIN_PASSWORD_LENGTH = 8

# Canonical user roles for the register endpoint (and the role dropdown in the
# frontend's sign-up form, src/api/types.ts AUTH_ROLES — keep the two lists in
# step). Registration rejects anything else so free-form strings like
# "auditor" or "" can never enter the users table.
VALID_ROLES = frozenset({
    "Business Analyst",
    "System Analyst",
    "Product Owner",
    "Technical Product Owner",
    "Project Manager",
    "Developer",
    "QA",
})


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class LoginResponse(BaseModel):
    """Response from successful login."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class PasswordChangeRequest(BaseModel):
    """Request to change password."""
    old_password: str
    new_password: str


class PasswordChangeResponse(BaseModel):
    """Response from successful password change."""
    message: str = "Password changed successfully"


class RegisterRequest(BaseModel):
    """Request to register a new user."""
    email: EmailStr
    password: str
    full_name: str
    role: str = "Business Analyst"


class RegisterResponse(BaseModel):
    """Response from successful registration."""
    message: str = "User registered successfully"
    user: UserResponse


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@router.post("/api/auth/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db),
):
    """
    Authenticate a user and return a JWT access token.
    
    Uses OAuth2 password flow. The username field is treated as email and is
    matched case-insensitively after trimming. Credential verification (and the
    "account has no password provisioned" diagnosis) lives in
    :func:`app.auth.authenticate_user`; this handler only issues the token.

    Raises:
        HTTPException 401: If credentials are invalid
    """
    user = await authenticate_user(form_data.username, form_data.password, session)

    access_token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
    )
    
    logger.info(f"User logged in: {user.email} (role: {user.role})")
    
    return LoginResponse(
        access_token=access_token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
        )
    )


# ---------------------------------------------------------------------------
# Current User / Auth Capabilities
# ---------------------------------------------------------------------------


@router.get("/api/auth/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def read_current_user(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Return the profile of the caller identified by the Bearer token.

    The token is re-resolved against the ``users`` table, so this doubles as the
    client-side "is my session still valid?" probe (401 once the account is gone
    or the token has expired).
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
    )


@router.get("/api/auth/config", status_code=status.HTTP_200_OK)
async def auth_config():
    """Public auth capabilities, so the UI can hide the sign-up form.

    Deliberately unauthenticated: the client must know whether registration is
    available BEFORE it holds a token.
    """
    return {
        "signup_enabled": settings.SIGNUP_ENABLED,
        "token_expiration_minutes": settings.JWT_EXPIRATION_MINUTES,
    }


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/api/auth/logout", status_code=status.HTTP_200_OK)
async def logout(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Logout the current user.
    
    Note: JWT tokens are stateless, so logout is primarily client-side.
    Server logs the event for audit purposes.
    """
    logger.info(f"User logged out: {current_user.email}")
    return {"message": "Successfully logged out"}


# ---------------------------------------------------------------------------
# Change Password
# ---------------------------------------------------------------------------


@router.post(
    "/api/auth/change-password",
    response_model=PasswordChangeResponse,
    status_code=status.HTTP_200_OK,
)
async def change_password_endpoint(
    password_request: PasswordChangeRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Change the current user's password with old password verification."""
    if len(password_request.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )

    await auth_change_password(
        user_id=current_user.id,
        old_password=password_request.old_password,
        new_password=password_request.new_password,
        session=session,
    )
    
    logger.info(f"Password changed for user: {current_user.email}")
    
    return PasswordChangeResponse(message="Password changed successfully")


# ---------------------------------------------------------------------------
# Register New User
# ---------------------------------------------------------------------------


@router.post(
    "/api/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    register_request: RegisterRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Register a new user account.

    Gated by ``SIGNUP_ENABLED`` (backend/.env): when false this endpoint is not
    exposed at all (403), so a shared/production deployment cannot be given new
    accounts by an anonymous caller. Uniqueness is enforced case-insensitively
    against the ``users`` table.

    Raises:
        HTTPException 403: If self-service signup is disabled.
        HTTPException 409: If an account with this email already exists.
    """
    if not settings.SIGNUP_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-service registration is disabled",
        )

    if len(register_request.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )

    # ROLE VALIDATION: only the canonical roles are accepted. Whitespace is
    # tolerated on input but the stored value is the exact canonical string.
    requested_role = register_request.role.strip()
    if requested_role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Allowed roles: " + ", ".join(sorted(VALID_ROLES)),
        )

    email = normalize_email(str(register_request.email))

    if await UserRepository.email_exists(email, session):
        logger.warning("Registration rejected — duplicate email: %s", email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    new_user = await UserRepository.create_user(
        email=email,
        full_name=register_request.full_name.strip(),
        role=requested_role,
        password_hash=get_password_hash(register_request.password),
        session=session,
    )
    await session.commit()
    await session.refresh(new_user)

    logger.info(f"New user registered: {new_user.email}")
    
    return RegisterResponse(
        message="User registered successfully",
        user=UserResponse(
            id=str(new_user.id),
            email=new_user.email,
            full_name=new_user.full_name,
            role=new_user.role,
        )
    )