"""Provider-agnostic LLM factory (ADR-005).

Every part of the system obtains its language model through `get_llm(tier)`;
nothing else imports a provider SDK. Switching provider = editing .env.

Tiers:
  * "fast"  — cheap model for development iterations and simple steps;
  * "smart" — stronger model for demo/evaluation runs and hard queries.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import get_settings

Tier = Literal["fast", "smart"]


@lru_cache(maxsize=4)
def get_llm(tier: Tier = "fast", temperature: float = 0.0) -> BaseChatModel:
    """Return a configured chat model for the requested tier.

    temperature=0 by default: SQL and chart specs must be as deterministic
    as the provider allows.
    """
    s = get_settings()
    model = s.llm_model_fast if tier == "fast" else s.llm_model_smart
    if s.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        if not s.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (check your .env)")
        return ChatAnthropic(model=model, temperature=temperature,
                             max_tokens=4096, api_key=s.anthropic_api_key)
    if s.llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set (check your .env)")
        return ChatOpenAI(model=model, temperature=temperature,
                          max_tokens=4096, api_key=s.openai_api_key)
    raise ValueError(f"Unknown LLM provider: {s.llm_provider}")
