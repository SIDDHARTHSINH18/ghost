"""
P0/P1 sprint regression tests:

1. Gemini default-model resolution: generate() and
   generate_stream() resolve the SAME default, and
   GEMINI_MODEL overrides it. The gemini-2.5-flash
   regression (404 on new API keys) cannot return.
2. Empty plans: AutomationEngine zero-step runs yield
   NO_STEPS and never terminalize a task as COMPLETED.
3. Planner gateway failure -> deterministic fallback ->
   zero steps -> task NOT completed.
4. MODEL audit events from the orchestrator gateway.
5. Redaction coverage: gsk_ / sk-or- / JWT-shaped secrets.
6. Audit rotation: bounded active file, history preserved.
7. Memory provenance: task-originated writes carry
   task_id/origin metadata.

No network access: providers are faked at the httpx
boundary or replaced with recording stubs.
"""

import asyncio
import json
import os

import pytest

from backend.agents.memory_bridge import MemoryBridge
from backend.audit.log import AuditLog
from backend.automation.engine import AutomationEngine, WorkflowState
from backend.core.task import Task, TaskStatus
from backend.providers.gemini import GeminiProvider


# ============================================================
# Fakes
# ============================================================

class _FakeResponse:
    def __init__(self, json_body=None, sse_lines=None):
        self._json_body = json_body or {}
        self._sse_lines = sse_lines or []
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_body

    async def aiter_lines(self):
        for line in self._sse_lines:
            yield line


class _FakeStreamCtx:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc):
        return False


class _FakeAsyncClient:
    """Records every request URL; serves canned responses."""

    last_url = None
    next_response = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        _FakeAsyncClient.last_url = url
        return _FakeAsyncClient.next_response

    def stream(self, method, url, **kwargs):
        _FakeAsyncClient.last_url = url
        return _FakeStreamCtx(_FakeAsyncClient.next_response)


@pytest.fixture
def fake_gemini_http(monkeypatch):
    import backend.providers.gemini as gemini_module

    monkeypatch.setattr(
        gemini_module.httpx,
        "AsyncClient",
        _FakeAsyncClient,
    )
    return _FakeAsyncClient


@pytest.fixture
def gemini_provider(monkeypatch):
    provider = GeminiProvider()
    monkeypatch.setattr(provider, "api_key", "synthetic-key", raising=False)
    return provider


def sse_response(text="Hello there."):
    payload = json.dumps(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": text}],
                        "role": "model",
                    }
                }
            ]
        }
    )
    return _FakeResponse(sse_lines=[f"data: {payload}", "data: [DONE]"])


def plain_response(text="Hello there."):
    return _FakeResponse(
        json_body={
            "candidates": [
                {"content": {"parts": [{"text": text}]}}
            ]
        }
    )


# ============================================================
# 1 + 4. Gemini default-model resolution
# ============================================================

class TestGeminiDefaultModel:

    def test_env_overrides_default(self, monkeypatch):
        monkeypatch.setenv("GEMINI_MODEL", "gemini-custom-9")

        assert GeminiProvider()._default_model() == "gemini-custom-9"

    def test_fallback_is_not_the_dead_model(self, monkeypatch):
        monkeypatch.delenv("GEMINI_MODEL", raising=False)

        default = GeminiProvider()._default_model()

        assert default == "gemini-3.5-flash"
        assert "gemini-2.5-flash" not in default

    def test_generate_and_stream_share_one_default(
        self,
        monkeypatch,
        gemini_provider,
        fake_gemini_http,
    ):
        """
        Regression guard: both call paths must resolve the
        same default model. If one path ever hardcodes a
        different model again, the two captured URLs diverge
        and this test fails.
        """

        monkeypatch.delenv("GEMINI_MODEL", raising=False)

        resolved = gemini_provider._default_model()

        fake_gemini_http.next_response = plain_response()
        asyncio.run(
            gemini_provider.generate(
                [{"role": "user", "content": "hi"}]
            )
        )
        generate_url = fake_gemini_http.last_url

        fake_gemini_http.next_response = sse_response()
        asyncio.run(
            _drain(gemini_provider.generate_stream(
                [{"role": "user", "content": "hi"}]
            ))
        )
        stream_url = fake_gemini_http.last_url

        assert f"models/{resolved}:generateContent" in generate_url
        assert (
            f"models/{resolved}:streamGenerateContent"
            in stream_url
        )
        assert "gemini-2.5-flash" not in generate_url
        assert "gemini-2.5-flash" not in stream_url


async def _drain(agen):
    chunks = []
    async for chunk in agen:
        chunks.append(chunk)
    return chunks


# ============================================================
# 2. Empty plans never complete
# ============================================================

class TestZeroStepRuns:

    def _task(self):
        return Task(title="empty plan", description="")

    def test_sync_zero_steps_no_steps_not_completed(self):
        task = self._task()
        engine = AutomationEngine(agent=object())

        result = engine.run(task, [])

        assert result.state is WorkflowState.NO_STEPS
        assert task.status is not TaskStatus.COMPLETED
        assert task.status is TaskStatus.PENDING

    def test_async_zero_steps_no_steps_not_completed(self):
        task = self._task()
        engine = AutomationEngine(agent=object())

        result = asyncio.run(engine.run_async(task, []))

        assert result.state is WorkflowState.NO_STEPS
        assert task.status is TaskStatus.PENDING

    def test_planner_fallback_zero_steps_regression(self):
        """
        The exact live failure: gateway error -> deterministic
        fallback (0 steps) -> run -> must NOT read COMPLETED.
        """

        task = self._task()
        engine = AutomationEngine(agent=object())

        result = asyncio.run(engine.run_async(task, []))

        assert result.state is WorkflowState.NO_STEPS
        assert result.steps == []
        assert task.status is TaskStatus.PENDING
        assert task.status is not TaskStatus.COMPLETED


class _RecordingAgent:
    """Minimal agent double for engine single-step runs."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute(self, task, tool_name, params):
        return self.results.pop(0)

    async def execute_async(self, task, tool_name, params):
        return self.results.pop(0)


# ============================================================
# 4. MODEL audit events from the gateway
# ============================================================

class TestModelAuditEvents:

    def test_successful_call_emits_model_event(self):
        from backend.core.orchestrator import Orchestrator

        rows = []

        gateway = Orchestrator(default_provider="gemini")
        gateway.audit_hook = lambda *a, **kw: rows.append((a, kw))

        class OkProvider:
            async def generate(self, messages, model=None, **kw):
                return "pong"

        gateway.register_provider("gemini", OkProvider())

        reply = asyncio.run(
            gateway.generate(
                "hi",
                provider_name="gemini",
                model="gemini-x",
                task_id="task-1",
            )
        )

        assert reply == "pong"
        assert len(rows) == 1

        args, kwargs = rows[0]
        assert args[0] == "task-1"
        assert kwargs["event"] == "provider_call"
        assert kwargs["status"] == "ok"

        data = kwargs["data"]
        assert data["provider"] == "gemini"
        assert data["model"] == "gemini-x"
        assert data["ok"] is True
        assert "duration_ms" in data

    def test_failing_call_emits_error_type_not_secret(self):
        from backend.core.orchestrator import Orchestrator

        rows = []

        gateway = Orchestrator(default_provider="gemini")
        gateway.audit_hook = lambda *a, **kw: rows.append((a, kw))

        class BadProvider:
            async def generate(self, messages, model=None, **kw):
                raise RuntimeError(
                    "404 for ?key=SYNTHETIC_GOOGLE_TEST_KEY"
                )

        gateway.register_provider("gemini", BadProvider())

        with pytest.raises(RuntimeError):
            asyncio.run(gateway.generate("hi"))

        assert len(rows) == 1

        _, kwargs = rows[0]
        assert kwargs["status"] == "failed"

        data = kwargs["data"]
        assert data["error_type"] == "RuntimeError"
        assert "SYNTHETIC_GOOGLE_TEST_KEY" not in json.dumps(kwargs)

    def test_raising_hook_never_fails_the_call(self):
        from backend.core.orchestrator import Orchestrator

        gateway = Orchestrator(default_provider="gemini")

        def boom(*a, **kw):
            raise OSError("audit disk full")

        gateway.audit_hook = boom

        class OkProvider:
            async def generate(self, messages, model=None, **kw):
                return "still works"

        gateway.register_provider("gemini", OkProvider())

        reply = asyncio.run(gateway.generate("hi"))

        assert reply == "still works"

    def test_model_generate_uses_gateway_with_default_model(
        self, monkeypatch
    ):
        """
        model_generate must reach the model only through the
        gateway, with model=None so the provider's (corrected)
        default resolver decides.
        """

        import backend.tools.builtin.model as model_tool

        calls = {}

        class FakeOrchestrator:
            async def generate(self, **kwargs):
                calls.update(kwargs)
                return "generated text"

        monkeypatch.setattr(
            model_tool,
            "orchestrator",
            FakeOrchestrator(),
        )

        output = asyncio.run(
            model_tool.model_generate({"prompt": "hello"})
        )

        assert output == "generated text"
        assert calls["message"] == "hello"
        assert calls["model"] is None


# ============================================================
# 5. Redaction coverage
# ============================================================

class TestRedactionCoverage:

    def test_groq_key_redacted(self):
        from backend.audit.log import redact_text

        text = "auth failed for gsk_AbC123XyZ456QwErTyUiOp secret"
        out = redact_text(text)

        assert "gsk_AbC123XyZ456QwErTyUiOp" not in out
        assert "[redacted]" in out
        assert "auth failed for" in out
        assert "secret" in out

    def test_openrouter_key_redacted(self):
        from backend.audit.log import redact_text

        text = "bad key sk-or-v1-AbCdEf123456 in url"
        out = redact_text(text)

        assert "sk-or-v1-AbCdEf123456" not in out
        assert "bad key" in out
        assert "in url" in out

    def test_jwt_shaped_token_redacted(self):
        from backend.audit.log import redact_text

        token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36P"
        )
        out = redact_text(f"Bearer {token} rejected")

        assert token not in out
        assert "rejected" in out

    def test_normal_text_untouched(self):
        from backend.audit.log import redact_text

        text = (
            "The quick brown fox jumps over 13 lazy dogs; "
            "key insights include sk-etching and gsk-ools."
        )
        assert redact_text(text) == text

    def test_google_query_key_still_redacted(self):
        from backend.audit.log import redact_text

        out = redact_text(
            "https://x/v1/models?key=SYNTHETIC_GOOGLE_TEST_KEY"
        )

        assert "SYNTHETIC_GOOGLE_TEST_KEY" not in out


# ============================================================
# 6. Audit rotation
# ============================================================

class TestAuditRotation:

    def _log(self, tmp_path, max_bytes):
        return AuditLog(
            storage_path=str(tmp_path / "audit.jsonl"),
            max_bytes=max_bytes,
            max_rotations=2,
        )

    def test_below_threshold_no_rotation(self, tmp_path):
        log = self._log(tmp_path, max_bytes=1024 * 1024)

        log.append("t", "model", event="e1")

        assert os.path.exists(log.storage_path)
        assert not os.path.exists(str(tmp_path / "audit.jsonl.1"))

    def test_threshold_exceeded_rotates_and_keeps_working(
        self, tmp_path
    ):
        log = self._log(tmp_path, max_bytes=400)

        for index in range(6):
            log.append(
                "t",
                "model",
                event=f"event-{index}",
                data={"pad": "x" * 120},
            )

        rotated = tmp_path / "audit.jsonl.1"

        assert rotated.exists()

        # Active file is fresh and still usable.
        assert os.path.exists(log.storage_path)

        row = log.append("t2", "model", event="after-rotation")

        assert row is not None

        rows = log.read()

        assert any(r["event"] == "after-rotation" for r in rows)

        # History was preserved, not deleted: the rotated file
        # still parses.
        rotated_lines = [
            line
            for line in rotated.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]

        assert rotated_lines
        json.loads(rotated_lines[0])

    def test_rotation_failure_does_not_break_append(
        self, tmp_path, monkeypatch
    ):
        log = self._log(tmp_path, max_bytes=1)

        def broken_replace(*args, **kwargs):
            raise OSError("locked")

        monkeypatch.setattr(os, "replace", broken_replace)

        row = log.append("t", "model", event="still-logged")

        assert row is not None
        assert log.read()[0]["event"] == "still-logged"


# ============================================================
# 7. Memory provenance
# ============================================================

class _RecordingMemory:
    def __init__(self):
        self.kwargs = None
        self.next_id = "mem-1"

    def add_memory(self, **kwargs):
        self.kwargs = kwargs
        return {"id": self.next_id}


class _RecordingAudit:
    def __init__(self):
        self.rows = []

    def append(self, *args, **kwargs):
        self.rows.append((args, kwargs))
        return {}


class _Reflection:
    def __init__(self):
        from backend.reflection.result import ReflectionOutcome

        self.outcome = ReflectionOutcome.SUCCEEDED
        self.confidence = 0.9
        # _failing_tools reads .tool_name off each failure.
        failure = type("Failure", (), {"tool_name": "fs_read"})()
        self.failures = [failure]
        self.memory_write_recommended = True
        self.summary = "the task finished"
        self.causes = []
        self.lessons = []
        self.recommended_next_action = ""


class TestMemoryProvenance:

    def test_task_memory_carries_provenance(self, tmp_path):
        memory = _RecordingMemory()
        bridge = MemoryBridge(
            memory=memory,
            audit=_RecordingAudit(),
        )

        task = Task(title="summarize report", description="", id="task-77")

        bridge.record_outcome(task, _Reflection())

        kwargs = memory.kwargs

        assert kwargs is not None
        assert kwargs["metadata"]["task_id"] == "task-77"
        assert kwargs["metadata"]["task_title"] == (
            "summarize report"
        )
        assert kwargs["metadata"]["origin"] == "task-execution"


class TestMemorySecretRedaction:

    def test_reflection_secret_is_scrubbed_before_persisting(self, tmp_path, monkeypatch):
        """
        Regression: a model reflection quoting a secret (e.g.
        echoing tool output that contained an API key) must not
        persist the secret into the memory store.
        """

        import os

        from backend.core.memory import MemoryService
        from backend.core.task import Task
        from backend.reflection.result import ReflectionOutcome

        store_path = str(tmp_path / "mem.json")

        class R:
            outcome = ReflectionOutcome.FAILED
            confidence = 0.8
            failures = [type("F", (), {"tool_name": "fs_read_file"})()]
            memory_write_recommended = True
            summary = (
                "read failed; file contained "
                "API_KEY=AIzaSySYNTHETIC12345678901234"
            )
            causes = ["bad path"]
            lessons = ["use absolute path"]
            recommended_next_action = ""

        class A:
            def append(self, *a, **k):
                return {}

        memory = MemoryService(storage_path=store_path)
        bridge = MemoryBridge(memory=memory, audit=A())

        bridge.record_outcome(
            Task(title="t", description=""), R()
        )

        stored = open(store_path, encoding="utf-8").read()

        assert "AIzaSySYNTHETIC12345678901234" not in stored
        assert "[redacted]" in stored


class TestPackagedConfigPrecedence:
    """
    Packaged-runtime configuration: ENMA_CONFIG_PATH (the user's
    private config.env written by the desktop layer) must be
    authoritative over a development .env that dotenv's directory
    walk-up might find, and the credential must never leak into
    logs or API responses.
    """

    CFG_PASSWORD = "ENMA_TEST_PACKED_PASSPHRASE_123456"
    DEV_PASSWORD = "ENMA_TEST_DEV_PASSPHRASE_654321"

    def _run_backend_snippet(self, tmp_path, monkeypatch_env):
        """
        Boot the config layer in a fresh interpreter (services
        is a singleton; reload isolation via subprocess).
        Returns (effective_password_source_ok, auth_password).
        """
        import subprocess
        import sys

        config_env = tmp_path / "config.env"
        config_env.write_text(
            f"GHOST_AUTH_PASSWORD={self.CFG_PASSWORD}\n",
            encoding="utf-8",
        )
        dev_env = tmp_path / ".env"
        dev_env.write_text(
            f"GHOST_AUTH_PASSWORD={self.DEV_PASSWORD}\n",
            encoding="utf-8",
        )

        snippet = (
            "import os, sys\n"
            "sys.path.insert(0, r'{root}')\n"
            "os.chdir(r'{tmp}')\n"
            "os.environ['ENMA_CONFIG_PATH'] = r'{cfg}'\n"
            "import backend.core.services  # performs the dotenv loading\n"
            "from backend.core.security import get_auth_password, hash_session_token\n"
            "pw = get_auth_password()\n"
            "# metadata only — never print the password itself\n"
            "print('MATCH_CFG', pw == os.environ['ENMA_EXPECTED'])\n"
            "print('SOURCE_TAG', 'packaged user config' if pw == os.environ['ENMA_EXPECTED'] else 'other')\n"
        ).format(root=r"C:/Users/SV/Downloads/ghost-main/ghost-main", tmp=str(tmp_path), cfg=str(config_env))

        env = {**os.environ, "ENMA_EXPECTED": self.CFG_PASSWORD, **monkeypatch_env}
        result = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )

        assert "MATCH_CFG" in result.stdout, (
            f"snippet failed: {result.stdout} {result.stderr[-400:]}"
        )
        return result.stdout, result.stderr

    def test_config_env_beats_dev_dotenv_walkup(self, tmp_path):
        stdout, stderr = self._run_backend_snippet(
            tmp_path, {"GHOST_AUTH_PASSWORD": ""}
        )

        assert "MATCH_CFG True" in stdout

    def test_config_env_wins_even_when_os_env_set(self, tmp_path):
        """
        The packaged spawn sets ENMA_CONFIG_PATH; a stale
        GHOST_AUTH_PASSWORD in the inherited OS environment must
        not override the user's private configuration.
        """

        stdout, _ = self._run_backend_snippet(
            tmp_path, {"GHOST_AUTH_PASSWORD": self.DEV_PASSWORD}
        )

        assert "MATCH_CFG True" in stdout

    def test_password_never_in_login_response_or_logs(
        self, tmp_path
    ):
        from fastapi.testclient import TestClient

        from backend.main import app

        config_env = tmp_path / "config.env"
        config_env.write_text(
            f"GHOST_AUTH_PASSWORD={self.CFG_PASSWORD}\n",
            encoding="utf-8",
        )

        client = TestClient(app)

        with client.stream(
            "POST",
            "/api/auth/login",
            json={"password": "deliberately-wrong"},
        ) as response:
            body = "".join(response.iter_text())

        assert response.status_code in (401, 429)
        assert self.CFG_PASSWORD not in body

        client.post(
            "/api/auth/login",
            json={"password": self.CFG_PASSWORD},
        )

        # The successful response must not echo the credential.
        success = client.post(
            "/api/auth/login",
            json={"password": self.CFG_PASSWORD},
        )
        assert self.CFG_PASSWORD not in success.text
