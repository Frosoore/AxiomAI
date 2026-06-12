"""axiom.cli.play — commande `axiom play <univers.axiom>`.

Text-adventure dans le terminal, posé sur l'API publique `Session` (la même que
pilote le GUI). Aucune dépendance Qt : c'est la preuve d'embarquabilité du
moteur (Pilier 1, §5.4).

Découpage testable :
    add_play_arguments / run_play  — câblage CLI (args, choix de save, LLM, I/O réels).
    play_loop                      — la boucle de jeu (injectable : read/out/err, session).
    _handle_command                — parsing des commandes slash (/stats, /rewind…).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, TextIO

from axiom.backends.base import LLMConnectionError

_HELP_TEXT = """\
Commands:
  /help                this message
  /stats               show current materialized stats
  /checkpoints         list turns that have a checkpoint
  /rewind <turn_id>    go back to a previous turn's state
  /quit                quit
Any other input is played as a player action.
"""


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def add_play_arguments(parser: argparse.ArgumentParser) -> None:
    """Déclare les arguments de la sous-commande `play`."""
    parser.add_argument(
        "universe",
        help="Path to the universe file (.axiom/.db). Also searched in ~/AxiomAI/universes.",
    )
    parser.add_argument("--save", metavar="SAVE_ID", help="Resume an existing save.")
    parser.add_argument("--new", action="store_true", help="Force a new game.")
    parser.add_argument("--name", default="Hero", help="Player name (new game).")
    parser.add_argument(
        "--difficulty",
        default="Normal",
        choices=["Normal", "Hardcore", "Companion"],
        help="Game mode (new game). Default: Normal.",
    )
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument(
        "--verbosity",
        default="balanced",
        choices=["short", "balanced", "talkative"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_universe_path(raw: str) -> Path | None:
    """Résout le chemin d'univers (tel quel, sinon sous ~/AxiomAI/universes)."""
    direct = Path(raw)
    if direct.exists():
        return direct
    from axiom import paths

    candidate = paths.UNIVERSES_DIR / raw
    if candidate.exists():
        return candidate
    # Permettre d'omettre l'extension.
    for ext in (".axiom", ".db"):
        c = paths.UNIVERSES_DIR / f"{raw}{ext}"
        if c.exists():
            return c
    return None


def _resolve_playable_db(raw: str) -> str | None:
    """Résout n'importe quelle forme d'univers vers un `.db` jouable.

    Accepte (Universe-as-Code) :
      - un `.db` compilé → utilisé tel quel ;
      - un **dossier source** (contient universe.toml) → compilé à la volée ;
      - une archive `.axiom` (v1 ou v2) → dépaquetée puis compilée.

    Retourne le chemin du `.db` runtime, ou None si l'univers est introuvable.
    """
    path = _resolve_universe_path(raw)
    if path is None:
        return None

    if path.is_dir():
        if (path / "universe.toml").exists():
            # ensure_compiled (pas compile_universe) : si la source a changé
            # depuis la dernière partie, refresh in-place de la définition —
            # un rebuild plein effacerait les saves du cache (§7.6 différé).
            from axiom.dev import ensure_compiled
            return str(ensure_compiled(path))
        return None

    if path.suffix == ".axiom":
        from axiom import paths
        from axiom.package import unpack_universe
        from axiom.compile import CACHE_DB_NAME, CACHE_DIRNAME

        dest = unpack_universe(path, paths.UNIVERSES_DIR)
        return str(dest / CACHE_DIRNAME / CACHE_DB_NAME)

    return str(path)  # .db direct


def _read_first_message(db_path: str) -> str:
    """Lit le message d'ouverture authored (clé `first_message` de Universe_Meta)."""
    from axiom.schema import get_connection

    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT value FROM Universe_Meta WHERE key = 'first_message';"
            ).fetchone()
        return (row[0] if row and row[0] else "") or ""
    except Exception:
        return ""


def _resolve_player_id(db_path: str) -> str:
    """Choisit l'entité joueur (1re de type 'player'), repli 'player_1' (parité GUI)."""
    from axiom.db_helpers import load_active_entities

    try:
        for ent in load_active_entities(db_path):
            if ent.get("entity_type") == "player":
                return ent["entity_id"]
    except Exception:
        pass
    return "player_1"


# ---------------------------------------------------------------------------
# Commandes slash
# ---------------------------------------------------------------------------

def _handle_command(line: str, session, out: TextIO, err: TextIO) -> str:
    """Traite une commande slash. Retourne 'quit' pour sortir, sinon 'continue'."""
    parts = line[1:].split()
    cmd = parts[0].lower() if parts else ""

    if cmd in ("quit", "exit", "q"):
        return "quit"

    if cmd in ("help", "h", "?"):
        out.write(_HELP_TEXT)
        out.flush()
        return "continue"

    if cmd == "stats":
        stats = session.current_stats()
        if not stats:
            out.write("(no materialized stats)\n")
        for entity_id, kv in stats.items():
            out.write(f"{entity_id}:\n")
            for key, value in kv.items():
                out.write(f"  {key} = {value}\n")
        out.flush()
        return "continue"

    if cmd in ("checkpoints", "saves"):
        cps = session.list_checkpoints()
        out.write(f"Checkpoints (turns): {cps}\n" if cps else "No checkpoint.\n")
        out.flush()
        return "continue"

    if cmd == "rewind":
        if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
            err.write("Usage: /rewind <turn_id>\n")
            err.flush()
            return "continue"
        summary = session.rewind(int(parts[1]))
        out.write(f"Rewound. {summary}\n")
        out.write(f"Current turn: {session.turn_id}\n")
        out.flush()
        return "continue"

    err.write(f"Unknown command: /{cmd} (see /help)\n")
    err.flush()
    return "continue"


# ---------------------------------------------------------------------------
# Boucle de jeu (injectable)
# ---------------------------------------------------------------------------

def play_loop(
    session,
    *,
    player_id: str = "player_1",
    first_message: str = "",
    read: Callable[[str], str] = input,
    out: TextIO | None = None,
    err: TextIO | None = None,
    temperature: float = 0.7,
    top_p: float = 1.0,
    verbosity: str = "balanced",
) -> None:
    """Boucle REPL d'une partie. S'arrête sur /quit ou EOF (Ctrl-D).

    `session` doit exposer l'API publique `Session` (take_turn, current_stats,
    list_checkpoints, rewind, turn_id). `read`/`out`/`err` sont injectables pour
    les tests.
    """
    out = out or sys.stdout
    err = err or sys.stderr

    if first_message and session.turn_id == 0:
        out.write(first_message.strip() + "\n")
        out.flush()
    out.write("\n(Type /help for commands, /quit to exit.)\n")
    out.flush()

    while True:
        try:
            line = read("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            out.write("\n")
            break

        if not line:
            continue

        if line.startswith("/"):
            if _handle_command(line, session, out, err) == "quit":
                break
            continue

        def on_token(token: str) -> None:
            out.write(token)
            out.flush()

        def on_status(status: str) -> None:
            err.write(f"… {status}\n")
            err.flush()

        try:
            out.write("\n")
            session.take_turn(
                line,
                player_id=player_id,
                on_token=on_token,
                on_status=on_status,
                temperature=temperature,
                top_p=top_p,
                verbosity_level=verbosity,
            )
            out.write("\n")
            out.flush()
        except LLMConnectionError as exc:
            err.write(
                f"\n[LLM unreachable] Check your Ollama server or your API key.\n{exc}\n"
            )
            err.flush()
        except Exception as exc:  # ne jamais casser la boucle sur une erreur de tour
            err.write(f"\n[Error during turn] {exc}\n")
            err.flush()


# ---------------------------------------------------------------------------
# Câblage CLI
# ---------------------------------------------------------------------------

def run_play(args: argparse.Namespace) -> int:
    """Résout univers + save + LLM, construit la Session, lance la boucle."""
    from axiom.universe import Universe
    from axiom.session import Session
    from axiom.config import load_config, build_llm_from_config
    from axiom.savestore import create_save, list_saves, prepare_save_for_play
    from axiom.compile import CompileError
    from axiom.package import PackageError

    try:
        universe_db = _resolve_playable_db(args.universe)
    except (CompileError, PackageError) as exc:
        print(f"Could not prepare the universe: {exc}", file=sys.stderr)
        return 2
    if universe_db is None:
        print(f"Universe not found: {args.universe}", file=sys.stderr)
        return 2

    universe = Universe.load(universe_db)
    print(f"Universe: {universe.name}  ({universe_db})")

    # --- Choix de la sauvegarde (§7.6 : séparées + legacy embarquées) ---
    saves = list_saves(universe_db)
    save_id: str
    db_path: str  # base de la PARTIE (save db séparée, ou l'univers en legacy)
    mode: str = args.difficulty

    if args.save:
        save_id = args.save
        match = next((s for s in saves if s["save_id"] == save_id), None)
        if not match:
            print(f"Save {save_id} not found in this universe.", file=sys.stderr)
            return 2
        mode = match["difficulty"] or mode
        # Resynchronise la définition de la save si la source a été patchée.
        db_path = prepare_save_for_play(universe_db, save_id)
    elif args.new or not saves:
        info = create_save(universe_db, args.name, args.difficulty)
        save_id = info["save_id"]
        db_path = info["db_path"]
        print(f"New game created (save_id={save_id}, mode={args.difficulty}).")
    else:
        # Reprend la sauvegarde la plus récente (list_saves trie desc).
        save_id = saves[0]["save_id"]
        mode = saves[0]["difficulty"] or mode
        db_path = prepare_save_for_play(universe_db, save_id)
        print(f"Resuming the most recent save: {saves[0]['player_name']} ({save_id}).")

    # --- LLM ---
    cfg = load_config()
    llm = build_llm_from_config(cfg)
    if hasattr(llm, "is_available") and not llm.is_available():
        print(
            "Warning: the LLM backend is not responding (API key / local server?).",
            file=sys.stderr,
        )

    session = Session(db_path, save_id, llm=llm, mode=mode)

    play_loop(
        session,
        player_id=_resolve_player_id(db_path),
        first_message=_read_first_message(db_path),
        temperature=args.temperature,
        top_p=args.top_p,
        verbosity=args.verbosity,
    )
    print("\nGame suspended. See you soon.")
    return 0
