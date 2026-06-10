"""axiom.mini_dico — requêtes encyclopédiques du Mini-Dico (portage B4).

Logique extraite de `workers/mini_dico_worker.py` : répondre à une question de
lore **hors narration** (aucun contexte de chat, aucune stat) — RAG scopé à la
save + prompt encyclopédique + appel LLM. Zéro dépendance Qt.
"""

from __future__ import annotations

from axiom.backends.base import LLMBackend
from axiom.prompts import build_mini_dico_prompt


def answer_lore_question(
    llm: LLMBackend,
    vector_memory,
    question: str,
    save_id: str,
    lore_book: list[dict] | None = None,
    global_lore: str | None = None,
    temperature: float = 0.7,
    top_p: float = 1.0,
    rag_chunks: int = 5,
) -> str:
    """Répond à une question de lore (persona encyclopédique, zéro narration).

    Args:
        vector_memory: instance compatible `VectorMemory` (méthode `query`).

    Returns:
        Le texte de réponse (jamais vide : repli explicite).
    """
    rag_results = vector_memory.query(save_id, question, k=rag_chunks)
    lore_chunks = [r["text"] for r in rag_results]

    messages = build_mini_dico_prompt(
        question,
        lore_chunks,
        lore_book=lore_book or [],
        global_lore=global_lore,
    )

    response = llm.complete(messages, temperature=temperature, top_p=top_p)
    return response.narrative_text or "(No answer generated.)"
