"""debug/run_step7_live.py — validation headless de l'Étape 7 (worker → Session).

Reproduit EXACTEMENT le chemin de tour de l'app GUI, mais sans Qt :
construit une `Session` comme `tabletop_view._on_send_message`, puis exécute le
vrai `NarrativeWorker.run()` (synchrone) en capturant ses signaux. Tape sur le
vrai backend LLM configuré (Gemini ici). VectorMemory remplacée par un stub léger
(pas d'embedder lourd) — le RAG renvoie vide, le reste du pipeline est réel.

Lancer : .venv/bin/python debug/run_step7_live.py
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass

from axiom.config import load_config, build_llm_from_config
from axiom.db_helpers import create_new_save, get_max_turn_id
from axiom.session import Session
from axiom.events import EventSourcer
from workers.narrative_worker import NarrativeWorker

DB = "/home/garen/AxiomAI/universes/Myria.db"


class StubVectorMemory:
    """VectorMemory factice : RAG vide, embedding no-op (évite chromadb/embedder)."""

    def __init__(self, persist_dir=None):
        self._persist_dir = persist_dir
        self.embedded = []

    def query(self, save_id, text, **kwargs):
        return []

    def embed_chunk(self, save_id, turn_id, text):
        self.embedded.append((turn_id, text[:40]))


@dataclass
class PlayerAction:
    player_id: str
    text: str


def banner(msg):
    print("\n" + "=" * 70 + f"\n{msg}\n" + "=" * 70, flush=True)


def run_turn_via_worker(db, save_id, llm, vm, mode, text, player_id="1"):
    """Construit Session + NarrativeWorker comme l'app et exécute run() (sync)."""
    session = Session(db, save_id, llm=llm, vector_memory=vm, mode=mode)
    print(f"[setup] Session.turn_id avant tour = {session.turn_id}", flush=True)

    worker = NarrativeWorker(
        session, PlayerAction(player_id=player_id, text=text),
        temperature=0.7, top_p=1.0, verbosity="short",
    )

    caps = {"tokens": [], "status": [], "hero": [], "result": [], "error": []}
    worker.token_received.connect(lambda t: caps["tokens"].append(t))
    worker.status_update.connect(lambda s: (caps["status"].append(s), print(f"   [status] {s}", flush=True)))
    worker.hero_decision_received.connect(lambda h: (caps["hero"].append(h), print(f"   [hero]   {h}", flush=True)))
    worker.turn_complete.connect(lambda r: caps["result"].append(r))
    worker.error_occurred.connect(lambda e: (caps["error"].append(e), print(f"   [ERROR]  {e}", flush=True)))

    print(f"[turn] >>> joueur: {text!r}", flush=True)
    worker.run()  # synchrone

    full = "".join(caps["tokens"])
    print(f"[turn] narration streamée ({len(caps['tokens'])} tokens) :", flush=True)
    print("   " + full.replace("\n", "\n   "), flush=True)
    if caps["result"]:
        res = caps["result"][0]
        print(f"[turn] turn_complete OK — game_state_tag={getattr(res, 'game_state_tag', '?')}", flush=True)
        rt = getattr(res, "narrative_text", "")
        print(f"[turn] result.narrative_text == tokens concat ? {rt.strip() == full.strip()}", flush=True)
    print(f"[turn] Event_Log max turn_id après = {get_max_turn_id(db, save_id)}", flush=True)
    return caps, session


def main():
    cfg = load_config()
    banner(f"CONFIG — backend={cfg.llm_backend} model={cfg.gemini_model}")
    if cfg.llm_backend.lower() == "gemini" and not cfg.gemini_api_key:
        print("Pas de clé Gemini — abandon.", flush=True)
        return 1

    llm = build_llm_from_config(cfg)
    vm = StubVectorMemory()

    # Sauvegarde de test dédiée (n'altère pas une partie existante).
    save_id = create_new_save(DB, player_name="Troll", difficulty="Normal")
    banner(f"SAVE de test créée : {save_id}")

    # --- Tour 1 (mode Normal) ---
    banner("TOUR 1 — mode Normal")
    caps1, _ = run_turn_via_worker(DB, save_id, llm, vm, "Normal",
                                   "Je regarde autour de moi dans la forêt.")

    # --- Tour 2 (continuité d'historique + turn_id) ---
    banner("TOUR 2 — continuité (l'historique du tour 1 doit être pris en compte)")
    caps2, sess2 = run_turn_via_worker(DB, save_id, llm, vm, "Normal",
                                       "J'avance vers le bruit que j'entends.")

    # --- Vérif historique reconstruit depuis l'Event_Log ---
    banner("HISTORIQUE reconstruit (Event_Log canonique)")
    hist = sess2._load_history()
    for h in hist:
        print(f"   {h['role']:9} | {h['content'][:60]!r}", flush=True)

    # --- Bilan ---
    banner("BILAN")
    ok = (
        bool(caps1["tokens"]) and bool(caps1["result"]) and not caps1["error"]
        and bool(caps2["tokens"]) and bool(caps2["result"]) and not caps2["error"]
        and get_max_turn_id(DB, save_id) == 2
    )
    print("Tour1 tokens:", len(caps1["tokens"]), "| result:", bool(caps1["result"]), "| err:", caps1["error"], flush=True)
    print("Tour2 tokens:", len(caps2["tokens"]), "| result:", bool(caps2["result"]), "| err:", caps2["error"], flush=True)
    print("Embeddings stub:", vm.embedded, flush=True)
    print("\nRESULTAT:", "✅ OK" if ok else "❌ ECHEC", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
