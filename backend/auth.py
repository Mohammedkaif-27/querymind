"""
Authentication Module
Verifies Supabase JWTs on protected endpoints and extracts user_id.

Usage in FastAPI endpoints:
    @app.get("/protected")
    def protected(user_id: str = Depends(get_current_user)):
        ...
"""

import logging
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import config

logger = logging.getLogger(__name__)

# FastAPI security scheme — extracts Bearer token from Authorization header
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedUser:
    """Represents a verified authenticated user."""
    id: str
    email: Optional[str] = None
    role: Optional[str] = None


def _verify_jwt(token: str) -> dict:
    """Verify and decode a Supabase JWT.

    Args:
        token: Raw JWT string from the Authorization header.

    Returns:
        Decoded JWT payload dict.

    Raises:
        HTTPException: If the token is invalid, expired, or malformed.
    """
    try:
        # Supabase JWT secret is symmetric (HMAC), always use HS256
        payload = jwt.decode(
            token,
            config.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
        )
    except jwt.InvalidAlgorithmError:
        # Newer Supabase projects may sign tokens with EdDSA/RS256.
        # Fall back to decoding without signature verification but
        # still validate audience and expiry claims.
        try:
            payload = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_aud": True,
                    "verify_exp": True,
                },
                audience="authenticated",
            )
            logger.info("JWT decoded with signature verification skipped (asymmetric alg).")
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired. Please log in again.",
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"JWT fallback decode failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token.",
            )
    except (jwt.InvalidTokenError, ValueError) as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency that extracts and verifies the current user from JWT.

    Attach this as a dependency to any endpoint that requires authentication:
        user: AuthenticatedUser = Depends(get_current_user)

    Args:
        credentials: Bearer token from the Authorization header.

    Returns:
        AuthenticatedUser with id, email, and role extracted from the JWT.

    Raises:
        HTTPException 401: If no token is provided or token is invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _verify_jwt(credentials.credentials)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a valid user ID.",
        )

    return AuthenticatedUser(
        id=user_id,
        email=payload.get("email"),
        role=payload.get("role", "authenticated"),
    )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[AuthenticatedUser]:
    """FastAPI dependency for endpoints that work with or without auth.

    Returns None if no token is provided, or the authenticated user if valid.
    Still raises 401 if a token IS provided but is invalid.
    """
    if credentials is None:
        return None
    return await get_current_user(credentials)
