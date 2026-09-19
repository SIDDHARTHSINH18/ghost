"""
GHOST — session security (M2).

Threat model context (docs/04-threat-model.md, T1/T6):
before M2, any local process or LAN peer could call the
API unauthenticated. This module provides:

- SessionStore: in-memory bearer-token sessions issued
  after passphrase login. Fixed TTL, revocation.
  In-memory means backend restarts invalidate all
  sessions — an honest limitation for a local
  single-user prototype (documented in README).

- RateLimiter: per-key sliding-window counters, used
  per session (general/chat/upload) and per client
  (login, to slow brute force).

Configuration is read from the environment on every
call (same pattern as backend/core/config.py):

  GHOST_AUTH_PASSWORD             required to start
  GHOST_SESSION_TTL_HOURS         default 12
  GHOST_RATE_LIMIT_GENERAL_PER_MIN  default 240
  GHOST_RATE_LIMIT_CHAT_PER_MIN     default 30
  GHOST_RATE_LIMIT_UPLOAD_PER_MIN   default 15
  GHOST_RATE_LIMIT_LOGIN_PER_MIN    default 10
"""

import math
import os
import secrets
import threading
import time

from collections import deque

from dataclasses import dataclass


DEFAULT_SESSION_TTL_HOURS = 12

DEFAULT_RATE_LIMIT_GENERAL = 240

DEFAULT_RATE_LIMIT_CHAT = 30

DEFAULT_RATE_LIMIT_UPLOAD = 15

DEFAULT_RATE_LIMIT_LOGIN = 10


def _env_int(name: str, default: int) -> int:
    """
    Read an integer from the environment; invalid,
    zero or negative values fall back to the default
    (a rate limit of 0 would silently block everything).
    """

    raw = os.getenv(name)

    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError:
        return default

    if value <= 0:
        return default

    return value


def get_session_ttl_seconds() -> int:
    return _env_int(
        "GHOST_SESSION_TTL_HOURS",
        DEFAULT_SESSION_TTL_HOURS,
    ) * 3600


def get_rate_limits() -> dict:
    return {
        "general": _env_int(
            "GHOST_RATE_LIMIT_GENERAL_PER_MIN",
            DEFAULT_RATE_LIMIT_GENERAL,
        ),
        "chat": _env_int(
            "GHOST_RATE_LIMIT_CHAT_PER_MIN",
            DEFAULT_RATE_LIMIT_CHAT,
        ),
        "upload": _env_int(
            "GHOST_RATE_LIMIT_UPLOAD_PER_MIN",
            DEFAULT_RATE_LIMIT_UPLOAD,
        ),
        "login": _env_int(
            "GHOST_RATE_LIMIT_LOGIN_PER_MIN",
            DEFAULT_RATE_LIMIT_LOGIN,
        ),
    }


def get_auth_password() -> str:
    """
    The configured API passphrase, trimmed. Empty when
    unset — backend.main refuses to start in that case.
    """

    return os.getenv(
        "GHOST_AUTH_PASSWORD",
        "",
    ).strip()


# ============================================================
# SESSIONS
# ============================================================

@dataclass
class Session:

    token: str

    created_at: float

    expires_at: float


class SessionStore:

    def __init__(self):
        self._sessions: dict = {}

        self._lock = threading.Lock()

    def create(self) -> Session:
        """
        Issue a new bearer-token session.
        """

        ttl_seconds = get_session_ttl_seconds()

        now = time.time()

        session = Session(
            token=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=now + ttl_seconds,
        )

        with self._lock:
            self._sessions[session.token] = session

        return session

    def get_valid(
        self,
        token: str,
    ) -> Session | None:
        """
        Return the session for a token if it exists and
        has not expired; expired sessions are removed.
        """

        with self._lock:

            session = self._sessions.get(token)

            if session is None:
                return None

            if time.time() >= session.expires_at:
                del self._sessions[token]

                return None

            return session

    def revoke(self, token: str) -> bool:
        """
        Remove a session (logout). Returns True when a
        session actually existed.
        """

        with self._lock:
            existed = token in self._sessions

            self._sessions.pop(token, None)

        return existed

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


# ============================================================
# RATE LIMITING
# ============================================================

class RateLimiter:
    """
    Sliding-window counter per key.

    check() returns (allowed, retry_after_seconds) so
    callers can set an honest Retry-After header.
    """

    def __init__(self):
        self._events: dict = {}

        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        limit: int,
        window_seconds: float = 60.0,
    ) -> tuple:
        now = time.monotonic()

        with self._lock:

            events = self._events.setdefault(
                key,
                deque(),
            )

            while (
                events
                and now - events[0] >= window_seconds
            ):
                events.popleft()

            if len(events) >= limit:

                retry_after = (
                    window_seconds
                    - (now - events[0])
                )

                return (
                    False,
                    max(
                        1.0,
                        math.ceil(retry_after),
                    ),
                )

            events.append(now)

            return True, 0.0


# ============================================================
# SINGLETONS (same pattern as backend/core/services.py)
# ============================================================

session_store = SessionStore()

rate_limiter = RateLimiter()
