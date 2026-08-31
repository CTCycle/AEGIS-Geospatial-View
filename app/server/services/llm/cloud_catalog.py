from __future__ import annotations

from server.services.llm.types import ModelContextProfile, ModelDescriptor


###############################################################################
def _catalog_model(
    *,
    name: str,
    description: str,
    provider: str,
    family: str,
    capabilities: list[str],
    context_window_tokens: int,
    maximum_output_tokens: int,
    default_output_reserve: int,
    supports_context_caching: bool = False,
    context_profile_source: str,
) -> ModelDescriptor:
    return ModelDescriptor(
        name=name,
        description=description,
        provider=provider,
        capabilities=capabilities,
        metadata={
            "family": family,
            "context_window_tokens": context_window_tokens,
            "maximum_output_tokens": maximum_output_tokens,
            "default_output_reserve": default_output_reserve,
            "tokenizer_strategy": "chars_per_token_4",
            "supports_context_caching": supports_context_caching,
            "supports_server_compaction": False,
            "context_profile_source": context_profile_source,
        },
    )


# The descriptor is the canonical static model record. Its metadata contains
# the complete context profile so catalog payloads and request budgeting cannot
# drift into separate model lists and profile tables.
CLOUD_MODEL_CATALOG: tuple[ModelDescriptor, ...] = (
    _catalog_model(
        name="gpt-5-mini",
        description="Cost-optimized OpenAI reasoning model for balanced speed and quality.",
        provider="openai",
        family="gpt-5",
        capabilities=["chat", "stream", "structured", "structured_output", "tools"],
        context_window_tokens=400_000,
        maximum_output_tokens=128_000,
        default_output_reserve=8_192,
        supports_context_caching=True,
        context_profile_source="openai_model_catalog",
    ),
    _catalog_model(
        name="gpt-5-nano",
        description="High-throughput OpenAI model for lightweight classification and extraction tasks.",
        provider="openai",
        family="gpt-5",
        capabilities=["chat", "stream", "structured", "structured_output", "tools"],
        context_window_tokens=400_000,
        maximum_output_tokens=128_000,
        default_output_reserve=8_192,
        supports_context_caching=True,
        context_profile_source="openai_model_catalog",
    ),
    _catalog_model(
        name="gpt-5.2",
        description="Flagship OpenAI reasoning model for complex multi-step planning and coding.",
        provider="openai",
        family="gpt-5.2",
        capabilities=["chat", "stream", "structured", "structured_output", "tools"],
        context_window_tokens=400_000,
        maximum_output_tokens=128_000,
        default_output_reserve=16_384,
        supports_context_caching=True,
        context_profile_source="openai_model_catalog",
    ),
    _catalog_model(
        name="gpt-4.1",
        description="General-purpose OpenAI model with strong instruction following and tool use.",
        provider="openai",
        family="gpt-4.1",
        capabilities=["chat", "stream", "structured", "structured_output", "tools"],
        context_window_tokens=1_047_576,
        maximum_output_tokens=32_768,
        default_output_reserve=8_192,
        supports_context_caching=True,
        context_profile_source="openai_model_catalog",
    ),
    _catalog_model(
        name="gpt-4.1-mini",
        description="Fast OpenAI model for responsive chat and structured extraction.",
        provider="openai",
        family="gpt-4.1",
        capabilities=["chat", "stream", "structured", "structured_output", "tools"],
        context_window_tokens=1_047_576,
        maximum_output_tokens=32_768,
        default_output_reserve=8_192,
        supports_context_caching=True,
        context_profile_source="openai_model_catalog",
    ),
    _catalog_model(
        name="gemini-2.5-pro",
        description="Google model for complex reasoning, planning, and long-context workflows.",
        provider="google",
        family="gemini-2.5",
        capabilities=["chat", "stream", "structured", "structured_output", "tools"],
        context_window_tokens=1_048_576,
        maximum_output_tokens=65_536,
        default_output_reserve=8_192,
        supports_context_caching=True,
        context_profile_source="google_models_api",
    ),
    _catalog_model(
        name="gemini-2.5-flash",
        description="Balanced Google model for multimodal chat and high-volume interactive tasks.",
        provider="google",
        family="gemini-2.5",
        capabilities=["chat", "stream", "structured", "structured_output", "tools"],
        context_window_tokens=1_048_576,
        maximum_output_tokens=65_536,
        default_output_reserve=8_192,
        supports_context_caching=True,
        context_profile_source="google_models_api",
    ),
    _catalog_model(
        name="gemini-2.5-flash-lite",
        description="Fast and cost-efficient Google model for frequent lightweight operations.",
        provider="google",
        family="gemini-2.5",
        capabilities=["chat", "stream", "structured", "structured_output", "tools"],
        context_window_tokens=1_048_576,
        maximum_output_tokens=65_536,
        default_output_reserve=8_192,
        supports_context_caching=True,
        context_profile_source="google_models_api",
    ),
    _catalog_model(
        name="gemini-2.0-flash",
        description="Low-latency Google model for quick conversational and extraction tasks.",
        provider="google",
        family="gemini-2.0",
        capabilities=["chat", "stream", "structured", "structured_output", "tools"],
        context_window_tokens=1_048_576,
        maximum_output_tokens=8_192,
        default_output_reserve=4_096,
        context_profile_source="google_models_api",
    ),
)


###############################################################################
def _positive_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    return number if number > 0 else None


###############################################################################
def get_model_context_profile(provider: str, model: str) -> ModelContextProfile | None:
    normalized_provider = provider.strip().lower()
    normalized_model = model.strip().lower()
    for descriptor in CLOUD_MODEL_CATALOG:
        if (
            descriptor.provider.lower() == normalized_provider
            and descriptor.name.lower() == normalized_model
        ):
            metadata = descriptor.metadata
            return ModelContextProfile(
                provider=descriptor.provider,
                model=descriptor.name,
                context_window_tokens=_positive_int(
                    metadata.get("context_window_tokens")
                ),
                maximum_output_tokens=_positive_int(
                    metadata.get("maximum_output_tokens")
                ),
                default_output_reserve=(
                    _positive_int(metadata.get("default_output_reserve")) or 8_192
                ),
                tokenizer_strategy=str(
                    metadata.get("tokenizer_strategy") or "chars_per_token_4"
                ),
                supports_context_caching=bool(metadata.get("supports_context_caching")),
                supports_server_compaction=bool(
                    metadata.get("supports_server_compaction")
                ),
                metadata_source=str(
                    metadata.get("context_profile_source") or "catalog"
                ),
            )
    return None


###############################################################################
def get_cloud_model_catalog() -> list[ModelDescriptor]:
    # Return detached records so callers cannot mutate the canonical snapshot.
    return [
        ModelDescriptor(
            name=item.name,
            description=item.description,
            provider=item.provider,
            capabilities=list(item.capabilities),
            metadata=dict(item.metadata),
        )
        for item in CLOUD_MODEL_CATALOG
    ]
