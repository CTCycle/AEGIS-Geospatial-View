from __future__ import annotations

from server.services.llm.types import ModelDescriptor


def get_cloud_model_catalog() -> list[ModelDescriptor]:
    return [
        ModelDescriptor(
            name="gpt-5-mini",
            description="Cost-optimized OpenAI reasoning model for balanced speed and quality.",
            provider="openai",
            capabilities=["chat", "stream", "structured"],
            metadata={"family": "gpt-5"},
        ),
        ModelDescriptor(
            name="gpt-5-nano",
            description="High-throughput OpenAI model for lightweight classification and extraction tasks.",
            provider="openai",
            capabilities=["chat", "stream", "structured"],
            metadata={"family": "gpt-5"},
        ),
        ModelDescriptor(
            name="gpt-5.2",
            description="Flagship OpenAI reasoning model for complex multi-step planning and coding.",
            provider="openai",
            capabilities=["chat", "stream", "structured"],
            metadata={"family": "gpt-5.2"},
        ),
        ModelDescriptor(
            name="gpt-4.1",
            description="General-purpose OpenAI model with strong instruction following and tool use.",
            provider="openai",
            capabilities=["chat", "stream", "structured"],
            metadata={"family": "gpt-4.1"},
        ),
        ModelDescriptor(
            name="gpt-4.1-mini",
            description="Fast OpenAI model for responsive chat and structured extraction.",
            provider="openai",
            capabilities=["chat", "stream", "structured"],
            metadata={"family": "gpt-4.1"},
        ),
        ModelDescriptor(
            name="gemini-2.5-pro",
            description="Google model for complex reasoning, planning, and long-context workflows.",
            provider="google",
            capabilities=["chat", "stream", "structured"],
            metadata={"family": "gemini-2.5"},
        ),
        ModelDescriptor(
            name="gemini-2.5-flash",
            description="Balanced Google model for multimodal chat and high-volume interactive tasks.",
            provider="google",
            capabilities=["chat", "stream", "structured"],
            metadata={"family": "gemini-2.5"},
        ),
        ModelDescriptor(
            name="gemini-2.5-flash-lite",
            description="Fast and cost-efficient Google model for frequent lightweight operations.",
            provider="google",
            capabilities=["chat", "stream", "structured"],
            metadata={"family": "gemini-2.5"},
        ),
        ModelDescriptor(
            name="gemini-2.0-flash",
            description="Low-latency Google model for quick conversational and extraction tasks.",
            provider="google",
            capabilities=["chat", "stream", "structured"],
            metadata={"family": "gemini-2.0"},
        ),
    ]
