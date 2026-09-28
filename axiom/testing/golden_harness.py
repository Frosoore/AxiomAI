"""axiom.testing.golden_harness

Deterministic integration testing harness and state canonicalization oracle.
Provides zero-network, zero-GPU reproducible validation for the game engine.
"""

from __future__ import annotations

import difflib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from axiom.backends.base import GenerationCancelled, LLMBackend, LLMMessage, LLMResponse
from axiom.saves import materialize_state
from axiom.schema import get_connection


class GoldenHarnessExhaustedError(Exception):
    """Raised when the engine requests more turns than scripted in the harness."""


@dataclass
class ScriptedTurnResponse:
    """Scripted turn response for deterministic LLM testing.

    Attributes:
        narrative_chunks: Simulated token chunks for streaming.
        tool_call: Simulated Arbitrator state change JSON (stats, inventory, etc.).
        delay_per_token: Optional simulated token delay (default 0.0 for instant tests).
    """

    narrative_chunks: list[str]
    tool_call: dict[str, Any]
    delay_per_token: float = 0.0


class ScriptedLLMBackend(LLMBackend):
    """Deterministic, sequential mock LLM backend for golden step test suites."""

    def __init__(self, responses: list[ScriptedTurnResponse]) -> None:
        self.responses = list(responses)
        self._index: int = 0
        self._last_tool_call: dict[str, Any] | None = None

    def is_available(self) -> bool:
        return True

    def cancel(self) -> None:
        """Simulate voluntary cancellation of generation."""
        import threading
        if self.cancel_event is None:
            self.cancel_event = threading.Event()
        self.cancel_event.set()

    def _is_timekeeper_query(self, messages: list[LLMMessage]) -> bool:
        """Detect whether the prompt is aimed at the Timekeeper rather than narration."""
        for msg in messages:
            content = str(msg.get("content", "")).lower()
            if "timekeeper" in content or "chronological parser" in content:
                return True
        return False

    def _is_auxiliary_query(self, messages: list[LLMMessage]) -> bool:
        """Detect stat dynamics or other auxiliary queries."""
        for msg in messages:
            content = str(msg.get("content", "")).lower()
            if "stat dynamics" in content or "classify" in content:
                return True
        return False

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
        self._check_cancelled()

        # Handle auxiliary / timekeeper calls gracefully without exhausting narrative script turns
        if self._is_timekeeper_query(messages):
            return LLMResponse(
                narrative_text='{"elapsed_minutes": 5}',
                tool_call={"elapsed_minutes": 5},
                finish_reason="stop",
            )
        if self._is_auxiliary_query(messages):
            return LLMResponse(
                narrative_text="{}",
                tool_call={},
                finish_reason="stop",
            )

        if self._index >= len(self.responses):
            raise GoldenHarnessExhaustedError(
                f"ScriptedLLMBackend exhausted: requested turn {self._index + 1} "
                f"but only {len(self.responses)} scripted responses available."
            )

        resp = self.responses[self._index]
        self._index += 1
        self._last_tool_call = resp.tool_call
        full_narrative = "".join(resp.narrative_chunks)
        return LLMResponse(
            content=full_narrative,
            tool_call=resp.tool_call,
            finish_reason="stop",
        )

    def stream_tokens(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        top_p: float = 1.0,
        response_format: str | None = None,
        stop_sequences: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        self._check_cancelled()

        if self._is_timekeeper_query(messages):
            yield '{"elapsed_minutes": 5}'
            return

        if self._index >= len(self.responses):
            raise GoldenHarnessExhaustedError(
                f"ScriptedLLMBackend exhausted: requested turn {self._index + 1} "
                f"but only {len(self.responses)} scripted responses available."
            )

        resp = self.responses[self._index]
        self._index += 1
        self._last_tool_call = resp.tool_call

        for chunk in resp.narrative_chunks:
            self._check_cancelled()
            if resp.delay_per_token > 0.0:
                time.sleep(resp.delay_per_token)
            yield chunk

        # Yield tool call as structured fenced block so stream parsers extract it
        if resp.tool_call:
            yield f"\n\n~~~json\n{json.dumps(resp.tool_call)}\n~~~\n"

    def parse_tool_call(self, raw_response: str) -> tuple[str, dict | list | None]:
        narrative, parsed = super().parse_tool_call(raw_response)
        if parsed is None and self._last_tool_call is not None:
            return narrative, self._last_tool_call
        return narrative, parsed


class SessionStateCanonicalizer:
    """Deterministic session state serializer and diff oracle."""

    @staticmethod
    def _normalize_payload(payload: Any) -> Any:
        """Recursively normalize JSON payload eliminating non-deterministic fields."""
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
                return SessionStateCanonicalizer._normalize_payload(data)
            except Exception:
                return payload
        elif isinstance(payload, dict):
            # Exclude non-deterministic volatile keys
            filtered = {
                k: SessionStateCanonicalizer._normalize_payload(v)
                for k, v in payload.items()
                if k not in ("save_id", "created_at", "last_updated", "event_id")
            }
            return {k: filtered[k] for k in sorted(filtered.keys())}
        elif isinstance(payload, list):
            return [SessionStateCanonicalizer._normalize_payload(item) for item in payload]
        return payload

    @classmethod
    def _build_normalized_inventory_tree(cls, raw_inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Construct a deterministic hierarchical tree of inventory items without instance UUIDs."""
        # Index instances by instance_id
        items_by_id: dict[str, dict[str, Any]] = {}
        for item in raw_inventory:
            iid = str(item.get("instance_id") or "")
            items_by_id[iid] = {
                "item_id": str(item.get("item_id") or ""),
                "name": str(item.get("name") or item.get("item_id") or ""),
                "quantity": int(item.get("quantity", 1)),
                "is_container": bool(item.get("is_container")),
                "holder_kind": str(item.get("holder_kind") or "entity"),
                "holder_id": str(item.get("holder_id") or item.get("entity_id") or ""),
                "children": [],
            }

        # Build parent -> children relationships
        roots_by_holder: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for iid, node in items_by_id.items():
            if node["holder_kind"] == "instance" and node["holder_id"] in items_by_id:
                items_by_id[node["holder_id"]]["children"].append(node)
            else:
                key = (node["holder_kind"], node["holder_id"])
                roots_by_holder.setdefault(key, []).append(node)

        # Recursively clean and sort tree nodes
        def _clean_node(n: dict[str, Any]) -> dict[str, Any]:
            sorted_kids = sorted(
                [_clean_node(child) for child in n["children"]],
                key=lambda c: (c["item_id"], c["name"], c["quantity"]),
            )
            return {
                "item_id": n["item_id"],
                "name": n["name"],
                "quantity": n["quantity"],
                "is_container": n["is_container"],
                "children": sorted_kids,
            }

        result_roots = []
        for (h_kind, h_id) in sorted(roots_by_holder.keys()):
            raw_children = roots_by_holder[(h_kind, h_id)]
            sorted_items = sorted(
                [_clean_node(c) for c in raw_children],
                key=lambda c: (c["item_id"], c["name"], c["quantity"]),
            )
            result_roots.append({
                "holder_kind": h_kind,
                "holder_id": h_id,
                "items": sorted_items,
            })

        return result_roots

    @classmethod
    def canonicalize(
        cls,
        db_path: str | Path,
        save_id: str,
        at_turn: int | None = None,
    ) -> dict[str, Any]:
        """Extract and normalize save state into a strictly sorted, deterministic dictionary.

        Eliminates volatile fields (save_id, timestamps, local file paths).
        """
        db_path_str = str(db_path)
        raw_state = materialize_state(db_path_str, save_id, at_turn=at_turn)
        target_turn = at_turn if at_turn is not None else int(raw_state["point"]["turn_id"])

        # 1. Normalized entities (all stats sorted by key, entities sorted by entity_id)
        raw_entities = raw_state.get("entities") or {}
        normalized_entities: dict[str, dict[str, str]] = {}
        for eid in sorted(raw_entities.keys()):
            stats = raw_entities[eid]
            normalized_entities[eid] = {k: str(stats[k]) for k in sorted(stats.keys())}

        # 2. Normalized hierarchical inventory
        raw_inventory = raw_state.get("inventory") or []
        normalized_inventory = cls._build_normalized_inventory_tree(raw_inventory)

        # 3. Normalized modifiers (sorted by (entity_id, stat_key))
        raw_modifiers = raw_state.get("modifiers") or []
        normalized_modifiers = [
            {
                "entity_id": str(m["entity_id"]),
                "stat_key": str(m["stat_key"]),
                "delta": float(m["delta"]),
                "minutes_remaining": int(m["minutes_remaining"]),
            }
            for m in raw_modifiers
        ]
        normalized_modifiers.sort(key=lambda m: (m["entity_id"], m["stat_key"]))

        # 4. Normalized Session_Lore (sorted by (name, category))
        raw_lore = raw_state.get("session_lore") or []
        normalized_lore = [
            {
                "category": str(l.get("category", "")),
                "name": str(l.get("name", "")),
                "keywords": str(l.get("keywords", "")),
                "content": str(l.get("content", "")),
                "origin_turn": int(l.get("origin_turn", 0)),
            }
            for l in raw_lore
        ]
        normalized_lore.sort(key=lambda l: (l["name"], l["category"]))

        # 5. In-game time (diegetic integer minutes)
        in_game_time = int(raw_state.get("point", {}).get("in_game_minutes", 0))

        # 6. Event_Log up to target_turn (with sorted payload keys)
        normalized_events = []
        with get_connection(db_path_str) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT turn_id, event_type, target_entity, payload "
                "FROM Event_Log WHERE save_id = ? AND turn_id <= ? "
                "ORDER BY turn_id ASC, event_id ASC;",
                (save_id, target_turn),
            ).fetchall()
            for r in rows:
                normalized_events.append({
                    "turn_id": int(r["turn_id"]),
                    "event_type": str(r["event_type"]),
                    "target_entity": str(r["target_entity"]),
                    "payload": cls._normalize_payload(r["payload"]),
                })

        return {
            "entities": normalized_entities,
            "inventory": normalized_inventory,
            "modifiers": normalized_modifiers,
            "session_lore": normalized_lore,
            "in_game_time": in_game_time,
            "event_log": normalized_events,
        }

    @classmethod
    def to_json(cls, state: dict[str, Any]) -> str:
        """Serialize a canonical state dict to deterministic formatted JSON."""
        return json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False)

    @classmethod
    def diff(
        cls,
        state_a: dict[str, Any] | str,
        state_b: dict[str, Any] | str,
    ) -> list[str]:
        """Compute standard unified diff between two canonical states.

        Returns an empty list if states are identical, or the diff lines.
        """
        str_a = state_a if isinstance(state_a, str) else cls.to_json(state_a)
        str_b = state_b if isinstance(state_b, str) else cls.to_json(state_b)

        if str_a == str_b:
            return []

        lines_a = [line + "\n" for line in str_a.splitlines()]
        lines_b = [line + "\n" for line in str_b.splitlines()]

        diff_gen = difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile="state_a",
            tofile="state_b",
        )
        return list(diff_gen)
