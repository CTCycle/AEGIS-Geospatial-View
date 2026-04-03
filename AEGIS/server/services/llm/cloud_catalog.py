from __future__ import annotations

from AEGIS.server.services.llm.types import ModelDescriptor


def get_cloud_model_catalog() -> list[ModelDescriptor]:
    return [
        ModelDescriptor(
            name="gpt-4.1-mini",
            description="Fast multimodal model for chat and structured tasks.",
            provider="openai",
            capabilities=["chat", "stream", "structured", "embeddings"],
            metadata={"family": "gpt-4.1"},
        ),
        ModelDescriptor(
            name="gpt-4.1",
            description="General-purpose OpenAI reasoning/chat model.",
            provider="openai",
            capabilities=["chat", "stream", "structured", "embeddings"],
            metadata={"family": "gpt-4.1"},
        ),
        ModelDescriptor(
            name="gemini-2.0-flash",
            description="Fast Google model for interactive chat and extraction.",
            provider="google",
            capabilities=["chat", "stream", "structured", "embeddings"],
            metadata={"family": "gemini-2.0"},
        ),
        ModelDescriptor(
            name="gemini-1.5-pro",
            description="Higher quality Google model for deep reasoning and planning.",
            provider="google",
            capabilities=["chat", "stream", "structured", "embeddings"],
            metadata={"family": "gemini-1.5"},
        ),
    ]
