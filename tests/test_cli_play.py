"""
tests/test_cli_play.py

Tests du CLI `axiom play` (Pilier 1, Étape 8).

On teste les briques injectables (`play_loop`, `_handle_command`, le parseur)
avec une fausse `Session` : aucun LLM, aucun Qt, aucun stdin réel.
"""

from __future__ import annotations

import io

import pytest

from axiom.backends.base import LLMConnectionError
from axiom.cli.main import build_parser
from axiom.cli.play import _handle_command, _resolve_universe_path, play_loop


class FakeSession:
    """Imite l'API publique `Session` consommée par le CLI."""

    def __init__(self, *, turn_id=0, tokens=("Il ", "fait ", "nuit."), raise_exc=None):
        self.turn_id = turn_id
        self._tokens = tokens
        self._raise_exc = raise_exc
        self.calls: list[dict] = []
        self.rewound_to: int | None = None

    def take_turn(self, player_input, *, player_id="player", on_token=None,
                  on_status=None, temperature=0.7, top_p=1.0, verbosity_level="balanced"):
        self.calls.append({"input": player_input, "player_id": player_id})
        if on_status:
            on_status("Generating narrative…")
        if self._raise_exc is not None:
            raise self._raise_exc
        for tok in self._tokens:
            if on_token:
                on_token(tok)
        self.turn_id += 1
        return object()

    def current_stats(self):
        return {"player_1": {"HP": "10", "Gold": "5"}}

    def list_checkpoints(self):
        return [1, 3, 5]

    def rewind(self, target_turn_id):
        self.rewound_to = target_turn_id
        self.turn_id = target_turn_id
        return {"deleted": 2}


def _reader(lines):
    """Fabrique un `read` qui débite `lines` puis lève EOFError (fin de boucle)."""
    it = iter(lines)

    def read(_prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    return read


def test_play_loop_streams_tokens_and_forwards_player_input():
    out, err = io.StringIO(), io.StringIO()
    sess = FakeSession()
    play_loop(sess, read=_reader(["J'ouvre la porte.", "/quit"]), out=out, err=err)

    assert sess.calls[0]["input"] == "J'ouvre la porte."
    assert "Il fait nuit." in out.getvalue()


def test_play_loop_shows_first_message_only_on_fresh_game():
    out = io.StringIO()
    play_loop(FakeSession(turn_id=0), first_message="Bienvenue, aventurier.",
              read=_reader(["/quit"]), out=out, err=io.StringIO())
    assert "Bienvenue, aventurier." in out.getvalue()

    out2 = io.StringIO()
    play_loop(FakeSession(turn_id=4), first_message="Bienvenue, aventurier.",
              read=_reader(["/quit"]), out=out2, err=io.StringIO())
    assert "Bienvenue, aventurier." not in out2.getvalue()


def test_play_loop_quits_on_eof_without_taking_a_turn():
    sess = FakeSession()
    play_loop(sess, read=_reader([]), out=io.StringIO(), err=io.StringIO())
    assert sess.calls == []


def test_play_loop_survives_llm_connection_error():
    out, err = io.StringIO(), io.StringIO()
    sess = FakeSession(raise_exc=LLMConnectionError("429 quota"))
    # Après l'échec du 1er tour, la boucle doit continuer (2e saisie traitée).
    play_loop(sess, read=_reader(["action", "/quit"]), out=out, err=err)
    assert "LLM unreachable" in err.getvalue()
    assert len(sess.calls) == 1  # le tour a bien été tenté


def test_play_loop_survives_generic_error():
    err = io.StringIO()
    sess = FakeSession(raise_exc=RuntimeError("boom"))
    play_loop(sess, read=_reader(["action", "/quit"]), out=io.StringIO(), err=err)
    assert "Error during turn" in err.getvalue()


def test_handle_command_quit():
    assert _handle_command("/quit", FakeSession(), io.StringIO(), io.StringIO()) == "quit"
    assert _handle_command("/q", FakeSession(), io.StringIO(), io.StringIO()) == "quit"


def test_handle_command_stats_prints_entities():
    out = io.StringIO()
    assert _handle_command("/stats", FakeSession(), out, io.StringIO()) == "continue"
    assert "player_1" in out.getvalue() and "HP = 10" in out.getvalue()


def test_handle_command_checkpoints():
    out = io.StringIO()
    _handle_command("/checkpoints", FakeSession(), out, io.StringIO())
    assert "[1, 3, 5]" in out.getvalue()


def test_handle_command_rewind_calls_session():
    sess = FakeSession(turn_id=5)
    _handle_command("/rewind 2", sess, io.StringIO(), io.StringIO())
    assert sess.rewound_to == 2


def test_handle_command_rewind_requires_numeric_arg():
    err = io.StringIO()
    sess = FakeSession()
    _handle_command("/rewind", sess, io.StringIO(), err)
    assert sess.rewound_to is None
    assert "Usage" in err.getvalue()


def test_handle_command_unknown():
    err = io.StringIO()
    assert _handle_command("/wat", FakeSession(), io.StringIO(), err) == "continue"
    assert "Unknown command" in err.getvalue()


def test_build_parser_play_subcommand():
    args = build_parser().parse_args(["play", "world.axiom", "--difficulty", "Companion"])
    assert args.command == "play"
    assert args.universe == "world.axiom"
    assert args.difficulty == "Companion"


def test_play_requires_universe_argument():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["play"])


def test_resolve_universe_path_direct(tmp_path):
    f = tmp_path / "u.db"
    f.write_text("")
    assert _resolve_universe_path(str(f)) == f
    assert _resolve_universe_path(str(tmp_path / "nope.db")) is None
