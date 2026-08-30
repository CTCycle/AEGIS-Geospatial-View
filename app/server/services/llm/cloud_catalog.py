from __future__ import annotations

from server.services.llm.types import ModelContextProfile, ModelDescriptor

MODEL_CONTEXT_PROFILES = {
    ("openai", "gpt-5-mini"): ModelContextProfile(
        "openai",
        "gpt-5-mini",
        400_000,
        128_000,
        8_192,
        supports_context_caching=True,
        metadata_source="openai_model_catalog",
    ),
    ("openai", "gpt-5-nano"): ModelContextProfile(
        "openai",
        "gpt-5-nano",
        400_000,
        128_000,
        8_192,
        supports_context_caching=True,
        metadata_source="openai_model_catalog",
    ),
    ("openai", "gpt-5.2"): ModelContextProfile(
        "openai",
        "gpt-5.2",
        400_000,
        128_000,
        16_384,
        supports_context_caching=True,
        metadata_source="openai_model_catalog",
    ),
    ("openai", "gpt-4.1"): ModelContextProfile(
        "openai",
        "gpt-4.1",
        1_047_576,
        32_768,
        8_192,
        supports_context_caching=True,
        metadata_source="openai_model_catalog",
    ),
    ("openai", "gpt-4.1-mini"): ModelContextProfile(
        "openai",
        "gpt-4.1-mini",
        1_047_576,
        32_768,
        8_192,
        supports_context_caching=True,
        metadata_source="openai_model_catalog",
    ),
    ("google", "gemini-2.5-pro"): ModelContextProfile(
        "google",
        "gemini-2.5-pro",
        1_048_576,
        65_536,
        8_192,
        supports_context_caching=True,
        metadata_source="google_models_api",
    ),
    ("google", "gemini-2.5-flash"): ModelContextProfile(
        "google",
        "gemini-2.5-flash",
        1_048_576,
        65_536,
        8_192,
        supports_context_caching=True,
        metadata_source="google_models_api",
    ),
    ("google", "gemini-2.5-flash-lite"): ModelContextProfile(
        "google",
        "gemini-2.5-flash-lite",
        1_048_576,
        65_536,
        8_192,
        supports_context_caching=True,
        metadata_source="google_models_api",
    ),
    ("google", "gemini-2.0-flash"): ModelContextProfile(
        "google",
        "gemini-2.0-flash",
        1_048_576,
        8_192,
        4_096,
        metadata_source="google_models_api",
    ),
}


###############################################################################
def get_model_context_profile(provider: str, model: str) -> ModelContextProfile | None:
    return MODEL_CONTEXT_PROFILES.get((provider.strip().lower(), model.strip().lower()))


###############################################################################
def get_cloud_model_catalog() -> list[ModelDescriptor]:
    return [
        ModelDescriptor(
            name="gpt-5-mini",
            description="Cost-optimized OpenAI reasoning model for balanced speed and quality.",
            provider="openai",
            capabilities=["chat", "stream", "structured", "structured_output", "tools"],
            metadata={"family": "gpt-5"},
        ),
        ModelDescriptor(
            name="gpt-5-nano",
            description="High-throughput OpenAI model for lightweight classification and extraction tasks.",
            provider="openai",
            capabilities=["chat", "stream", "structured", "structured_output", "tools"],
            metadata={"family": "gpt-5"},
        ),
        ModelDescriptor(
            name="gpt-5.2",
            description="Flagship OpenAI reasoning model for complex multi-step planning and coding.",
            provider="openai",
            capabilities=["chat", "stream", "structured", "structured_output", "tools"],
            metadata={"family": "gpt-5.2"},
        ),
        ModelDescriptor(
            name="gpt-4.1",
            description="General-purpose OpenAI model with strong instruction following and tool use.",
            provider="openai",
            capabilities=["chat", "stream", "structured", "structured_output", "tools"],
            metadata={"family": "gpt-4.1"},
        ),
        ModelDescriptor(
            name="gpt-4.1-mini",
            description="Fast OpenAI model for responsive chat and structured extraction.",
            provider="openai",
            capabilities=["chat", "stream", "structured", "structured_output", "tools"],
            metadata={"family": "gpt-4.1"},
        ),
        ModelDescriptor(
            name="gemini-2.5-pro",
            description="Google model for complex reasoning, planning, and long-context workflows.",
            provider="google",
            capabilities=["chat", "stream", "structured", "structured_output", "tools"],
            metadata={"family": "gemini-2.5"},
        ),
        ModelDescriptor(
            name="gemini-2.5-flash",
            description="Balanced Google model for multimodal chat and high-volume interactive tasks.",
            provider="google",
            capabilities=["chat", "stream", "structured", "structured_output", "tools"],
            metadata={"family": "gemini-2.5"},
        ),
        ModelDescriptor(
            name="gemini-2.5-flash-lite",
            description="Fast and cost-efficient Google model for frequent lightweight operations.",
            provider="google",
            capabilities=["chat", "stream", "structured", "structured_output", "tools"],
            metadata={"family": "gemini-2.5"},
        ),
        ModelDescriptor(
            name="gemini-2.0-flash",
            description="Low-latency Google model for quick conversational and extraction tasks.",
            provider="google",
            capabilities=["chat", "stream", "structured", "structured_output", "tools"],
            metadata={"family": "gemini-2.0"},
        ),
    ]
