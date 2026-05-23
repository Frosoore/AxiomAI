"""
axiom/session.py

API publique de haut niveau du moteur Axiom (headless, zéro Qt).

Une `Session` compose les briques du moteur (Arbitrator, EventSourcer,
CheckpointManager, VectorMemory) et expose une boucle de jeu synchrone qu'une
app (GUI, CLI, serveur) peut piloter :

    from axiom.session import Session
    from axiom.config import load_config, build_llm_from_config

    llm = build_llm_from_config(load_config())
    sess = Session("universes/my_world.axiom", save_id, llm=llm)
    result = sess.take_turn("J'ouvre la porte.", on_token=print)

Le streaming se fait via le callback `on_token`. La méthode est synchrone :
côté GUI, l'app l'enveloppe dans un QThread (cf. workers/narrative_worker.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from axiom.arbitrator import ArbitratorEngine, ArbitratorResult
from axiom.backends.base import LLMBackend, LLMMessage
from axiom.checkpoint import CheckpointManager
from axiom.events import EventSourcer
from axiom.memory import VectorMemory
from axiom.universe import Universe
from axiom.db_helpers import load_rules_for_session, get_max_turn_id
from axiom import paths

_DEFAULT_SYSTEM_PROMPT = "You are the narrator of this world."


class Session:
    """Wrapper de haut niveau pour jouer une sauvegarde d'un univers.

    Args:
        universe_path:  Chemin du fichier univers (.axiom / .db SQLite).
        save_id:        Identifiant de la sauvegarde active.
        llm:            Backend LLM déjà construit (cf. build_llm_from_config).
        vector_memory:  Mémoire vectorielle. Si None, une `VectorMemory` est
                        créée sous `<data_dir>/vector/<save_id>` (ou le dossier
                        vector par défaut de l'app si data_dir est None).
        data_dir:       Racine de données optionnelle pour l'injection de chemins
                        (utilisée seulement pour la VectorMemory par défaut).
        mode:           Mode de jeu ('Normal', 'Hardcore', 'Companion').
    """

    def __init__(
        self,
        universe_path: str | Path,
        save_id: str,
        *,
        llm: LLMBackend,
        vector_memory: VectorMemory | None = None,
        data_dir: str | Path | None = None,
        mode: str = "Normal",
    ) -> None:
        self._db_path = str(universe_path)
        self._save_id = save_id
        self._llm = llm
        self._mode = mode

        self.universe = Universe.load(self._db_path)
        self._system_prompt = self.universe.system_prompt or _DEFAULT_SYSTEM_PROMPT

        if vector_memory is None:
            base = Path(data_dir) / "vector" if data_dir is not None else paths.VECTOR_DIR
            vector_memory = VectorMemory(persist_dir=str(Path(base) / save_id))
        self._vector_memory = vector_memory

        rules = load_rules_for_session(self._db_path)
        self._arbitrator = ArbitratorEngine(self._db_path, rules)
        self._events = EventSourcer(self._db_path)
        self._checkpoints = CheckpointManager(self._db_path)
        self._turn_id = get_max_turn_id(self._db_path, save_id)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    @property
    def turn_id(self) -> int:
        """Numéro du dernier tour joué (0 si la partie n'a pas commencé)."""
        return self._turn_id

    def take_turn(
        self,
        player_input: str,
        *,
        player_id: str = "player",
        on_token: Callable[[str], None] | None = None,
        temperature: float = 0.7,
        top_p: float = 1.0,
        verbosity_level: str = "balanced",
        hero_action: str | None = None,
        hero_entity_id: str | None = None,
    ) -> ArbitratorResult:
        """Exécute un tour complet (synchrone) et retourne le résultat.

        L'historique est reconstruit depuis l'Event_Log à chaque tour. Les
        tokens narratifs sont streamés via `on_token` au fur et à mesure.
        """
        self._arbitrator.configure(self._llm, self._vector_memory)
        history = self._load_history()
        self._turn_id += 1
        return self._arbitrator.process_turn(
            save_id=self._save_id,
            turn_id=self._turn_id,
            user_message=player_input,
            universe_system_prompt=self._system_prompt,
            history=history,
            player_entity_id=player_id,
            stream_token_callback=on_token,
            temperature=temperature,
            top_p=top_p,
            verbosity_level=verbosity_level,
            hero_action=hero_action,
            hero_entity_id=hero_entity_id,
            mode=self._mode,
        )

    def rewind(self, target_turn_id: int) -> dict[str, int]:
        """Ramène la sauvegarde à son état au tour `target_turn_id`.

        Invalide le cache de stats de l'Arbitrator et resynchronise `turn_id`.
        Retourne le résumé fourni par `CheckpointManager.rewind`.
        """
        summary = self._checkpoints.rewind(self._save_id, target_turn_id)
        self._arbitrator.invalidate_stats_cache()
        self._turn_id = get_max_turn_id(self._db_path, self._save_id)
        return summary

    def list_checkpoints(self) -> list[int]:
        """Liste les tours pour lesquels un checkpoint (snapshot) existe."""
        return self._checkpoints.list_checkpoints(self._save_id)

    def current_stats(self) -> dict[str, dict[str, str]]:
        """Stats matérialisées courantes par entité (reconstruit le State_Cache).

        Returns:
            dict `entity_id -> {stat_key: stat_value}`.
        """
        from axiom.schema import get_connection

        self._events.rebuild_state_cache(self._save_id)
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT entity_id, stat_key, stat_value FROM State_Cache "
                "WHERE save_id = ?;",
                (self._save_id,),
            ).fetchall()
        out: dict[str, dict[str, str]] = {}
        for entity_id, key, value in rows:
            out.setdefault(entity_id, {})[key] = value
        return out

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _load_history(self) -> list[LLMMessage]:
        """Reconstruit l'historique conversationnel depuis l'Event_Log.

        `user_input` -> rôle "user" ; `narrative_text` -> rôle "assistant"
        (variante active si l'event en contient plusieurs).
        """
        history: list[LLMMessage] = []
        for ev in self._events.get_events(self._save_id):
            event_type = ev["event_type"]
            payload = ev["payload"]
            if event_type == "user_input":
                text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
                history.append({"role": "user", "content": text})
            elif event_type == "narrative_text":
                if isinstance(payload, dict):
                    if "variants" in payload:
                        variants = payload.get("variants") or [""]
                        text = variants[payload.get("active", 0)]
                    else:
                        text = payload.get("text", "")
                else:
                    text = str(payload)
                history.append({"role": "assistant", "content": text or ""})
        return history
