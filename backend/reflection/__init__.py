"""
GHOST — Reflection System (M3-G).

A read-only, deterministic POST-EXECUTION ANALYZER.
"""

from .engine import ReflectionEngine
from .result import (
    ReflectionFailure,
    ReflectionOutcome,
    ReflectionResult,
)

__all__ = [
    "ReflectionEngine",
    "ReflectionFailure",
    "ReflectionOutcome",
    "ReflectionResult",
]