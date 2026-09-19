"""
GHOST — authentication API (M2).

POST /api/auth/login    passphrase -> session token
GET  /api/auth/session  verify a token, read expiry
DELETE /api/auth/session logout (revoke)

Login is rate-limited per client IP to slow brute
force. Password comparison is constant-time.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import secrets

from backend.core.security import (
    get_auth_password,
    get_rate_limits,
    rate_limiter,
    session_store,
)


logger = logging.getLogger(
    "ghost.auth",
)


router = APIRouter(
    prefix="/api/auth",
    tags=["Auth"],
)


class LoginRequest(BaseModel):

    password: str


@router.post("/login")
async def login(
    request: LoginRequest,
    http_request: Request,
):
    # ----------------------------------------------------
    # Rate limit BEFORE touching the password check:
    # brute force attempts burn the limit regardless of
    # whether the guess is right.
    # ----------------------------------------------------

    client_ip = (
        http_request.client.host
        if http_request.client
        else "unknown"
    )

    limits = get_rate_limits()

    allowed, retry_after = rate_limiter.check(
        f"login:{client_ip}",
        limits["login"],
    )

    if not allowed:

        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
            headers={
                "Retry-After": str(
                    int(retry_after),
                ),
            },
        )

    # ----------------------------------------------------
    # Constant-time comparison
    # ----------------------------------------------------

    supplied = request.password.strip()

    configured = get_auth_password()

    if (
        not configured
        or not supplied
        or not secrets.compare_digest(
            supplied.encode(),
            configured.encode(),
        )
    ):

        logger.warning(
            "Failed login attempt from %s",
            client_ip,
        )

        raise HTTPException(
            status_code=401,
            detail="Invalid password.",
        )

    session = session_store.create()

    logger.info(
        "Session issued for %s (expires %s)",
        client_ip,
        session.expires_at,
    )

    return {
        "token": session.token,
        "token_type": "bearer",
        "expires_at": session.expires_at,
    }


@router.get("/session")
async def session_info(http_request: Request):
    """
    Frontend uses this to validate a stored token on
    page load. The auth middleware has already verified
    the token by the time this runs.
    """

    token = getattr(
        http_request.state,
        "session_token",
        None,
    )

    session = session_store.get_valid(token)

    if session is None:

        raise HTTPException(
            status_code=401,
            detail="Session no longer valid.",
        )

    return {
        "valid": True,
        "expires_at": session.expires_at,
    }


@router.delete("/session")
async def logout(http_request: Request):
    """
    Revoke the current session. Requires a valid token
    (enforced by middleware), so logout cannot be used
    to probe token validity for arbitrary tokens.
    """

    token = getattr(
        http_request.state,
        "session_token",
        None,
    )

    revoked = session_store.revoke(token)

    return {
        "revoked": revoked,
    }
