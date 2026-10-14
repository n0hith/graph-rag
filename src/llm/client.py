"""Provider-agnostic LLM client: caching, structured output and token-usage tracking.

Pipeline code only talks to `LLMClient`. The actual API (Gemini today, possibly Ollama
later) sits behind the small `LLMProvider` interface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from src.config import Settings
from src.llm.cache import LLMCache

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """The provider returned something unusable (e.g. an empty or blocked response)."""


class MissingAPIKeyError(LLMError):
    """No API key is configured for the selected provider."""


class StructuredOutputError(LLMError):
    """The model's reply did not match the requested Pydantic schema."""

    def __init__(self, message: str, raw_text: str, validation_error: ValidationError) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.validation_error = validation_error


@dataclass(frozen=True)
class LLMRequest:
    """Everything a provider needs for one call."""

    model: str
    prompt: str
    system: str | None = None
    json_schema: dict | None = None
    temperature: float | None = None


@dataclass
class LLMResponse:
    """A provider's reply, with approximate token counts."""

    text: str
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0


class LLMProvider(Protocol):
    """What every provider must implement."""

    name: str

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Make one API call (including any retries) and return the reply."""
        ...


@dataclass
class StepUsage:
    """Token and call counts for one pipeline step."""

    calls: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0


@dataclass
class UsageTracker:
    """Accumulates token usage per pipeline step (e.g. "extract.directors")."""

    steps: dict[str, StepUsage] = field(default_factory=dict)

    def record(self, step: str, response: LLMResponse | None, cached: bool) -> None:
        usage = self.steps.setdefault(step, StepUsage())
        if cached:
            usage.cache_hits += 1
            return
        usage.calls += 1
        if response is not None:
            usage.prompt_tokens += response.prompt_tokens
            usage.output_tokens += response.output_tokens
            usage.thinking_tokens += response.thinking_tokens

    def summary(self) -> str:
        """A short human-readable table of usage per step."""
        if not self.steps:
            return "LLM usage: no calls made."
        lines = ["LLM usage (approximate):"]
        for name, u in sorted(self.steps.items()):
            lines.append(
                f"  {name}: {u.calls} API calls, {u.cache_hits} from cache, "
                f"{u.prompt_tokens:,} input tokens, {u.output_tokens:,} output tokens"
                + (f", {u.thinking_tokens:,} thinking tokens" if u.thinking_tokens else "")
            )
        return "\n".join(lines)


class LLMClient:
    """The one entry point the pipeline uses for LLM calls."""

    def __init__(
        self,
        provider: LLMProvider,
        default_model: str,
        cache: LLMCache | None = None,
        tracker: UsageTracker | None = None,
    ) -> None:
        self.provider = provider
        self.default_model = default_model
        self.cache = cache
        self.tracker = tracker or UsageTracker()
        self.last_call_cached = False

    def generate_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        step: str = "default",
    ) -> str:
        """Plain text completion."""
        request = LLMRequest(model or self.default_model, prompt, system, None, temperature)
        return self._call(request, step)

    def generate_structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        step: str = "default",
    ) -> T:
        """Ask for JSON matching `schema` and return it as a validated Pydantic object.

        Raises:
            StructuredOutputError: if the reply doesn't validate. Invalid replies are never
                cached, so a retry (e.g. with the error added to the prompt) makes a fresh call.
        """
        request = LLMRequest(
            model or self.default_model, prompt, system, schema.model_json_schema(), temperature
        )

        def parse(text: str) -> T:
            try:
                return schema.model_validate_json(text)
            except ValidationError as exc:
                raise StructuredOutputError(
                    f"Reply did not match {schema.__name__}: {exc.error_count()} error(s)", text, exc
                ) from exc

        return parse(self._call(request, step, validate=parse))

    def _call(self, request: LLMRequest, step: str, validate=None) -> str:
        key = LLMCache.make_key(
            provider=self.provider.name,
            model=request.model,
            system=request.system,
            prompt=request.prompt,
            schema=request.json_schema,
            temperature=request.temperature,
        )
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                self.last_call_cached = True
                self.tracker.record(step, None, cached=True)
                logger.debug("Cache hit for %s (%s)", step, key[:12])
                return hit["text"]

        self.last_call_cached = False
        response = self.provider.generate(request)
        self.tracker.record(step, response, cached=False)
        if validate is not None:
            validate(response.text)  # raises before anything invalid is cached
        if self.cache is not None:
            self.cache.set(
                key,
                {
                    "provider": self.provider.name,
                    "model": request.model,
                    "step": step,
                    "text": response.text,
                    "prompt_tokens": response.prompt_tokens,
                    "output_tokens": response.output_tokens,
                },
            )
        return response.text


def build_client(
    settings: Settings,
    purpose: Literal["extraction", "qa"] = "extraction",
    tracker: UsageTracker | None = None,
) -> LLMClient:
    """Create an `LLMClient` from settings; `purpose` picks the default model."""
    from src.llm.rate_limiter import RateLimiter

    provider_name = settings.llm_provider.lower()
    if provider_name != "gemini":
        raise ValueError(
            f"LLM_PROVIDER={settings.llm_provider!r} is not supported yet. Only 'gemini' is implemented."
        )
    from src.llm.gemini_provider import GeminiProvider

    limiter = RateLimiter(settings.gemini_rpm, settings.gemini_rpd, settings.quota_state_file)
    provider = GeminiProvider(
        api_key=settings.api_key,
        rate_limiter=limiter,
        max_retries=settings.gemini_max_retries,
    )
    model = settings.gemini_extraction_model if purpose == "extraction" else settings.gemini_qa_model
    return LLMClient(provider, model, LLMCache(settings.llm_cache_dir), tracker)
