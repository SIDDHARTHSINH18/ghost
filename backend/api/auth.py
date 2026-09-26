"""
GHOST — authentication API (M2).

POST /api/auth/login    passphrase -> session token
GET  /api/auth/session  verify a token, read expiry
DELETE /api/auth/session logout (revoke)

Login is rate-limited per client IP to slow brute
force. Password comparison is constant-time.
"""

import logging
import os

from typing import Optional

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


class SetupRequest(BaseModel):

    passphrase: str
    confirm: str


MIN_PASSPHRASE_LENGTH = 8


def _setup_pending() -> bool:
    """
    True only while the packaged first-run bootstrap is in
    effect: the desktop layer created config.env with a
    generated bootstrap credential and marked it as awaiting
    the user's own passphrase.
    """

    return (
        os.getenv("ENMA_SETUP_PENDING") == "1"
        and bool(os.getenv("ENMA_CONFIG_PATH"))
        and os.path.isfile(os.getenv("ENMA_CONFIG_PATH", ""))
    )


def _persist_passphrase(passphrase: str) -> None:
    """
    Replace GHOST_AUTH_PASSWORD in the user's private config
    file and clear the setup-pending marker, preserving every
    other configuration line (provider keys etc.).
    """

    config_path = os.environ["ENMA_CONFIG_PATH"]

    with open(config_path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    rewritten = []

    for line in lines:
        if line.startswith("ENMA_SETUP_PENDING="):
            continue

        if line.startswith("GHOST_AUTH_PASSWORD="):
            rewritten.append(
                f"GHOST_AUTH_PASSWORD={passphrase}"
            )
        else:
            rewritten.append(line)

    if not any(
        line.startswith("GHOST_AUTH_PASSWORD=")
        for line in rewritten
    ):
        rewritten.append(f"GHOST_AUTH_PASSWORD={passphrase}")

    with open(config_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(rewritten) + "\n")

    # The running process must immediately use the new value.
    os.environ["GHOST_AUTH_PASSWORD"] = passphrase
    os.environ.pop("ENMA_SETUP_PENDING", None)


def _reject_weak(passphrase: str) -> Optional[str]:
    """Reasonable local policy. Returns a reason or None."""

    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        return (
            f"Passphrase must be at least "
            f"{MIN_PASSPHRASE_LENGTH} characters."
        )

    if passphrase.strip() != passphrase:
        return "Passphrase cannot start or end with spaces."

    return None


@router.post("/setup")
async def setup_passphrase(
    request: SetupRequest,
    http_request: Request,
):
    """
    First-run setup: the user chooses their own permanent ENMA
    passphrase. Available ONLY while the bootstrap credential
    is pending — once completed, this endpoint is closed and
    normal authentication applies. The chosen passphrase is
    persisted to the user's private config file and never
    returned or logged.
    """

    if not _setup_pending():

        raise HTTPException(
            status_code=409,
            detail=(
                "Passphrase setup is not pending for this "
                "installation."
            ),
        )

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
            detail="Too many attempts. Try again later.",
        )

    passphrase = request.passphrase.strip()
    confirm = request.confirm.strip()

    if passphrase != confirm:

        raise HTTPException(
            status_code=400,
            detail="Passphrases do not match.",
        )

    weakness = _reject_weak(passphrase)

    if weakness:

        raise HTTPException(
            status_code=400,
            detail=weakness,
        )

    _persist_passphrase(passphrase)

    logger.info(
        "First-run passphrase setup completed for %s",
        client_ip,
    )

    session = session_store.create()

    return {
        "token": session.token,
        "token_type": "bearer",
        "expires_at": session.expires_at,
        "setup_complete": True,
    }


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
