"""
GHOST — model generation tool (M4 step 4).

model_generate is the only model-facing tool, and it is
intentionally narrow:

- It reaches the model through the single existing gateway
  (backend/core/services.py ``orchestrator``). No provider is
  imported, constructed or called here, and no HTTP happens
  here.
- It is read-only and side-effect free: no files, no memory
  writes, no network beyond the gateway call itself. Hence
  RiskLevel.SAFE.
- It is asynchronous, so it runs through
  Agent.execute_async(). The synchronous path refuses
  awaitable tools rather than leaking an un-awaited coroutine.
- Its params are untrusted model output: the prompt is
  length-bounded, and no arbitrary kwargs are forwarded to
  the gateway, so a model cannot forge provider request
  fields.
- Gateway failures become a controlled ModelToolError whose
  text is credential-redacted and shortened, so a step fails
  cleanly without retaining a traceback or a provider URL
  that carries an API key.
"""

from backend.audit.log import redact_text
from backend.core.services import orchestrator


MAX_PROMPT_CHARS = 8000

MAX_IDENTIFIER_CHARS = 120

MAX_OUTPUT_CHARS = 8000

MAX_ERROR_CHARS = 400


class ModelToolError(Exception):
    """Raised for invalid params or a failed gateway call, so
    the Agent maps it to a FAILED step with this message."""


def _string_param(
    params: dict,
    key: str,
    *,
    required: bool,
    max_chars: int,
):
    raw = params.get(key)

    if raw is None:
        if required:
            raise ModelToolError(
                f"model_generate requires a '{key}' parameter."
            )
        return None

    if not isinstance(raw, str):
        # A malformed value is refused rather than silently
        # dropped: ignoring it would let a planner believe a
        # provider or model selection had taken effect.
        raise ModelToolError(
            f"model_generate '{key}' must be a string."
        )

    value = raw.strip()

    if not value:
        if required:
            raise ModelToolError(
                f"model_generate '{key}' must be a non-empty string."
            )
        return None

    if len(value) > max_chars:
        raise ModelToolError(
            f"model_generate '{key}' is too long "
            f"({len(value)} chars; limit {max_chars} chars)."
        )

    return value


def _safe_error_text(error: Exception) -> str:
    """Single-line, credential-free, bounded failure text."""

    message = " ".join(str(error).split())

    message = redact_text(f"{type(error).__name__}: {message}")

    if len(message) > MAX_ERROR_CHARS:
        message = message[:MAX_ERROR_CHARS] + "...[truncated]"

    return message


async def model_generate(params: dict) -> str:
    """
    Generate text with the configured model.

    params: {"prompt": <required text>,
             "provider": <optional registered provider>,
             "model": <optional model id>}

    Returns the model's text output. The gateway supplies its
    own system prompt and default provider/model; nothing here
    bypasses that layer.
    """

    params = params if isinstance(params, dict) else {}

    prompt = _string_param(
        params,
        "prompt",
        required=True,
        max_chars=MAX_PROMPT_CHARS,
    )

    provider_name = _string_param(
        params,
        "provider",
        required=False,
        max_chars=MAX_IDENTIFIER_CHARS,
    )

    model = _string_param(
        params,
        "model",
        required=False,
        max_chars=MAX_IDENTIFIER_CHARS,
    )

    try:
        output = await orchestrator.generate(
            message=prompt,
            provider_name=provider_name,
            model=model,
        )
    except Exception as error:
        # from None drops the chained provider traceback, which
        # can carry a request URL containing an API key.
        raise ModelToolError(_safe_error_text(error)) from None

    text = output if isinstance(output, str) else str(output)

    if len(text) > MAX_OUTPUT_CHARS:
        text = (
            text[:MAX_OUTPUT_CHARS]
            + f"...[truncated {len(text) - MAX_OUTPUT_CHARS} chars]"
        )

    return text
