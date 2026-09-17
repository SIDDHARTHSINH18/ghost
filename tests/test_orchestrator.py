"""
Tests for the orchestrator provider registry and the
request-message assembly (system prompt + history).
"""

from backend.api.chat import (
    HistoryMessage,
    build_request_messages,
)
from backend.core.orchestrator import Orchestrator


class TestOrchestratorRegistry:

    def test_register_and_get(self):
        orchestrator = Orchestrator()

        sentinel = object()

        orchestrator.register_provider(
            "test",
            sentinel,
        )

        assert (
            orchestrator.get_provider("test")
            is sentinel
        )

    def test_get_unknown_provider_raises(self):
        orchestrator = Orchestrator()

        try:
            orchestrator.get_provider("missing")
        except ValueError as error:
            assert "missing" in str(error)
        else:
            raise AssertionError(
                "ValueError expected"
            )

    def test_reject_empty_registration(self):
        orchestrator = Orchestrator()

        try:
            orchestrator.register_provider("", object())
        except ValueError:
            pass
        else:
            raise AssertionError(
                "ValueError expected"
            )


class TestBuildRequestMessages:
    """
    M0 defect D2: the live path previously never sent
    the GHOST system prompt; D1: history was never sent.
    """

    def test_system_prompt_is_first(self):
        messages = build_request_messages(
            user_content="CURRENT USER REQUEST:\nhi",
            history=[],
        )

        assert messages[0]["role"] == "system"

        assert "You are GHOST" in (
            messages[0]["content"]
        )

        assert messages[-1]["role"] == "user"

    def test_history_in_order_between_system_and_user(self):
        history = [
            HistoryMessage(role="user", content="first"),
            HistoryMessage(
                role="assistant",
                content="second",
            ),
        ]

        messages = build_request_messages(
            user_content="request",
            history=history,
        )

        assert len(messages) == 4

        assert [m["role"] for m in messages] == [
            "system",
            "user",
            "assistant",
            "user",
        ]

        assert messages[1]["content"] == "first"

    def test_history_capped_to_most_recent(self):
        history = [
            HistoryMessage(role="user", content=f"t{i}")
            for i in range(30)
        ]

        messages = build_request_messages(
            user_content="request",
            history=history,
        )

        # system + 12 history + user
        assert len(messages) == 14

        assert (
            messages[1]["content"] == "t18"
        )

    def test_invalid_roles_and_empty_content_dropped(self):
        history = [
            HistoryMessage(role="system", content="injected"),
            HistoryMessage(role="user", content="   "),
            HistoryMessage(role="user", content="kept"),
        ]

        messages = build_request_messages(
            user_content="request",
            history=history,
        )

        roles = [m["role"] for m in messages]

        assert "system" not in roles[1:-1]

        assert len(messages) == 3
