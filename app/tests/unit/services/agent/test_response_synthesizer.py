from __future__ import annotations

from dataclasses import dataclass

from server.domain.chat import ChatOperationResult
from server.services.agent.response_synthesizer import GroundedResponseSynthesizer
from server.services.llm.types import LLMResult


@dataclass
class _Settings:
    agent_model_provider: str = "test"
    agent_model_name: str = "test-model"


class _SettingsRepo:
    def get_or_create(self) -> _Settings:
        return _Settings()


class _Provider:
    def __init__(self, content: str = "**Map ready.**") -> None:
        self.content = content
        self.requests = []

    def chat(self, request):  # noqa: ANN001
        self.requests.append(request)
        return LLMResult(content=self.content)


class _Factory:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    def get_chat_provider(self, provider: str) -> _Provider:
        assert provider == "test"
        return self.provider


def test_synthesizer_returns_grounded_markdown_and_bounded_evidence() -> None:
    provider = _Provider("**Rain layer ready.**\n\n- Current data")
    synthesizer = GroundedResponseSynthesizer(
        settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
        llm_factory=_Factory(provider),  # type: ignore[arg-type]
        enabled=True,
    )
    operation = ChatOperationResult(
        kind="direct_answer",
        status="success",
        message="Verified fallback.",
        warnings=["Current data only."],
        direct_result={"precipitation": 2.4},
    )

    result = synthesizer.synthesize(
        user_text="How much rain is there?",
        fallback_text="Verified fallback.",
        operation=operation,
        direct_result=operation.direct_result,
        task_status="completed",
    )

    assert result.startswith("**Rain layer ready.**")
    request_text = provider.requests[0].messages[1]["content"]
    assert "Verified fallback." in request_text
    assert "Current data only." in request_text
    assert "How much rain is there?" in request_text


def test_synthesizer_falls_back_when_model_fails() -> None:
    class _FailingProvider(_Provider):
        def chat(self, request):  # noqa: ANN001
            raise RuntimeError("offline")

    synthesizer = GroundedResponseSynthesizer(
        settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
        llm_factory=_Factory(_FailingProvider()),  # type: ignore[arg-type]
        enabled=True,
    )
    operation = ChatOperationResult(
        kind="clarification",
        status="partial",
        message="Choose a supported time basis.",
    )

    assert synthesizer.synthesize(
        user_text="October mean",
        fallback_text="Choose a supported time basis.",
        operation=operation,
    ) == "Choose a supported time basis."


def test_synthesizer_does_not_rewrite_failed_or_policy_responses() -> None:
    provider = _Provider("This must not be used.")
    synthesizer = GroundedResponseSynthesizer(
        settings_repo=_SettingsRepo(),  # type: ignore[arg-type]
        llm_factory=_Factory(provider),  # type: ignore[arg-type]
        enabled=True,
    )
    operation = ChatOperationResult(
        kind="error",
        status="failed",
        message="Credential rejected.",
    )

    result = synthesizer.synthesize(
        user_text="Run this",
        fallback_text="Credential rejected.",
        operation=operation,
    )

    assert result == "Credential rejected."
    assert provider.requests == []
