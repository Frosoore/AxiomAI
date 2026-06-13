"""
llm_engine/gemini_client.py

LLM backend client for Google Gemini models (remote / cloud fallback).

Uses the google-genai SDK (google.genai).  The client translates Axiom AI's
internal list[LLMMessage] format to Gemini's Content objects: the first
system-role message becomes the model's system_instruction, and the
remaining turns become the contents list.

Typical usage::

    from axiom.backends.gemini import GeminiClient

    llm = GeminiClient(api_key="YOUR_KEY", model_name="gemini-2.0-flash")
    if llm.is_available():
        response = llm.complete(messages)
        print(response.narrative_text)
"""

import re
import threading
import time
from typing import Callable, Iterator, TypeVar

from google import genai
from google.genai import types as genai_types

from axiom.backends.base import (
    GenerationCancelled,
    LLMBackend,
    LLMConnectionError,
    LLMMessage,
    LLMParseError,
    LLMResponse,
)
from axiom.backends.transport import IPv4FirstTransport
from axiom.logger import logger

_DEFAULT_MODEL: str = "gemini-2.0-flash"

# --- Résilience aux quotas (TICKET-031) -------------------------------------
# Le free tier Gemini est limité par requêtes/minute ET PAR MODÈLE. Trois
# parades, toutes côté backend pour couvrir tous les appels (Populate,
# canonisation, narration, Timekeeper, Chronicler) sans toucher aux appelants :
# 1. retry sur 429 en respectant le délai renvoyé par l'API ;
# 2. ralentisseur optionnel (requêtes/minute, partagé entre threads) ;
# 3. modèle de secours quand le quota du modèle principal persiste.

_MAX_QUOTA_RETRIES: int = 3      # tentatives supplémentaires par modèle
_MAX_RETRY_WAIT_S: float = 90.0  # plafond d'attente par retry

T = TypeVar("T")


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text or getattr(exc, "code", None) == 429 or " 429 " in f" {text} "


def _is_hard_quota_error(exc: Exception) -> bool:
    """A 429 whose quota is structurally zero: the model is simply not in this
    API key's free tier (the violation reports `limit: 0` / `quotaValue: "0"`).

    Waiting can NEVER make it succeed — yet the API still sends a misleading
    `retryDelay` — so the caller must skip the retry/backoff for this model and
    fail fast instead of burning 1-2 min of countdown per turn (TICKET-050).
    """
    if not _is_quota_error(exc):
        return False
    text = str(exc)
    # The value must be exactly zero: "limit: 100" / "quotaValue: 5" must NOT match.
    return bool(
        re.search(r"limit['\"]?\s*[:=]\s*['\"]?0(?!\d)", text)
        or re.search(r"quotaValue['\"]?\s*[:=]\s*['\"]?0(?!\d)", text)
    )


def _parse_retry_delay(exc_text: str) -> float | None:
    """Extrait le délai suggéré par l'API (« Please retry in 32.4s » / retryDelay)."""
    m = re.search(r"retry in ([0-9.]+)\s*s", exc_text, re.IGNORECASE)
    if not m:
        m = re.search(r"retryDelay'?\"?\s*[:=]\s*'?\"?([0-9.]+)s", exc_text)
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


class _RateLimiter:
    """Espacement minimal entre requêtes, par modèle, partagé entre threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_slot: dict[str, float] = {}

    def reserve_turn(self, key: str, min_interval: float) -> float:
        """Reserve the next slot and return the delay to wait (0 = go).

        Waiting is left to the caller, so it can stay interruptible
        (cancellation, TICKET-033).
        """
        if min_interval <= 0:
            return 0.0
        with self._lock:
            now = time.monotonic()
            slot = max(self._next_slot.get(key, now), now)
            self._next_slot[key] = slot + min_interval
        return max(0.0, slot - time.monotonic())

    def wait_turn(self, key: str, min_interval: float) -> None:
        delay = self.reserve_turn(key, min_interval)
        if delay > 0:
            time.sleep(delay)


_RATE_LIMITER = _RateLimiter()

# The Gemini API rejects requests with more than 5 stop sequences
# (GenerateContentRequest.generation_config.stop_sequences). The engine builds
# a backend-agnostic list that can exceed this, so we clamp it here.
_GEMINI_MAX_STOP_SEQUENCES: int = 5


def _clamp_stop_sequences(stop_sequences: list[str] | None) -> list[str] | None:
    """Truncate stop sequences to the Gemini API limit (max 5)."""
    if stop_sequences and len(stop_sequences) > _GEMINI_MAX_STOP_SEQUENCES:
        return stop_sequences[:_GEMINI_MAX_STOP_SEQUENCES]
    return stop_sequences


class GeminiClient(LLMBackend):
    """LLM backend targeting Google Gemini via the google-genai SDK.

    Args:
        api_key:    Google Generative AI API key.
        model_name: Gemini model identifier.
                    Defaults to "gemini-2.0-flash".
        requests_per_minute: Soft rate limiter (TICKET-031). 0 = unlimited.
        fallback_model: Model tried when the primary model's quota is still
                    exhausted after the retries (quotas are per-model).
                    "" = none.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = _DEFAULT_MODEL,
        requests_per_minute: int = 0,
        fallback_model: str = "",
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._min_interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self._fallback_model = fallback_model.strip()
        # Custom transport (IPv4 first + connect timeout): the SDK ships with
        # no timeout at all and overrides client-level httpx timeouts with an
        # explicit None per request — see axiom/backends/transport.py.
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(
                client_args={"transport": IPv4FirstTransport()},
            ),
        )

    # ------------------------------------------------------------------
    # Résilience quota (TICKET-031)
    # ------------------------------------------------------------------

    def _candidate_models(self) -> list[str]:
        models = [self._model_name]
        if self._fallback_model and self._fallback_model != self._model_name:
            models.append(self._fallback_model)
        return models

    def _interruptible_wait(self, delay: float, label: str | None = None) -> None:
        """Attend `delay` secondes par tranches : annulable (`cancel_event`) et,
        si `label` est fourni, compte à rebours émis via `on_status` (TICKET-033)."""
        deadline = time.monotonic() + delay
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if label is not None:
                self._notify(f"{label} — retry in {max(1, round(remaining))}s")
            slice_s = min(remaining, 5.0)
            if self.cancel_event is not None:
                if self.cancel_event.wait(slice_s):
                    raise GenerationCancelled("Generation cancelled by user.")
            else:
                time.sleep(slice_s)

    def _call_with_quota_retry(self, request: Callable[[str], T]) -> T:
        """Exécute `request(model)` avec pacing, retries 429  and fallback model.

        Pour chaque modèle candidat : jusqu'à `_MAX_QUOTA_RETRIES` reprises en
        respectant le délai suggéré par l'API (backoff sinon). Quota toujours
        épuisé → modèle de secours. Toute autre erreur part immédiatement en
        LLMConnectionError (comportement historique).
        """
        last_exc: Exception | None = None
        for model in self._candidate_models():
            for attempt in range(_MAX_QUOTA_RETRIES + 1):
                self._check_cancelled()
                # Pacing : silencieux mais interruptible (le délai peut être long
                # avec un faible req/min).
                slot_delay = _RATE_LIMITER.reserve_turn(model, self._min_interval)
                if slot_delay > 0:
                    self._interruptible_wait(slot_delay)
                try:
                    return request(model)
                except GenerationCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001 — trié juste dessous
                    if not _is_quota_error(exc):
                        raise LLMConnectionError(
                            f"Gemini API error ({type(exc).__name__}): {exc}"
                        ) from exc
                    last_exc = exc
                    # TICKET-050 : quota structurellement à zéro (modèle hors
                    # free tier) → attendre ne servira jamais. On saute les
                    # retries pour ce modèle et on passe direct au modèle de
                    # secours (qui, lui, peut être dans le tier gratuit).
                    if _is_hard_quota_error(exc):
                        logger.warning(
                            "Gemini quota à 0 pour '%s' (modèle hors free tier) "
                            "— pas de retry, on tente le modèle de secours.", model)
                        break
                    if attempt < _MAX_QUOTA_RETRIES:
                        delay = _parse_retry_delay(str(exc)) or (5.0 * (2 ** attempt))
                        delay = min(delay + 0.5, _MAX_RETRY_WAIT_S)
                        logger.warning(
                            "Gemini quota épuisé (%s) — nouvel essai dans %.1fs "
                            "(tentative %d/%d)", model, delay, attempt + 1, _MAX_QUOTA_RETRIES)
                        # TICKET-033 : compte à rebours visible + annulable.
                        self._interruptible_wait(
                            delay,
                            label=(f"Quota exhausted ({model}) "
                                   f"— attempt {attempt + 1}/{_MAX_QUOTA_RETRIES}"),
                        )
            if model != self._candidate_models()[-1]:
                logger.warning(
                    "Gemini quota toujours épuisé pour '%s' — bascule sur le modèle "
                    "de secours '%s'", model, self._fallback_model)
                self._notify(f"Quota still exhausted on '{model}' "
                             f"— switching to fallback model '{self._fallback_model}'")
        # TICKET-050 : message actionnable quand la cause est un quota à 0
        # (modèle hors free tier) plutôt que le générique « épuisé après retries ».
        if last_exc is not None and _is_hard_quota_error(last_exc):
            raise LLMConnectionError(
                "Gemini quota is 0 for this model — it is not included in your "
                "API key's free tier. Enable billing on the key or pick a model "
                "that is in the free tier (e.g. gemini-2.0-flash). "
                f"Original error: {last_exc}"
            ) from last_exc
        raise LLMConnectionError(
            f"Gemini API error (quota exhausted after retries"
            f"{' and fallback model' if self._fallback_model else ''}): {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # LLMBackend interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check whether the Gemini API is reachable with the configured key.

        Attempts to list available models.  Returns True on success, False
        on any exception.  Never raises.

        Returns:
            True if the API responds without error, False otherwise.
        """
        try:
            # A lightweight list call — verifies connectivity and auth
            list(self._client.models.list())
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return the generation-capable model names, without the "models/" prefix.

        Empty list on any error — best-effort, used by the settings dialog's
        model picker (TICKET-062).
        """
        try:
            names: list[str] = []
            for m in self._client.models.list():
                actions = (getattr(m, "supported_actions", None)
                           or getattr(m, "supported_generation_methods", None)
                           or [])
                if actions and "generateContent" not in actions:
                    continue
                name = (getattr(m, "name", "") or "").removeprefix("models/")
                if name:
                    names.append(name)
            return names
        except Exception:
            return []

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
        """Send messages to Gemini and return a parsed LLMResponse.

        Translates list[LLMMessage] into Gemini format:
        - The first message with role="system" becomes system_instruction.
        - Remaining messages map user/assistant → user/model roles.

        Args:
            messages:    Conversation turns (system, user, assistant).
            stream:      Ignored; use stream_tokens() for token streaming.
            temperature: Sampling temperature (0.0 to 1.0).
            top_p:       Nucleus sampling parameter (0.0 to 1.0).
            response_format: Currently unused for Gemini.
            stop_sequences:  Custom strings to trigger generation stop.
            max_tokens:      Optional limit on the number of tokens to generate.

        Returns:
            LLMResponse with narrative_text, optional tool_call, finish_reason.

        Raises:
            LLMConnectionError: On network failure or API error.
            LLMParseError: On unexpected response structure or bad tool-call JSON.
        """
        system_instruction, contents = self._translate_messages(messages)

        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            top_p=top_p,
            max_output_tokens=max_tokens if max_tokens else 1024,
            stop_sequences=_clamp_stop_sequences(stop_sequences),
        )

        # TICKET-031 : pacing + retry 429 (délai suggéré par l'API) + fallback.
        response = self._call_with_quota_retry(
            lambda model: self._client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        )

        try:
            raw_content: str = response.text
        except (AttributeError, ValueError) as exc:
            raise LLMParseError(
                f"Cannot extract text from Gemini response: {exc}"
            ) from exc

        if raw_content is None:
            raise LLMParseError("Gemini response returned None text.")

        finish_reason = self._extract_finish_reason(response)
        narrative, tool_call = self.parse_tool_call(raw_content)

        return LLMResponse(
            narrative_text=narrative,
            tool_call=tool_call,
            finish_reason=finish_reason,
        )

    def generate_image_bytes(
        self,
        prompt: str,
        aspect_ratio: str | None = None,
    ) -> bytes | None:
        """Generate an image from a text prompt and return the raw bytes.

        Used by the "gemini" image backend (axiom/image_generator.py) with an
        image-capable model (e.g. "gemini-2.5-flash-image"). Goes through the
        same quota-resilience path as text calls (TICKET-031 pacing/429 retry,
        TICKET-033 status/cancellation hooks).

        Args:
            prompt:       Visual prompt describing the image.
            aspect_ratio: Optional aspect ratio supported by the API
                          ("1:1", "16:9", ...). Omitted if the installed SDK
                          does not expose ImageConfig.

        Returns:
            The image bytes (PNG/JPEG as returned by the API), or None if the
            response contains no image part.

        Raises:
            LLMConnectionError: On network failure, API error or exhausted quota.
            GenerationCancelled: If cancel_event is set during a retry wait.
        """
        config_kwargs: dict = {"response_modalities": ["TEXT", "IMAGE"]}
        if aspect_ratio and hasattr(genai_types, "ImageConfig"):
            config_kwargs["image_config"] = genai_types.ImageConfig(
                aspect_ratio=aspect_ratio
            )
        config = genai_types.GenerateContentConfig(**config_kwargs)

        response = self._call_with_quota_retry(
            lambda model: self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
        )

        for candidate in getattr(response, "candidates", None) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline is not None else None
                if data:
                    # The SDK normally returns bytes; tolerate base64 strings.
                    if isinstance(data, str):
                        import base64
                        return base64.b64decode(data)
                    return data
        return None

    def stream_tokens(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        top_p: float = 1.0,
        response_format: str | None = None,
        stop_sequences: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Yield tokens from a streaming Gemini response.

        Args:
            messages:    Conversation turns (system, user, assistant).
            temperature: Sampling temperature (0.0 to 1.0).
            top_p:       Nucleus sampling parameter (0.0 to 1.0).
            response_format: Currently unused for Gemini.
            stop_sequences:  Custom strings to trigger generation stop.
            max_tokens:      Optional limit on the number of tokens to generate.

        Yields:
            Individual token strings in arrival order.

        Raises:
            LLMConnectionError: On network failure.
        """
        system_instruction, contents = self._translate_messages(messages)

        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            top_p=top_p,
            max_output_tokens=max_tokens if max_tokens else 1024,
            stop_sequences=_clamp_stop_sequences(stop_sequences),
        )

        # TICKET-031 : le 429 d'un stream surgit à l'établissement (première
        # itération) — on force le premier chunk DANS la zone de retry, puis
        # on streame le reste normalement.
        def _open_stream(model: str):
            stream = iter(self._client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            ))
            first = next(stream, None)
            return first, stream

        try:
            first_chunk, stream = self._call_with_quota_retry(_open_stream)
        except LLMConnectionError:
            raise

        try:
            chunks = [first_chunk] if first_chunk is not None else []
            for chunk in chunks:
                try:
                    text = chunk.text
                    if text:
                        yield text
                except (AttributeError, ValueError):
                    pass
            for chunk in stream:
                try:
                    text = chunk.text
                    if text:
                        yield text
                except (AttributeError, ValueError):
                    # Empty or safety-blocked chunk — skip silently
                    continue
        except LLMConnectionError:
            raise
        except Exception as exc:
            raise LLMConnectionError(
                f"Gemini stream error ({type(exc).__name__}): {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _translate_messages(
        messages: list[LLMMessage],
    ) -> tuple[str | None, list[genai_types.ContentDict]]:
        """Translate list[LLMMessage] into (system_instruction, contents).

        The first message with role='system' is extracted as system_instruction.
        Remaining messages are mapped: user→user, assistant→model.
        Additional system messages after the first are folded into the user
        turn that follows them as a prefixed block.

        Args:
            messages: Axiom AI internal message list.

        Returns:
            Tuple of (system_instruction_str_or_None, gemini_contents_list).
        """
        system_instruction: str | None = None
        contents: list[dict] = []
        pending_system_injections: list[str] = []

        for msg in messages:
            role: str = msg["role"]
            content: str = msg["content"]

            if role == "system":
                if system_instruction is None:
                    system_instruction = content
                else:
                    pending_system_injections.append(content)
            elif role == "user":
                if pending_system_injections:
                    injection = "\n".join(
                        f"[SYSTEM: {s}]" for s in pending_system_injections
                    )
                    content = f"{injection}\n\n{content}"
                    pending_system_injections = []
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})

        return system_instruction, contents

    @staticmethod
    def _extract_finish_reason(response: object) -> str:
        """Extract a normalised finish_reason string from a Gemini response.

        Args:
            response: The GenerateContentResponse object.

        Returns:
            "stop", "length", or "error".
        """
        try:
            candidates = response.candidates  # type: ignore[attr-defined]
            if not candidates:
                return "error"
            finish = candidates[0].finish_reason
            # FinishReason: STOP=1, MAX_TOKENS=2, others treated as stop
            finish_str = str(finish).upper() if finish else ""
            if "MAX_TOKENS" in finish_str or finish_str == "2":
                return "length"
            return "stop"
        except Exception:
            return "stop"
