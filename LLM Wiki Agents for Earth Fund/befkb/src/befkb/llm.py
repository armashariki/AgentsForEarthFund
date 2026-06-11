"""Provider-agnostic LLM + embeddings.

Local-first: Ollama is the default for both chat/extraction and embeddings.
A cloud key (Anthropic/OpenAI) is an opt-in accuracy lever for extraction/claims
only — adding it is a config flip, not a rewrite. Structured output is enforced by
passing a Pydantic model's JSON Schema to the model and validating the result.
"""

from __future__ import annotations

import json
from typing import Optional, Protocol, Type, TypeVar, overload

import numpy as np
from pydantic import BaseModel

from .config import Settings

T = TypeVar("T", bound=BaseModel)


# --------------------------------------------------------------------------- #
# Interfaces
# --------------------------------------------------------------------------- #

class LLMClient(Protocol):
    def complete(self, prompt: str, *, schema: Optional[Type[BaseModel]] = None,
                 system: Optional[str] = None) -> object: ...


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...


def _extract_json(text: str) -> str:
    """Best-effort pull of a JSON object/array out of a model response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=0)
    end = max(text.rfind("}"), text.rfind("]"))
    if end != -1 and end >= start:
        return text[start:end + 1]
    return text


# --------------------------------------------------------------------------- #
# Ollama (default, local)
# --------------------------------------------------------------------------- #

class OllamaClient:
    def __init__(self, model: str, host: str):
        import ollama
        self._client = ollama.Client(host=host)
        self.model = model

    @overload
    def complete(self, prompt: str, *, schema: Type[T], system: Optional[str] = None) -> T: ...
    @overload
    def complete(self, prompt: str, *, schema: None = None, system: Optional[str] = None) -> str: ...

    def complete(self, prompt, *, schema=None, system=None):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        fmt = schema.model_json_schema() if schema is not None else None
        resp = self._client.chat(
            model=self.model, messages=messages,
            format=fmt, options={"temperature": 0.0},
        )
        content = resp["message"]["content"] if isinstance(resp, dict) else resp.message.content
        if schema is None:
            return content
        try:
            return schema.model_validate_json(content)
        except Exception:
            # one structured retry: re-validate against best-effort-extracted JSON
            return schema.model_validate(json.loads(_extract_json(content)))


class OllamaEmbedder:
    def __init__(self, model: str, host: str):
        import ollama
        self._client = ollama.Client(host=host)
        self.model = model

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        resp = self._client.embed(model=self.model, input=texts)
        embs = resp["embeddings"] if isinstance(resp, dict) else resp.embeddings
        return np.asarray(embs, dtype=np.float32)


# --------------------------------------------------------------------------- #
# Cloud seam (opt-in; Anthropic via httpx — no extra dependency)
# --------------------------------------------------------------------------- #

class AnthropicClient:
    def __init__(self, model: str):
        import os
        self.model = model
        self.key = os.environ["ANTHROPIC_API_KEY"]

    def complete(self, prompt, *, schema=None, system=None):
        import httpx
        sys = system or ""
        if schema is not None:
            sys += ("\nRespond with ONLY a single JSON object that conforms to this JSON Schema:\n"
                    + json.dumps(schema.model_json_schema()))
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": self.model, "max_tokens": 4096, "temperature": 0,
                  "system": sys, "messages": [{"role": "user", "content": prompt}]},
            timeout=120,
        )
        r.raise_for_status()
        content = r.json()["content"][0]["text"]
        if schema is None:
            return content
        return schema.model_validate(json.loads(_extract_json(content)))


# --------------------------------------------------------------------------- #
# Factories
# --------------------------------------------------------------------------- #

def get_llm(settings: Settings) -> LLMClient:
    if settings.cloud_provider == "anthropic" and settings.cloud_model:
        return AnthropicClient(settings.cloud_model)
    return OllamaClient(settings.chat_model, settings.ollama_host)


def get_embedder(settings: Settings) -> Embedder:
    # embeddings stay local even when extraction is cloud-routed (keeps the index private + free)
    return OllamaEmbedder(settings.embed_model, settings.ollama_host)
