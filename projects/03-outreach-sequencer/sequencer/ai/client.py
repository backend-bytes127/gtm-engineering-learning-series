"""A thin wrapper over the official Anthropic SDK. It returns only text, raises distinct errors, and never lets the key
reach an error message. The SDK object is injectable so every test runs without a network."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 4000  # thinking is always on for this model, so leave room for it as well as the short message
TIMEOUT_SECONDS = 60.0


class AIError(Exception):
    """The model could not be used for this request. Callers hand the work to a human."""


class AIRefusal(AIError):
    """The model declined (a safety refusal). Never retried or worked around: a person decides."""


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class AIClient:
    def __init__(self, api_key: str = "", model: str = DEFAULT_MODEL, client: object | None = None):
        self.model, self._key = model or DEFAULT_MODEL, api_key
        if client is not None:
            self._sdk = client
            return
        if not api_key:
            raise AIError("An Anthropic API key is required (set ANTHROPIC_API_KEY)")
        import anthropic

        self._sdk = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=TIMEOUT_SECONDS)

    def complete(self, system: str, user: str) -> Completion:
        try:
            response = self._sdk.messages.create(
                model=self.model, max_tokens=MAX_TOKENS, system=system, messages=[{"role": "user", "content": user}]
            )
        except Exception as exc:  # the SDK's typed errors all end up here; callers only need "it failed"
            status = getattr(exc, "status_code", None)
            raise AIError(f"The AI request failed ({type(exc).__name__}{f' {status}' if status else ''})") from None
        if response.stop_reason == "refusal":
            raise AIRefusal("The model declined this request")
        if response.stop_reason == "max_tokens":
            raise AIError("The model's answer was cut off")
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = getattr(response, "usage", None)
        return Completion(
            text, getattr(response, "model", self.model), getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0)
        )
