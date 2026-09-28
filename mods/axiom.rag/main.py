"""mods/axiom.rag/main.py

Official mod: axiom.rag (Semantic Vector Memory via ChromaDB)
Provides:
1. Local semantic memory store backed by ChromaDB and offline embeddings.
2. Slot contribution to axiom.turn:prompt_sections (injects relevant past memories into LLM prompt).
3. Hook axiom.step:after_step (embeds generated narrative prose into ChromaDB post-commit).
4. Custom storage rollback registration in storage_registry.
5. Service 'rag' registration for engine and session queries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from axiom.kernel.context import ModContext
from axiom.logger import logger
from axiom.memory import VectorMemory


class RagService:
    """Public service exposed by axiom.rag."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        if base_dir is None:
            try:
                from axiom import paths
                self.base_dir = paths.get_vector_dir()
            except Exception:
                self.base_dir = Path.home() / ".local" / "share" / "axiom_ai" / "vectors"
        else:
            self.base_dir = Path(base_dir)
        self._instances: dict[str, VectorMemory] = {}

    def get_vector_memory(self, save_id: str, base_dir: Path | str | None = None) -> VectorMemory:
        target_base = Path(base_dir) if base_dir is not None else self.base_dir
        cache_key = f"{target_base}:{save_id}"
        if cache_key not in self._instances:
            save_dir = target_base / save_id
            self._instances[cache_key] = VectorMemory(persist_dir=str(save_dir))
        return self._instances[cache_key]

    def query(
        self,
        save_id: str,
        query_text: str,
        k: int = 3,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        vm = self.get_vector_memory(save_id)
        return vm.query(save_id, query_text, k=k, **kwargs)

    def embed_chunk(
        self,
        save_id: str,
        chunk_id: Any,
        text: str,
        chunk_type: str = "narrative",
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        vm = self.get_vector_memory(save_id)
        # Handle chunk_id being turn_id or identifier
        turn_id = int(chunk_id) if isinstance(chunk_id, int) or (isinstance(chunk_id, str) and chunk_id.isdigit()) else 0
        return vm.embed_chunk(
            save_id,
            turn_id,
            text,
            chunk_type=chunk_type,
            metadata_extra=metadata,
            **kwargs,
        )

    def rollback(self, save_id: str, target_turn_id: int) -> int:
        vm = self.get_vector_memory(save_id)
        return vm.rollback(save_id, target_turn_id)


_RAG_SERVICE: RagService | None = None


def get_rag_service() -> RagService:
    global _RAG_SERVICE
    if _RAG_SERVICE is None:
        _RAG_SERVICE = RagService()
    return _RAG_SERVICE


def build_rag_prompt_section(ctx: Any) -> dict[str, Any] | None:
    """Slot handler for axiom.turn:prompt_sections (priority 20, position system)."""
    save_id = getattr(ctx, "save_id", "")
    query_text = getattr(ctx, "combined_intents_text", "")
    if not save_id or not query_text:
        return None

    rag_chunks = list(getattr(ctx, "rag_chunks", []) or [])
    if not rag_chunks:
        try:
            svc = get_rag_service()
            results = svc.query(save_id, query_text, k=3)
            rag_chunks = [
                r["text"] if isinstance(r, dict) and "text" in r else str(r)
                for r in results
                if not (isinstance(r, dict) and r.get("chunk_type") == "lore")
            ]
            if hasattr(ctx, "rag_chunks") and rag_chunks:
                ctx.rag_chunks.extend(rag_chunks)
        except Exception as exc:
            logger.debug("[axiom.rag] Query failed: %s", exc)
            return None

    if not rag_chunks:
        return None

    formatted_memories = "\n".join(f"- {c.strip()}" for c in rag_chunks if str(c).strip())
    if not formatted_memories.strip():
        return None

    return {
        "position": "system",
        "text": f"RELEVANT MEMORIES (RAG):\n{formatted_memories}",
        "priority": 20,
        "depth": 2,
    }


def on_after_step(ctx: Any) -> None:
    """Hook: axiom.step:after_step.
    Vectorizes the generated narrative prose and indexes it into ChromaDB post-commit.
    """
    save_id = getattr(ctx, "save_id", "")
    turn_id = getattr(ctx, "turn_id", 0)
    narrative = getattr(ctx, "narrative_text", "") or ""
    if not save_id or not narrative.strip():
        return

    svc = get_rag_service()

    def _embed() -> None:
        try:
            svc.embed_chunk(save_id, turn_id, narrative)
        except Exception as exc:
            logger.warning("[axiom.rag] Narrative embedding failed: %s", exc)

    if hasattr(ctx, "write_batch") and hasattr(ctx.write_batch, "post_commit_callbacks"):
        ctx.write_batch.post_commit_callbacks.append(_embed)
    else:
        _embed()


def init(ctx: ModContext) -> None:
    """Entry point for axiom.rag mod."""
    svc = get_rag_service()
    ctx.register_service("rag", svc)

    # Register prompt section contribution
    ctx.contribute_slot("axiom.turn:prompt_sections", build_rag_prompt_section)

    # Register turn hook
    ctx.register_hook("axiom.step:after_step", on_after_step)

    # Register custom storage rollback with storage_registry
    try:
        from axiom.storage_registry import register_custom_storage
        register_custom_storage(
            "vector_store",
            rewind_callback=lambda conn, sid, t: svc.rollback(sid, t),
        )
        register_custom_storage(
            "VectorMemory",
            rewind_callback=lambda conn, sid, t: svc.rollback(sid, t),
        )
    except Exception as exc:
        logger.debug("[axiom.rag] Failed to register custom storage: %s", exc)
