"""
providers/adapters.py
=====================
Unified adapter interface for all 4 LLM providers.
Each adapter normalises provider-specific APIs into a common response shape.

Adding a new provider = implement ProviderAdapter and register in PROVIDER_REGISTRY.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from models import Message, Provider
from config import settings


@dataclass
class AdapterResponse:
    content: str
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    provider: Provider


class ProviderAdapter(ABC):
    """Base class all provider adapters must implement."""

    @property
    @abstractmethod
    def name(self) -> Provider:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider is configured (API key present)."""
        ...

    @abstractmethod
    def complete(
        self,
        messages: list[Message],
        model: str | None,
        max_tokens: int,
        temperature: float,
    ) -> AdapterResponse:
        ...

    def default_model(self) -> str:
        return "default"


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

class AnthropicAdapter(ProviderAdapter):
    name = Provider.ANTHROPIC

    def is_available(self) -> bool:
        return bool(settings.anthropic_api_key)

    def default_model(self) -> str:
        return "claude-sonnet-4-6"

    def complete(self, messages, model=None, max_tokens=1024, temperature=0.7) -> AdapterResponse:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        model = model or self.default_model()

        # Separate system message if present
        system = next((m.content for m in messages if m.role == "system"), None)
        user_messages = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

        kwargs = dict(model=model, max_tokens=max_tokens, messages=user_messages)
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)

        return AdapterResponse(
            content=response.content[0].text,
            model_used=model,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            provider=Provider.ANTHROPIC,
        )


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

class OpenAIAdapter(ProviderAdapter):
    name = Provider.OPENAI

    def is_available(self) -> bool:
        return bool(settings.openai_api_key)

    def default_model(self) -> str:
        return "gpt-4o"

    def complete(self, messages, model=None, max_tokens=1024, temperature=0.7) -> AdapterResponse:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        model = model or self.default_model()

        oai_messages = [{"role": m.role, "content": m.content} for m in messages]
        response = client.chat.completions.create(
            model=model,
            messages=oai_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return AdapterResponse(
            content=response.choices[0].message.content,
            model_used=model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            provider=Provider.OPENAI,
        )


# ---------------------------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------------------------

class AzureOpenAIAdapter(ProviderAdapter):
    name = Provider.AZURE_OPENAI

    def is_available(self) -> bool:
        return bool(settings.azure_openai_api_key and settings.azure_openai_endpoint)

    def default_model(self) -> str:
        return settings.azure_openai_deployment

    def complete(self, messages, model=None, max_tokens=1024, temperature=0.7) -> AdapterResponse:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        deployment = model or self.default_model()
        oai_messages = [{"role": m.role, "content": m.content} for m in messages]

        response = client.chat.completions.create(
            model=deployment,
            messages=oai_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return AdapterResponse(
            content=response.choices[0].message.content,
            model_used=deployment,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            provider=Provider.AZURE_OPENAI,
        )


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

class GeminiAdapter(ProviderAdapter):
    name = Provider.GEMINI

    def is_available(self) -> bool:
        return bool(settings.google_api_key)

    def default_model(self) -> str:
        return "gemini-1.5-flash"

    def complete(self, messages, model=None, max_tokens=1024, temperature=0.7) -> AdapterResponse:
        import google.generativeai as genai
        genai.configure(api_key=settings.google_api_key)
        model_name = model or self.default_model()

        gen_model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=genai.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        # Convert to Gemini format
        system_msg = next((m.content for m in messages if m.role == "system"), None)
        chat_messages = []
        for m in messages:
            if m.role == "system":
                continue
            gemini_role = "user" if m.role == "user" else "model"
            chat_messages.append({"role": gemini_role, "parts": [m.content]})

        prompt = chat_messages[-1]["parts"][0] if chat_messages else ""
        history = chat_messages[:-1]

        chat = gen_model.start_chat(history=history)
        response = chat.send_message(prompt)

        # Gemini doesn't always return token counts — estimate
        prompt_tokens = len(" ".join(m.content for m in messages).split()) * 1.3
        completion_tokens = len(response.text.split()) * 1.3

        return AdapterResponse(
            content=response.text,
            model_used=model_name,
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            provider=Provider.GEMINI,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROVIDER_REGISTRY: dict[Provider, ProviderAdapter] = {
    Provider.ANTHROPIC: AnthropicAdapter(),
    Provider.OPENAI: OpenAIAdapter(),
    Provider.AZURE_OPENAI: AzureOpenAIAdapter(),
    Provider.GEMINI: GeminiAdapter(),
}
