"""
GHOST — builtin production tools (M3-H).

Real tool implementations, one concern per module.
Each module exports plain functions taking a controlled
params dict and returning deterministic results; safety
constraints are enforced in code inside each tool, never
in policy or prompt wording alone.

Registration happens centrally in
backend/core/agent_services.py.
"""
