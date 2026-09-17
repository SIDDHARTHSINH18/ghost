"""
Shared pytest configuration.

Must set environment BEFORE any backend import:
- GHOST_MEMORY_PATH: keep tests off the real memory store
- NVIDIA_API_KEY: backend.main fails fast without it
"""

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault(
    "GHOST_MEMORY_PATH",
    str(
        Path(tempfile.gettempdir())
        / "ghost-test-memory.json"
    ),
)

os.environ.setdefault(
    "NVIDIA_API_KEY",
    "test-key-not-real",
)
