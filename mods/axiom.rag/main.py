"""mods/axiom.rag/main.py

Official mod: axiom.rag (Semantic Vector Memory via ChromaDB)
Provides:
1. Local semantic memory store backed by ChromaDB and offline embeddings.
2. Slot contribution to axiom.turn:prompt_sections (injects relevant past memories into LLM prompt).
3. Hook axiom.step:after_step (embeds generated narrative prose into ChromaDB post-commit).
4. External storage registration (rewind after the SQL commit) via ctx.register_storage.
5. Service 'rag' registration for engine and session queries.
"""

from __future__ import annotations

from pathlib import Path
import weakref
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
        # Memory of the running session for a save: the turn indexes into it and a
        # rewind/fork rolls back that same instance. Weak: a closed session's
        # memory is not kept alive by the service.
        self._session_memories: "weakref.WeakValueDictionary[str, VectorMemory]" = (
            weakref.WeakValueDictionary()
        )

    def set_vector_memory(self, save_id: str, vm: VectorMemory) -> None:
        """Use the session's vector memory for this save (instead of the service's own)."""
        self._session_memories[str(save_id)] = vm

    def get_vector_memory(self, save_id: str, base_dir: Path | str | None = None) -> VectorMemory:
        if base_dir is None:
            vm = self._session_memories.get(str(save_id))
            if vm is not None:
                return vm
        target_base = Path(base_dir) if base_dir is not None else self.base_dir
        cache_key = f"{target_base}:{save_id}"
        if cache_key not in self._instances:
            self._instances[cache_key] = VectorMemory(persist_dir=str(target_base / save_id))
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

    def fork(self, src_save_id: str, dst_save_id: str, at_turn: int) -> int:
        """Give a forked save the source's memories up to the fork point."""
        src = self.get_vector_memory(src_save_id)
        dst = self.get_vector_memory(dst_save_id)
        return src.copy_to(dst, src_save_id, dst_save_id, at_turn)


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
            vm = getattr(ctx, "vector_memory", None)
            if vm is not None:
                svc.set_vector_memory(save_id, vm)
                results = vm.query(save_id, query_text, k=3, exclude_chunk_type="lore")
            else:
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
    vm = getattr(ctx, "vector_memory", None)
    if vm is not None:
        svc.set_vector_memory(save_id, vm)

    def _embed() -> None:
        try:
            target_vm = getattr(ctx, "vector_memory", None) or svc.get_vector_memory(save_id)
            # One narrative chunk per turn: index 0, so a turn replayed after a
            # rewind overwrites its chunk instead of duplicating it (TICKET-100).
            target_vm.embed_chunk(
                save_id,
                turn_id,
                narrative,
                chunk_type="narrative",
                chunk_index=0,
            )
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

    # External store: rolled back by the engine after the SQL rewind is
    # committed; unregistered when the mod is disabled.
    ctx.register_storage(
        "vector_store",
        rewind_callback=lambda conn, sid, t: svc.rollback(sid, t),
        fork_callback=lambda conn, src, dst, t: svc.fork(src, dst, t),
    )
