"""
llm_engine/universal_client.py

Universal OpenAI-compatible API client for Axiom AI.
Supports any local/remote backend that implements the OpenAI /v1/chat/completions API
(e.g., LM Studio, KoboldCPP, Ollama, standard OpenAI, etc.).
"""

from __future__ import annotations

import json
from typing import Callable, Iterator

import httpx

from axiom.backends.base import LLMBackend, LLMConnectionError, LLMMessage, LLMResponse
from axiom.backends.transport import IPv4FirstTransport
from axiom.logger import logger

_DEFAULT_TIMEOUT: float = 600.0
# Per-address connect timeout: without it the scalar 600s also applied to the
# TCP connect phase, so a broken IPv6 route stalled for minutes (see
# axiom/backends/transport.py for the long story).
_CONNECT_TIMEOUT: float = 5.0

# Statuses that mean "this key is dead or out of budget" — worth retrying the
# same request with the next key of the pool (TICKET-062: shared beta keys).
# 401 revoked, 402 payment required, 403 suspended, 429 rate/quota exhausted.
_KEY_ROTATION_STATUSES: frozenset[int] = frozenset({401, 402, 403, 429})

# Reasoning models (gpt-oss, OpenAI o-series, DeepSeek R/v4, QwQ, *-thinking)
# spend tokens on a hidden chain-of-thought (`reasoning_content`) BEFORE the
# answer lands in `content`. `max_tokens` caps the total, so a budget sized
# for plain models (150-600 in the arbitrator) gets eaten by the reasoning
# and `content` is never produced (TICKET-066). The cap is billed on actual
# usage, so flooring it higher is free when the model stops early — it only
# prevents that truncation. deepseek-v4-flash confirmed reasoning by live
# probe on Fireworks, 2026-06-12.
_REASONING_MODEL_HINTS: tuple[str, ...] = (
    "gpt-oss", "deepseek-r", "deepseek-v4", "qwq", "-thinking", "-reasoning",
)
_REASONING_TOKEN_FLOOR: int = 2048


def _is_reasoning_model(model_name: str) -> bool:
    """Heuristic match on the model id (after the last '/')."""
    tail = model_name.lower().rsplit("/", 1)[-1]
    # OpenAI o-series ids start with the family name (o1-mini, o3, o4-mini…).
    if tail.startswith(("o1", "o3", "o4")):
        return True
    return any(hint in tail for hint in _REASONING_MODEL_HINTS)


class UniversalClient(LLMBackend):
    """OpenAI-compatible LLM client using httpx.

    Args:
        base_url:   The base URL (e.g., http://localhost:1234/v1).
        api_key:    Optional API key for authorization.
        model_name: The model identifier to request.
        extra_headers: Optional headers merged into every request. Lets a
                    provider use a non-Bearer auth scheme (e.g. Anthropic's
                    x-api-key + anthropic-version) — pass api_key="" then.
        max_stop_sequences: Optional cap on the number of stop sequences sent
                    (OpenAI rejects more than 4; most providers have no limit).
        fallback_api_keys: Optional pool of spare Bearer keys. When a request
                    fails with an auth/quota status (401/402/403/429), the
                    client switches to the next key — stickily — and retries,
                    until the pool is exhausted (TICKET-062: shared beta
                    keys). Only meaningful with Bearer auth (`api_key`).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        extra_headers: dict[str, str] | None = None,
        max_stop_sequences: int | None = None,
        fallback_api_keys: list[str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.extra_headers = dict(extra_headers) if extra_headers else {}
        self.max_stop_sequences = max_stop_sequences
        # Ordered, deduplicated key pool; index 0 is the active key.
        pool = [api_key] + [k for k in (fallback_api_keys or []) if k]
        self._api_keys = list(dict.fromkeys(k for k in pool if k)) or [api_key]
        self._key_index = 0
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=self._get_headers(),
            timeout=httpx.Timeout(_DEFAULT_TIMEOUT, connect=_CONNECT_TIMEOUT),
            transport=IPv4FirstTransport(),
        )

    def _rotate_key(self) -> bool:
        """Switch to the next key of the pool (sticky). False when exhausted."""
        if self._key_index + 1 >= len(self._api_keys):
            return False
        self._key_index += 1
        self.api_key = self._api_keys[self._key_index]
        self._client.headers["Authorization"] = f"Bearer {self.api_key}"
        logger.warning(
            "LLM API key rejected/exhausted — switching to spare key %d/%d.",
            self._key_index + 1, len(self._api_keys),
        )
        return True

    def _send_with_rotation(self, send: "Callable[[], httpx.Response]") -> httpx.Response:
        """Run `send()`, retrying on the next key after an auth/quota status."""
        while True:
            response = send()
            if response.status_code in _KEY_ROTATION_STATUSES and self._rotate_key():
                continue
            return response

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        return headers

    @staticmethod
    def _format_status_error(exc: httpx.HTTPStatusError) -> str:
        """Build an error message that includes the provider's response body.

        A bare "400 Bad Request" hides the actionable cause (unknown model,
        rejected parameter…) — cloud providers put it in the JSON body.
        """
        try:
            exc.response.read()  # streamed responses: body not read yet
        except Exception:
            pass
        try:
            body = " ".join(exc.response.text.split())[:300]
        except Exception:
            body = ""
        message = (
            f"LLM API error {exc.response.status_code} from "
            f"{exc.request.url}: {body or exc}"
        )
        if exc.response.status_code == 404 and "chat/completions" in str(exc.request.url):
            # Cloud providers answer 404 on generation when the model id is
            # unknown/retired (the server itself is fine).
            message += (
                " — a 404 here usually means the configured model does not "
                "exist on this provider. Check the Model field in Settings."
            )
        return message

    def _get_payload(self, messages: list[LLMMessage], stream: bool, temperature: float = 0.7, top_p: float = 1.0, response_format: str | None = None, stop_sequences: list[str] | None = None, max_tokens: int | None = None) -> dict:
        budget = max_tokens if max_tokens else 1024
        if _is_reasoning_model(self.model_name):
            budget = max(budget, _REASONING_TOKEN_FLOOR)
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": budget,
        }
        if "gpt-oss" in self.model_name.lower():
            # Shorter chain-of-thought = lower latency for the same answers.
            # Fireworks accepts the parameter (probed live 2026-06-12).
            payload["reasoning_effort"] = "low"

        # Merge stop sequences
        stops = ["</s>", "<|im_end|>", "\n===", "\n###", "\nUser:", "\nPlayer:", "\n[User]"]
        if stop_sequences:
            stops.extend(stop_sequences)
        stops = list(dict.fromkeys(stops))
        if self.max_stop_sequences is not None:
            stops = stops[: self.max_stop_sequences]
        payload["stop"] = stops

        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        return payload

    def complete(
        self,
        messages: list[LLMMessage],
        stream: bool = False,
        temperature: float = 0.7,
        top_p: float = 1.0,
        response_format: str | None = None,
        stop_sequences: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a list of messages and return a fully assembled LLMResponse."""
        payload = self._get_payload(messages, stream=False, temperature=temperature, top_p=top_p, response_format=response_format, stop_sequences=stop_sequences, max_tokens=max_tokens)

        try:
            response = self._send_with_rotation(
                lambda: self._client.post("/chat/completions", json=payload)
            )
            response.raise_for_status()
            data = response.json()

            choice = data["choices"][0]
            # Reasoning models (gpt-oss, o-series…) put their chain-of-thought
            # in `reasoning_content` and the answer in `content`. When the token
            # budget is spent on reasoning, `content` is null or absent — that
            # is an empty generation, NOT a malformed response, so tolerate it
            # instead of raising KeyError (TICKET-066).
            raw_text = choice.get("message", {}).get("content") or ""
            reason = choice.get("finish_reason", "stop")

            narrative, tool_call = self.parse_tool_call(raw_text)
            return LLMResponse(
                narrative_text=narrative,
                tool_call=tool_call,
                finish_reason=reason,
            )
        except httpx.HTTPStatusError as exc:
            raise LLMConnectionError(self._format_status_error(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMConnectionError(f"Universal API unreachable: {exc}") from exc
        except (KeyError, json.JSONDecodeError) as exc:
            raise LLMConnectionError(f"Unexpected response format: {exc}") from exc

    def stream_tokens(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        top_p: float = 1.0,
        response_format: str | None = None,
        stop_sequences: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Yield individual tokens as they arrive via SSE."""
        payload = self._get_payload(messages, stream=True, temperature=temperature, top_p=top_p, response_format=response_format, stop_sequences=stop_sequences, max_tokens=max_tokens)

        try:
            while True:
                with self._client.stream("POST", "/chat/completions", json=payload) as response:
                    # The status arrives before any token: rotating the key
                    # here can never drop already-yielded content.
                    if (response.status_code in _KEY_ROTATION_STATUSES
                            and self._rotate_key()):
                        continue
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[len("data: "):]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                    return
        except httpx.HTTPStatusError as exc:
            raise LLMConnectionError(self._format_status_error(exc)) from exc
        except httpx.HTTPError as exc:
            raise LLMConnectionError(f"Universal API streaming error: {exc}") from exc

    def is_available(self) -> bool:
        """Check if the backend is reachable."""
        try:
            response = self._send_with_rotation(
                lambda: self._client.get("/models", timeout=5.0)
            )
            return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return the model ids exposed by the server's /models endpoint.

        Empty list on any error — callers use this as a best-effort check
        (e.g. the settings dialog verifying the configured model exists).
        """
        try:
            response = self._send_with_rotation(
                lambda: self._client.get("/models", timeout=10.0)
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            return [m["id"] for m in data if isinstance(m, dict) and "id" in m]
        except Exception:
            return []
