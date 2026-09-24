"""
Tests for the model generation tool (M4 step 4).

model_generate is the one model-facing capability, so these
tests pin the three properties that make it safe to expose to
a planner:

1. It talks to the model ONLY through the existing gateway
   singleton (no provider import, construction, credentials or
   HTTP in the tool).
2. Its parameters are untrusted model output and are validated
   and bounded.
3. It is async and completes only on the async execution path,
   and any gateway failure surfaces as a controlled, credential
   free error on a FAILED step — never a raw traceback.

No network is ever reached: the gateway is always a fake.
"""

import asyncio
import inspect
import re

import pytest

import backend.tools.builtin.model as model_tool

from backend.agents.executor import Agent
from backend.audit.log import redact_text
from backend.core.agent_services import (
    TOOL_IMPLEMENTATIONS,
    permission_policy,
    production_tool_executor,
    tool_registry,
)
from backend.core.task import Task, TaskStatus
from backend.tools.builtin.model import (
    MAX_ERROR_CHARS,
    MAX_OUTPUT_CHARS,
    MAX_PROMPT_CHARS,
    ModelToolError,
    model_generate,
)


SYNTHETIC_KEY = "SYNTHETIC_KEY_TEST"


class FakeGateway:
    """Duck-typed orchestrator; records calls, never network."""

    def __init__(self, response="model says hello", error=None):
        self._response = response
        self._error = error
        self.generate_calls = []

    async def generate(self, **kwargs):
        self.generate_calls.append(kwargs)

        if self._error is not None:
            raise self._error

        return self._response


def run(coro):
    """Drive one coroutine from a plain test function.

    Nothing here runs inside a FastAPI request handler, so
    there is no already-running loop and no nested loop.
    """

    return asyncio.run(coro)


def production_agent() -> Agent:
    """The real registry/policy/dispatch stack, no fakes."""

    return Agent(
        name="test-agent",
        registry=tool_registry,
        permission_policy=permission_policy,
        tool_executor=production_tool_executor,
    )


def new_task() -> Task:
    return Task(
        title="ask the model",
        description="call model_generate",
    )


@pytest.fixture
def gateway(monkeypatch):
    fake = FakeGateway()
    monkeypatch.setattr(model_tool, "orchestrator", fake)
    return fake


# ============================================================
# GATEWAY-ONLY: NO SECOND MODEL PATH
# ============================================================

def test_tool_is_registered_as_safe_model_capability():
    metadata = tool_registry.get_tool("model_generate")

    assert metadata.category == "model"
    assert metadata.risk_level.value == "SAFE"


def test_tool_is_wired_in_the_existing_dispatch_table():
    # Same object, not a re-implementation.
    assert TOOL_IMPLEMENTATIONS["model_generate"] is model_generate


def test_gateway_is_the_only_model_call_in_the_source():
    source = inspect.getsource(model_tool)

    # Exactly one gateway touchpoint: orchestrator.generate().
    assert source.count("orchestrator.") == 1
    assert "orchestrator.generate" in source


def test_no_provider_or_http_layer_is_reachable_from_the_tool():
    source = inspect.getsource(model_tool)

    for forbidden in (
        "httpx",
        "requests",
        "GeminiProvider",
        "OpenAICompatibleProvider",
        "register_provider",
        "get_provider",
        "GEMINI_API_KEY",
        "NVIDIA_API_KEY",
        "api_key",
        "os.environ",
    ):
        assert forbidden not in source, forbidden

    # No provider object is imported into the module namespace.
    for name in dir(model_tool):
        assert "Provider" not in name


def test_gateway_receives_only_the_authorized_fields(gateway):
    result = run(
        model_generate(
            {
                "prompt": "What is ENMA?",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
            }
        )
    )

    assert result == "model says hello"
    assert gateway.generate_calls == [
        {
            "message": "What is ENMA?",
            "provider_name": "gemini",
            "model": "gemini-2.5-flash",
        }
    ]


def test_provider_and_model_default_to_the_gateway(gateway):
    run(model_generate({"prompt": "hello"}))

    call = gateway.generate_calls[0]

    # None means "the gateway decides"; nothing is invented here.
    assert call["provider_name"] is None
    assert call["model"] is None


def test_unlisted_params_are_never_forwarded(gateway):
    run(
        model_generate(
            {
                "prompt": "hello",
                "generationConfig": {"maxOutputTokens": 1},
                "stream": True,
                "temperature": 2.5,
            }
        )
    )

    # A planner cannot forge provider request fields through
    # this tool: only message/provider_name/model are sent.
    assert set(gateway.generate_calls[0]) == {
        "message",
        "provider_name",
        "model",
    }


# ============================================================
# PARAMETER VALIDATION (untrusted params)
# ============================================================

def test_is_a_coroutine_function():
    assert inspect.iscoroutinefunction(model_generate)


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"prompt": ""},
        {"prompt": "   "},
        {"prompt": None},
        {"prompt": 42},
        {"prompt": ["a list"]},
    ],
)
def test_missing_or_invalid_prompt_is_refused_without_a_call(
    gateway,
    params,
):
    with pytest.raises(ModelToolError):
        run(model_generate(params))

    assert gateway.generate_calls == []


def test_overlong_prompt_is_refused(gateway):
    with pytest.raises(ModelToolError, match="too long"):
        run(model_generate({"prompt": "x" * (MAX_PROMPT_CHARS + 1)}))

    assert gateway.generate_calls == []


@pytest.mark.parametrize("key", ["provider", "model"])
def test_overlong_identifier_is_refused(gateway, key):
    with pytest.raises(ModelToolError, match="too long"):
        run(
            model_generate(
                {"prompt": "hello", key: "z" * 500}
            )
        )

    assert gateway.generate_calls == []


@pytest.mark.parametrize("key", ["provider", "model"])
def test_non_string_optional_param_is_refused(gateway, key):
    with pytest.raises(ModelToolError):
        run(model_generate({"prompt": "hello", key: {"nested": 1}}))

    assert gateway.generate_calls == []


def test_whitespace_is_trimmed_not_rejected(gateway):
    run(model_generate({"prompt": "  hello  ", "provider": " gemini "}))

    call = gateway.generate_calls[0]

    assert call["message"] == "hello"
    assert call["provider_name"] == "gemini"


def test_non_dict_params_is_a_controlled_error(gateway):
    with pytest.raises(ModelToolError):
        run(model_generate("not a dict"))

    assert gateway.generate_calls == []


# ============================================================
# OUTPUT HANDLING
# ============================================================

def test_long_output_is_bounded(gateway):
    gateway._response = "y" * (MAX_OUTPUT_CHARS + 500)

    output = run(model_generate({"prompt": "hello"}))

    assert output.startswith("y" * MAX_OUTPUT_CHARS)
    assert "truncated 500 chars" in output
    assert len(output) < MAX_OUTPUT_CHARS + 64


def test_non_string_gateway_output_is_still_text(gateway):
    gateway._response = {"unexpected": "shape"}

    output = run(model_generate({"prompt": "hello"}))

    assert isinstance(output, str)
    assert "unexpected" in output


# ============================================================
# FAILURE PATH: CONTROLLED, CREDENTIAL-FREE
# ============================================================

def test_gateway_failure_becomes_controlled_error(gateway):
    gateway._error = RuntimeError("upstream rejected the request")

    with pytest.raises(ModelToolError) as exc_info:
        run(model_generate({"prompt": "hello"}))

    message = str(exc_info.value)

    assert message == "RuntimeError: upstream rejected the request"
    assert "Traceback" not in message


def test_provider_error_carrying_a_key_url_is_redacted(gateway):
    # Real provider clients echo the request URL, which for the
    # Gemini gateway contains the API key as a query parameter.
    gateway._error = RuntimeError(
        "Client error '400 Bad Request' for url "
        f"'https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.5-flash:generateContent?key={SYNTHETIC_KEY}'"
    )

    with pytest.raises(ModelToolError) as exc_info:
        run(model_generate({"prompt": "hello"}))

    message = str(exc_info.value)

    assert SYNTHETIC_KEY not in message
    assert "[redacted]" in message


def test_error_text_is_bounded(gateway):
    gateway._error = RuntimeError("boom " + ("x" * 5000))

    with pytest.raises(ModelToolError) as exc_info:
        run(model_generate({"prompt": "hello"}))

    assert len(str(exc_info.value)) <= MAX_ERROR_CHARS + 20


def test_failure_suppresses_the_provider_exception_context(gateway):
    gateway._error = ValueError(f"auth failed key={SYNTHETIC_KEY}")

    with pytest.raises(ModelToolError) as exc_info:
        run(model_generate({"prompt": "hello"}))

    # `raise ... from None`: the provider exception (whose repr
    # can carry secrets) is not surfaced as a cause, and the
    # chained context is explicitly suppressed.
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    assert SYNTHETIC_KEY not in str(exc_info.value)


def test_errorred_step_fails_closed_in_the_task(gateway):
    gateway._error = RuntimeError("provider unavailable")

    task = new_task()

    result = run(
        production_agent().execute_async(
            task,
            "model_generate",
            {"prompt": "hello"},
        )
    )

    assert result.status is TaskStatus.FAILED
    assert task.status is TaskStatus.FAILED
    assert task.result is None
    assert task.error.startswith("ModelToolError: RuntimeError:")
    assert "Traceback" not in task.error


# ============================================================
# ASYNC EXECUTION PATH
# ============================================================

def test_completes_through_the_async_agent_path(gateway):
    task = new_task()

    result = run(
        production_agent().execute_async(
            task,
            "model_generate",
            {"prompt": "hello"},
        )
    )

    assert result.status is TaskStatus.COMPLETED
    assert task.status is TaskStatus.COMPLETED
    assert task.result == "model says hello"
    assert result.decision.value == "ALLOW"


def test_sync_agent_path_refuses_it_without_leaking_a_coroutine(
    gateway,
):
    task = new_task()

    result = production_agent().execute(
        task,
        "model_generate",
        {"prompt": "hello"},
    )

    assert result.status is TaskStatus.FAILED
    assert "execute_async" in result.error
    assert task.result is None
    assert gateway.generate_calls == []


def test_permission_precedes_the_model_call(gateway):
    # An unknown name never reaches the gateway: the policy
    # gates the model capability like every other tool.
    task = new_task()

    result = run(
        production_agent().execute_async(
            task,
            "rm_rf",
            {"prompt": "hello"},
        )
    )

    assert result.status is TaskStatus.FAILED
    assert gateway.generate_calls == []


def test_secret_scrubbing_is_reused_not_reimplemented():
    """The tool must not grow a second credential matcher."""

    source = inspect.getsource(model_tool)

    assert "from backend.audit.log import redact_text" in source
    assert "re.compile" not in source
    assert "_SECRET_ASSIGNMENT" not in source

    # No compiled pattern lives in the module namespace either.
    assert not any(
        isinstance(value, type(re.compile("")))
        for value in vars(model_tool).values()
    )

    # And the shared scrubber really does scrub, so the tool's
    # single call site is sufficient.
    redacted = redact_text(f"token: {SYNTHETIC_KEY}")

    assert SYNTHETIC_KEY not in redacted
    assert "[redacted]" in redacted
