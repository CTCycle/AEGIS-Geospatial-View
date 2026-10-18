from __future__ import annotations

from typing import Final, Literal

LLMProviderId = Literal[
    "openai",
    "google",
    "deepseek",
    "opencode",
    "opencode-go",
    "ollama",
]

SUPPORTED_LLM_PROVIDERS: Final[frozenset[str]] = frozenset(
    {
        "openai",
        "google",
        "deepseek",
        "opencode",
        "opencode-go",
        "ollama",
    }
)


###############################################################################
def require_canonical_provider(provider: object) -> str:
    """Return an exact registered provider ID or reject the configuration."""

    if not isinstance(provider, str) or provider not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(
            f"Unsupported model provider '{provider}'. Expected one of: "
            f"{', '.join(sorted(SUPPORTED_LLM_PROVIDERS))}."
        )
    return provider
