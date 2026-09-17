"""
GHOST — shared service singletons.

One instance of each long-lived service for the whole
backend. Always import these instead of constructing
new instances: two MemoryService objects pointing at
the same file caused silent lost-update races
(docs/01-architecture-assessment.md, defect D3).
"""

import os

from dotenv import load_dotenv

from backend.core.context_optimizer import ContextOptimizer
from backend.core.document_processor import DocumentProcessor
from backend.core.document_summarizer import DocumentSummarizer
from backend.core.memory import MemoryService
from backend.core.orchestrator import Orchestrator
from backend.core.retriever import DocumentRetriever
from backend.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


load_dotenv()


DEFAULT_NVIDIA_BASE_URL = (
    "https://integrate.api.nvidia.com/v1"
)

DEFAULT_NVIDIA_MODEL = (
    "nvidia/nemotron-3.5-lightning-30b-a3b"
)


# ============================================================
# SINGLETON SERVICES
# ============================================================
#
# GHOST_MEMORY_PATH lets tests redirect the memory store
# away from the real backend/data/memory.json.

memory_service = (
    MemoryService(
        storage_path=os.environ["GHOST_MEMORY_PATH"],
    )
    if os.getenv("GHOST_MEMORY_PATH")
    else MemoryService()
)

document_processor = DocumentProcessor(
    chunk_size=1500,
    chunk_overlap=200,
)

document_retriever = DocumentRetriever(
    top_k=5,
)

context_optimizer = ContextOptimizer(
    max_words=4500,
)

orchestrator = Orchestrator(
    default_provider="nemotron",
)


# ============================================================
# DEFAULT PROVIDER (NVIDIA, OpenAI-compatible)
# ============================================================

nvidia_base_url = os.getenv(
    "NVIDIA_BASE_URL",
    DEFAULT_NVIDIA_BASE_URL,
)

nvidia_model = os.getenv(
    "NVIDIA_MODEL",
    DEFAULT_NVIDIA_MODEL,
)

orchestrator.register_provider(
    "nemotron",
    OpenAICompatibleProvider(
        name="nemotron",
        base_url=nvidia_base_url,
        api_key=os.getenv(
            "NVIDIA_API_KEY",
        ),
    ),
)

document_summarizer = DocumentSummarizer(
    provider=orchestrator.get_provider(
        "nemotron",
    ),
    model=nvidia_model,
    chunk_batch_size=5,
)


# ============================================================
# DOCUMENT REGISTRY (per-process, in-memory)
# ============================================================
#
# Uploaded documents live here until the process exits.
# upload.py writes, chat.py reads, graph.py reads.
# Sharing one registry (instead of importing the dict
# from upload.py) keeps that dependency explicit;
# persistence and eviction arrive in M1.

documents: dict = {}


def provider_status() -> dict:
    """
    Report provider configuration without secrets.

    Reads the environment live so startup validation
    and /health reflect the current process state.
    Used by backend.main (fail-fast startup) and the
    /health endpoint.
    """

    return {
        "provider": "nemotron",
        "api_key_present": bool(
            os.getenv("NVIDIA_API_KEY"),
        ),
        "base_url": os.getenv(
            "NVIDIA_BASE_URL",
            DEFAULT_NVIDIA_BASE_URL,
        ),
        "model": os.getenv(
            "NVIDIA_MODEL",
            DEFAULT_NVIDIA_MODEL,
        ),
    }
