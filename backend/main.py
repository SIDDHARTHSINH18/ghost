import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router
from backend.api.graph import router as graph_router
from backend.api.memory import router as memory_router
from backend.api.upload import router as upload_router
from backend.core.security import (
    get_auth_password,
    get_rate_limits,
    rate_limiter,
    session_store,
)
from backend.core.services import (
    orchestrator,
    provider_status,
)


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s "
        "%(name)s "
        "%(levelname)s "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "ghost.main",
)


# ============================================================
# PUBLIC ROUTES (no session required)
# ============================================================

PUBLIC_PATHS = {
    "/",
    "/health",
    "/health/provider",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/auth/login",
}


_warned_non_loopback = False


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """
    Enforces bearer-token authentication on every route
    except PUBLIC_PATHS. CORS preflight (OPTIONS) passes
    through because browsers never attach Authorization
    headers to preflight requests.
    """

    async def dispatch(
        self,
        request: Request,
        call_next,
    ):
        global _warned_non_loopback

        # ------------------------------------------------
        # One-time warning for non-loopback access (M2):
        # the API is designed for the local machine; a
        # request from another host deserves a loud note
        # in the server log.
        # ------------------------------------------------

        client_host = (
            request.client.host
            if request.client
            else None
        )

        if (
            client_host
            and client_host
            not in ("127.0.0.1", "::1")
            # Starlette's TestClient identifies itself
            # as "testclient"; tests are loopback by
            # definition.
            and client_host != "testclient"
            and not _warned_non_loopback
        ):

            logger.warning(
                "GHOST API is being accessed from a "
                "non-loopback address (%s). If this is "
                "not intentional, stop the server and "
                "bind to 127.0.0.1.",
                client_host,
            )

            _warned_non_loopback = True

        # ------------------------------------------------
        # Public paths and CORS preflight
        # ------------------------------------------------

        if (
            request.method == "OPTIONS"
            or request.url.path in PUBLIC_PATHS
        ):
            return await call_next(request)

        # ------------------------------------------------
        # Bearer token validation
        # ------------------------------------------------

        authorization = request.headers.get(
            "Authorization",
            "",
        )

        token = (
            authorization[len("Bearer "):].strip()
            if authorization.startswith("Bearer ")
            else ""
        )

        session = (
            session_store.get_valid(token)
            if token
            else None
        )

        if session is None:

            return JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Authentication required."
                    ),
                },
                headers={
                    "WWW-Authenticate": "Bearer",
                },
            )

        # ------------------------------------------------
        # General per-session rate limit (chat/upload/
        # login apply their own tighter limits on top)
        # ------------------------------------------------

        limits = get_rate_limits()

        allowed, retry_after = rate_limiter.check(
            f"session:{token}",
            limits["general"],
        )

        if not allowed:

            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        "Rate limit exceeded. "
                        "Slow down."
                    ),
                },
                headers={
                    "Retry-After": str(
                        int(retry_after),
                    ),
                },
            )

        request.state.session_token = token

        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Fail fast on a half-configured backend.

    A missing NVIDIA_API_KEY or GHOST_AUTH_PASSWORD
    previously surfaced only as errors on first use.
    GHOST refuses to start instead.
    """

    status = provider_status()

    if not status["api_key_present"]:

        raise RuntimeError(
            "\n"
            "========================================\n"
            "NVIDIA_API_KEY is not configured.\n"
            "\n"
            "Fix:\n"
            "  1. Copy .env.example to .env\n"
            "  2. Set NVIDIA_API_KEY in .env\n"
            "  3. Restart the backend\n"
            "\n"
            "GHOST refuses to start with a\n"
            "half-configured provider.\n"
            "========================================"
        )

    if not get_auth_password():

        raise RuntimeError(
            "\n"
            "========================================\n"
            "GHOST_AUTH_PASSWORD is not configured.\n"
            "\n"
            "Since M2 the API requires a passphrase.\n"
            "\n"
            "Fix:\n"
            "  1. Open .env\n"
            "  2. Set GHOST_AUTH_PASSWORD to a strong\n"
            "     passphrase of your choice\n"
            "  3. Restart the backend\n"
            "\n"
            "GHOST refuses to start without it —\n"
            "an unauthenticated API is not a safe\n"
            "default.\n"
            "========================================"
        )

    logger.info(
        "Provider '%s' configured "
        "(model=%s, base_url=%s)",
        status["provider"],
        status["model"],
        status["base_url"],
    )

    yield


app = FastAPI(
    title="GHOST — Personal AI Operating System",
    version="0.2.0",
    lifespan=lifespan,
)


app.add_middleware(SessionAuthMiddleware)

# CORS must run OUTERMOST (added last): Starlette runs
# the last-added middleware first on the request path,
# so this ordering lets even 401/429 responses from the
# auth middleware carry CORS headers — otherwise the
# browser could not read them.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Ghost-Sources"],
)


@app.get("/")
def root():
    return {
        "message": "GHOST API is running"
    }


@app.get("/health")
def health():
    """
    Configuration check only — deliberately no
    network call, so health stays fast and works
    offline. /health/provider does a live ping.
    """

    return {
        "status": "ok",
        "provider": provider_status(),
    }


@app.get("/health/provider")
async def health_provider():
    """
    Live reachability check for the configured
    provider (GET /models). Any HTTP response
    counts as reachable; this is a network check,
    not an authentication check.
    """

    provider = orchestrator.get_provider()

    result = await provider.ping()

    return {
        "provider": "nemotron",
        **result,
    }


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(graph_router)
app.include_router(memory_router)
