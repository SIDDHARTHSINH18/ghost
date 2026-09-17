import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.chat import router as chat_router
from backend.api.graph import router as graph_router
from backend.api.memory import router as memory_router
from backend.api.upload import router as upload_router
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Fail fast on a half-configured backend.

    A missing NVIDIA_API_KEY previously surfaced only
    as a 500 on the first chat request
    (docs/01-architecture-assessment.md, defect D12).
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
    version="0.1.0",
    lifespan=lifespan,
)


# Allow React frontend to communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(graph_router)
app.include_router(memory_router)
