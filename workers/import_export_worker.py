"""
workers/import_export_worker.py

QThread worker for .axiom archive import and export operations.

Thin Qt shell over the engine (`axiom.package`) : toute la logique de
packaging vit côté moteur (Pilier 2, règle ARCHITECTURE.md). Ce worker ne
fait que déporter l'appel hors du thread principal et traduire le résultat
en signaux Qt.

.axiom v2 = zip de l'arborescence source (TOML/MD) + cache compilé
`.axiom-cache/universe.db`. Les archives v1 (zip de JSON) sont converties
à la volée par `axiom.package.unpack_universe`.

Le mode `import_st` (cartes SillyTavern → .db plat) est indépendant du
format .axiom et reste implémenté ici.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from axiom.schema import create_universe_db


class ImportExportWorker(QThread):
    """Handles .axiom pack/unpack entirely off the main thread.

    Signals:
        import_complete(str):       Emitted with the new db_path on success.
        export_complete(str):       Emitted with the output .axiom path.
        progress_update(int, int):  (current_step, total_steps) for progress UI.
        error_occurred(str):        Human-readable error message.
        status_update(str):         Short message for QStatusBar.

    Args:
        mode:        "import" or "export".
        source_path: .axiom file path (import) or .db path (export).
        dest_path:   Target .db directory (import) or output .axiom path (export).
    """

    import_complete = Signal(str)
    export_complete = Signal(str)
    progress_update = Signal(int, int)
    error_occurred = Signal(str)
    status_update = Signal(str)

    def __init__(
        self,
        mode: str,
        source_path: str,
        dest_path: str,
    ) -> None:
        super().__init__()
        self._mode = mode
        self._source_path = source_path
        self._dest_path = dest_path

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Dispatch to the correct task based on mode.  Never raises."""
        try:
            if self._mode == "import":
                self._run_import()
            elif self._mode == "export":
                self._run_export()
            elif self._mode == "import_st":
                self._run_import_st()
            else:
                self.error_occurred.emit(f"Unknown mode: '{self._mode}'")
        except Exception as exc:
            self.error_occurred.emit(f"Unexpected error: {exc}")

    # ------------------------------------------------------------------
    # SillyTavern Import
    # ------------------------------------------------------------------

    def _run_import_st(self) -> None:
        """Parse a SillyTavern card and provision a new Axiom AI universe."""
        self.status_update.emit("Importing SillyTavern card...")
        self.progress_update.emit(0, 4)
        
        try:
            from core.st_parser import parse_st_card
            data = parse_st_card(self._source_path)
        except Exception as exc:
            self.error_occurred.emit(f"Failed to parse card: {exc}")
            return
            
        self.progress_update.emit(1, 4)
        
        # 1. DB Setup
        name = data.get("name", "Unknown Character")
        safe_name = "".join(c if c.isalnum() or c in "_ " else "_" for c in name)
        dest_dir = Path(self._dest_path)
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure unique name if conflict
        db_path = dest_dir / f"ST_{safe_name}.db"
        counter = 1
        while db_path.exists():
            db_path = dest_dir / f"ST_{safe_name}_{counter}.db"
            counter += 1
            
        db_path_str = str(db_path)
        
        try:
            create_universe_db(db_path_str)
        except Exception as exc:
            self.error_occurred.emit(f"Failed to create universe DB: {exc}")
            return
            
        self.progress_update.emit(2, 4)
        
        # 2. Extract Data
        default_prompt = (
            "You are the Game Master and the characters of this world. "
            "You MUST NOT act, speak, or think for the User/Player. "
            "Wait for the User input."
        )
        system_prompt = data.get("system_prompt", default_prompt)
        if not system_prompt.strip():
            system_prompt = default_prompt
            
        # Composite Lore (Phase 10 refinement)
        lore_parts = []
        if data.get("description"): lore_parts.append(f"### Description\n{data['description']}")
        if data.get("personality"): lore_parts.append(f"### Personality\n{data['personality']}")
        if data.get("scenario"):    lore_parts.append(f"### Scenario\n{data['scenario']}")
        composite_lore = "\n\n".join(lore_parts)

        # Phase 11: Collect variants for first message
        first_mes = data.get("first_mes", "")
        alt_greetings = data.get("alternate_greetings", [])
        if not alt_greetings and "data" in data:
            alt_greetings = data.get("data", {}).get("alternate_greetings", [])
        
        all_variants = [first_mes] if first_mes else []
        if isinstance(alt_greetings, list):
            for alt in alt_greetings:
                if isinstance(alt, str) and alt.strip():
                    all_variants.append(alt.strip())
                elif isinstance(alt, dict) and alt.get("message"):
                    all_variants.append(alt["message"].strip())
        
        # Use Axiom AI separator for multiverse first message
        first_msg_meta = "\n\n---VARIANT---\n\n".join(all_variants) if all_variants else ""

        meta = {
            "universe_name": name,
            "system_prompt": system_prompt,
            "global_lore": composite_lore,
            "first_message": first_msg_meta
        }
        
        entities = [{
            "entity_id": safe_name.replace(" ", "_").lower() or "npc_character",
            "entity_type": "npc",
            "name": name,
            "stats": {}
        }]
        
        lore_book = []
        import uuid
        def add_lore(cat: str, name_entry: str, content: str, keywords: str = ""):
            if content and content.strip():
                lore_book.append({
                    "entry_id": str(uuid.uuid4()),
                    "category": cat,
                    "name": name_entry,
                    "keywords": keywords,
                    "content": content.strip()
                })
        
        # Add basic character info to Lore Book
        add_lore("Example Messages", name, data.get("mes_example", ""))
        
        # Extract SillyTavern V2 Lorebook (character_book)
        char_book = data.get("character_book", {})
        if not char_book and "data" in data:
            char_book = data.get("data", {}).get("character_book", {})
            
        if char_book:
            entries = char_book.get("entries", [])
            # Support both array and object format for entries
            if isinstance(entries, dict):
                entries = list(entries.values())
                
            for entry in entries:
                if not entry.get("enabled", True):
                    continue
                
                entry_name = entry.get("name") or entry.get("comment") or "Lore Entry"
                entry_content = entry.get("content", "")
                
                # SillyTavern keys are the keywords
                keys = entry.get("keys", [])
                if isinstance(keys, list):
                    keywords_str = ", ".join(keys)
                else:
                    keywords_str = str(keys)
                
                add_lore("SillyTavern", entry_name, entry_content, keywords_str)

        self.progress_update.emit(3, 4)
        
        # 3. Populate DB
        try:
            self._populate_db(db_path_str, meta, entities, [], lore_book)
            
            with sqlite3.connect(db_path_str) as conn:
                conn.execute("PRAGMA foreign_keys=ON;")
                
                # Fulfill Phase 10 & 11 Directive: Inject Event directly into Event_Log
                if all_variants:
                    import uuid
                    import random
                    from datetime import datetime
                    
                    default_save_id = str(uuid.uuid4())
                    conn.execute(
                        "INSERT INTO Saves (save_id, player_name, difficulty, last_updated, player_persona) "
                        "VALUES (?, ?, ?, ?, ?);",
                        (default_save_id, "Player", "Normal", datetime.now().isoformat(), "")
                    )
                    
                    # Create structured multiverse payload
                    active_idx = random.randint(0, len(all_variants) - 1)
                    event_payload = {
                        "active": active_idx,
                        "variants": all_variants
                    }
                    
                    conn.execute(
                        "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                        "VALUES (?, ?, ?, ?, ?);",
                        (default_save_id, 0, "narrative_text", entities[0]["entity_id"], json.dumps(event_payload))
                    )

                conn.commit()
                
        except Exception as exc:
            self.error_occurred.emit(f"Failed to populate database: {exc}")
            return
            
        self.progress_update.emit(4, 4)
        self.status_update.emit(f"SillyTavern card '{name}' imported.")
        self.import_complete.emit(db_path_str)

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def _run_import(self) -> None:
        """Unpack a .axiom archive (v1 or v2) into a playable source tree."""
        from axiom.compile import CACHE_DB_NAME, CACHE_DIRNAME, CompileError
        from axiom.package import PackageError, unpack_universe

        self.status_update.emit("Importing universe…")
        total_steps = 2
        self.progress_update.emit(0, total_steps)

        try:
            src_dir = unpack_universe(self._source_path, self._dest_path)
        except (PackageError, CompileError) as exc:
            self.error_occurred.emit(f"Cannot import .axiom file: {exc}")
            return

        self.progress_update.emit(1, total_steps)

        db_path = str(Path(src_dir) / CACHE_DIRNAME / CACHE_DB_NAME)
        self.progress_update.emit(total_steps, total_steps)
        self.status_update.emit(f"Universe '{Path(src_dir).name}' imported.")
        self.import_complete.emit(db_path)

    @staticmethod
    def _populate_db(
        db_path: str,
        meta: dict,
        entities: list[dict],
        rules: list[dict],
        lore_book: list[dict] = None,
    ) -> None:
        """Write imported data into the freshly provisioned universe database.

        Args:
            db_path:   Path to the new universe .db.
            meta:      Universe_Meta key→value pairs.
            entities:  List of entity dicts (with nested stats).
            rules:     List of rule dicts.
            lore_book: List of lore book entry dicts.
        """
        lore_book = lore_book or []
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")

            # Universe_Meta
            for key, value in meta.items():
                conn.execute(
                    "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
                    (str(key), str(value)),
                )

            # Entities + Entity_Stats
            for entity in entities:
                conn.execute(
                    "INSERT OR REPLACE INTO Entities "
                    "(entity_id, entity_type, name, is_active) VALUES (?, ?, ?, 1);",
                    (entity["entity_id"], entity["entity_type"], entity["name"]),
                )
                for stat_key, stat_value in entity.get("stats", {}).items():
                    conn.execute(
                        "INSERT OR REPLACE INTO Entity_Stats "
                        "(entity_id, stat_key, stat_value) VALUES (?, ?, ?);",
                        (entity["entity_id"], str(stat_key), str(stat_value)),
                    )

            # Rules
            for rule in rules:
                conn.execute(
                    "INSERT OR REPLACE INTO Rules "
                    "(rule_id, priority, conditions, actions, target_entity) "
                    "VALUES (?, ?, ?, ?, ?);",
                    (
                        rule["rule_id"],
                        int(rule.get("priority", 0)),
                        json.dumps(rule.get("conditions", {})),
                        json.dumps(rule.get("actions", [])),
                        rule.get("target_entity", "*"),
                    ),
                )

            # Lore Book
            for entry in lore_book:
                conn.execute(
                    "INSERT OR REPLACE INTO Lore_Book "
                    "(entry_id, category, name, keywords, content) "
                    "VALUES (?, ?, ?, ?, ?);",
                    (
                        entry["entry_id"],
                        entry.get("category", ""),
                        entry.get("name", ""),
                        entry.get("keywords", ""),
                        entry.get("content", ""),
                    ),
                )

            conn.commit()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _run_export(self) -> None:
        """Pack a universe (source tree or flat .db) into a .axiom v2 archive."""
        from axiom.compile import CompileError
        from axiom.library import universe_root_for
        from axiom.package import PackageError, export_db_to_axiom, pack_universe

        self.status_update.emit("Exporting universe…")

        try:
            src_root = universe_root_for(self._source_path)
            if src_root is not None:
                # Univers-dossier : on zippe l'arbo telle quelle (texte = vérité).
                pack_universe(src_root, self._dest_path)
            else:
                # .db plat legacy : decompile → pack (définition seule, comme en v1).
                export_db_to_axiom(self._source_path, self._dest_path)
        except (PackageError, CompileError) as exc:
            self.error_occurred.emit(f"Failed to write .axiom archive: {exc}")
            return

        self.status_update.emit("Universe exported.")
        self.export_complete.emit(self._dest_path)
