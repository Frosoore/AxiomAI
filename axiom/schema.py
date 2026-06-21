"""
database/schema.py

Provisions a fresh Axiom AI universe SQLite database with all required tables.
Every universe is stored in a single .db file; this module is the sole authority
over the schema definition.
"""

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

# NOTE: the database layer must not import `core` at module load time. Doing so
# triggers core/__init__ (which eagerly imports the arbitrator -> event_sourcing
# -> database.schema), creating a circular import. We grab the already-configured
# named logger directly instead. core.logger.setup_logger() owns the handlers.
logger = logging.getLogger("Axiom AI")


# ---------------------------------------------------------------------------
# DDL statements — one constant per table for clarity and testability
# ---------------------------------------------------------------------------

_DDL_UNIVERSE_META = """
CREATE TABLE IF NOT EXISTS Universe_Meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_DDL_ENTITIES = """
CREATE TABLE IF NOT EXISTS Entities (
    entity_id   TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK(entity_type IN ('player', 'npc', 'faction', 'world')),
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    origin      TEXT NOT NULL DEFAULT 'definition' CHECK(origin IN ('definition', 'runtime'))
);
"""

_DDL_ENTITY_STATS = """
CREATE TABLE IF NOT EXISTS Entity_Stats (
    entity_id  TEXT NOT NULL,
    stat_key   TEXT NOT NULL,
    stat_value TEXT NOT NULL,
    PRIMARY KEY (entity_id, stat_key),
    FOREIGN KEY (entity_id) REFERENCES Entities(entity_id) ON DELETE CASCADE
);
"""

_DDL_RULES = """
CREATE TABLE IF NOT EXISTS Rules (
    rule_id       TEXT PRIMARY KEY,
    priority      INTEGER NOT NULL DEFAULT 0,
    conditions    TEXT NOT NULL,
    actions       TEXT NOT NULL,
    target_entity TEXT NOT NULL DEFAULT '*'
);
"""

_DDL_ACTIVE_MODIFIERS = """
CREATE TABLE IF NOT EXISTS Active_Modifiers (
    modifier_id     TEXT PRIMARY KEY,
    save_id         TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    stat_key        TEXT NOT NULL,
    delta           REAL NOT NULL,
    minutes_remaining INTEGER NOT NULL CHECK(minutes_remaining >= 0),
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES Entities(entity_id) ON DELETE CASCADE
);
"""

_DDL_SAVES = """
CREATE TABLE IF NOT EXISTS Saves (
    save_id        TEXT PRIMARY KEY,
    player_name    TEXT NOT NULL,
    difficulty     TEXT NOT NULL CHECK(difficulty IN ('Normal', 'Hardcore', 'Companion')),
    last_updated   TEXT NOT NULL,
    player_persona TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT ''
);
"""

_DDL_EVENT_LOG = """
CREATE TABLE IF NOT EXISTS Event_Log (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    save_id       TEXT NOT NULL,
    turn_id       INTEGER NOT NULL,
    event_type    TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    payload       TEXT NOT NULL,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE
);
"""

_DDL_STATE_CACHE = """
CREATE TABLE IF NOT EXISTS State_Cache (
    save_id    TEXT NOT NULL,
    entity_id  TEXT NOT NULL,
    stat_key   TEXT NOT NULL,
    stat_value TEXT NOT NULL,
    PRIMARY KEY (save_id, entity_id, stat_key),
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE
);
"""

_DDL_LORE_BOOK = """
CREATE TABLE IF NOT EXISTS Lore_Book (
    entry_id TEXT PRIMARY KEY,
    category TEXT NOT NULL DEFAULT '',
    name     TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '',
    content  TEXT NOT NULL DEFAULT ''
);
"""

# Structured facts extracted from the narrative by the LLM in "living" memory
# mode (Hindsight-inspired who/what/when/where/why model, causal links deferred).
# Lives in the same DB as Event_Log / State_Cache, keyed by save_id + turn_id, so
# CheckpointManager.rewind deletes future facts in the same transaction as events.
_DDL_FACTS = """
CREATE TABLE IF NOT EXISTS Facts (
    fact_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    save_id     TEXT NOT NULL,
    turn_id     INTEGER NOT NULL,
    fact_type   TEXT NOT NULL DEFAULT 'world',
    who         TEXT NOT NULL DEFAULT '',
    what        TEXT NOT NULL DEFAULT '',
    fact_when   TEXT NOT NULL DEFAULT '',
    fact_where  TEXT NOT NULL DEFAULT '',
    why         TEXT NOT NULL DEFAULT '',
    entities    TEXT NOT NULL DEFAULT '',
    statement   TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE
);
"""

# Consolidated beliefs ("observations", Hindsight-inspired) distilled from Facts
# by the LLM in "living" memory mode, Phase 3. A belief evolves (CREATE/UPDATE/
# DELETE) and remembers WHICH facts support it via `sources` (a JSON list of
# {fact_id, turn_id}). The turn ids are the rollback key: rewinding to turn N
# drops beliefs created after N and recomputes the proof_count of the survivors
# from their sources at turns <= N — so beliefs roll back atomically with the
# facts and events they derive from. Same DB as Facts / Event_Log.
_DDL_OBSERVATIONS = """
CREATE TABLE IF NOT EXISTS Observations (
    observation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    save_id         TEXT NOT NULL,
    subject         TEXT NOT NULL DEFAULT '',
    statement       TEXT NOT NULL,
    proof_count     INTEGER NOT NULL DEFAULT 1,
    sources         TEXT NOT NULL DEFAULT '[]',
    history         TEXT NOT NULL DEFAULT '[]',
    created_turn_id INTEGER NOT NULL DEFAULT 0,
    updated_turn_id INTEGER NOT NULL DEFAULT 0,
    stale           INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE
);
"""

# Mental models (Hindsight §7.8): one curated, synthetic profile per subject (a
# character, or "" for the world), sitting *above* the beliefs in the recall
# hierarchy. Regenerated periodically by the LLM from the subject's beliefs, so a
# model is always reconstructible — rollback only needs to drop models created
# after the target turn and flag the survivors stale for the next refresh. Same DB
# as Observations / Facts. ``sources`` holds the observation_ids it was built from.
_DDL_MENTAL_MODELS = """
CREATE TABLE IF NOT EXISTS Mental_Models (
    model_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    save_id         TEXT NOT NULL,
    subject         TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL,
    sources         TEXT NOT NULL DEFAULT '[]',
    created_turn_id INTEGER NOT NULL DEFAULT 0,
    updated_turn_id INTEGER NOT NULL DEFAULT 0,
    stale           INTEGER NOT NULL DEFAULT 0,
    UNIQUE (save_id, subject),
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE
);
"""

_DDL_GLOBAL_PERSONAS = """
CREATE TABLE IF NOT EXISTS Global_Personas (
    persona_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL
);
"""

_DDL_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS Snapshots (
    save_id    TEXT NOT NULL,
    turn_id    INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    PRIMARY KEY (save_id, turn_id),
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE
);
"""

# Per-turn capture of the Active_Modifiers table so rewind can restore temporary
# buffs/debuffs to their end-of-turn-N state (TICKET-074). Active_Modifiers decays
# in *minutes* and is hard-deleted on expiry, so it can't be replayed from the
# turn-keyed Event_Log; a snapshot is the only faithful source. A row is written
# only on turns where the save has active modifiers (the common case is none → no
# rows), so absence of a row for a turn means "no modifiers then".
_DDL_MODIFIER_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS Modifier_Snapshots (
    save_id    TEXT NOT NULL,
    turn_id    INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    PRIMARY KEY (save_id, turn_id),
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE
);
"""

_DDL_STAT_DEFINITIONS = """
CREATE TABLE IF NOT EXISTS Stat_Definitions (
    stat_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    value_type  TEXT NOT NULL CHECK(value_type IN ('numeric', 'categorical')),
    parameters  TEXT NOT NULL DEFAULT '{}'
);
"""

_DDL_TIMELINE = """
CREATE TABLE IF NOT EXISTS Timeline (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    save_id       TEXT NOT NULL,
    turn_id       INTEGER NOT NULL,
    in_game_time  INTEGER NOT NULL,
    description   TEXT NOT NULL,
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE
);
"""

_DDL_SCHEDULED_EVENTS = """
CREATE TABLE IF NOT EXISTS Scheduled_Events (
    event_id        TEXT PRIMARY KEY,
    trigger_minute  INTEGER NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL
);
"""

_DDL_FIRED_SCHEDULED_EVENTS = """
CREATE TABLE IF NOT EXISTS Fired_Scheduled_Events (
    save_id  TEXT NOT NULL,
    event_id TEXT NOT NULL,
    fired_turn_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (save_id, event_id),
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES Scheduled_Events(event_id) ON DELETE CASCADE
);
"""

_DDL_ITEM_DEFINITIONS = """
CREATE TABLE IF NOT EXISTS Item_Definitions (
    item_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT 'misc',
    weight      REAL NOT NULL DEFAULT 0.0,
    rarity      TEXT NOT NULL DEFAULT 'common'
);
"""

_DDL_ITEMS_INVENTORY = """
CREATE TABLE IF NOT EXISTS Items_Inventory (
    save_id     TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1 CHECK(quantity >= 0),
    PRIMARY KEY (save_id, entity_id, item_id),
    FOREIGN KEY (save_id) REFERENCES Saves(save_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES Entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES Item_Definitions(item_id) ON DELETE CASCADE
);
"""

_DDL_STORY_SETUP = """
CREATE TABLE IF NOT EXISTS Story_Setup (
    setup_id       TEXT PRIMARY KEY,
    question       TEXT NOT NULL,
    type           TEXT NOT NULL CHECK(type IN ('text', 'single_choice', 'multi_choice')),
    options        TEXT NOT NULL DEFAULT '[]',
    max_selections INTEGER NOT NULL DEFAULT 1,
    priority       INTEGER NOT NULL DEFAULT 0
);
"""

_DDL_LOCATIONS = """
CREATE TABLE IF NOT EXISTS Locations (
    location_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    scale       TEXT NOT NULL CHECK(scale IN ('universe', 'galaxy', 'world', 'country', 'zone', 'city', 'district', 'building', 'room', 'poi')),
    parent_id   TEXT,
    description TEXT NOT NULL DEFAULT '',
    x           REAL DEFAULT 0,
    y           REAL DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES Locations(location_id) ON DELETE CASCADE
);
"""

_DDL_LOCATION_CONNECTIONS = """
CREATE TABLE IF NOT EXISTS Location_Connections (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    distance_km INTEGER NOT NULL,
    PRIMARY KEY (source_id, target_id),
    FOREIGN KEY (source_id) REFERENCES Locations(location_id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES Locations(location_id) ON DELETE CASCADE
);
"""

_ALL_DDL: list[str] = [
    _DDL_UNIVERSE_META,
    _DDL_ENTITIES,
    _DDL_ENTITY_STATS,
    _DDL_RULES,
    _DDL_STAT_DEFINITIONS,
    _DDL_ACTIVE_MODIFIERS,
    _DDL_SAVES,
    _DDL_EVENT_LOG,
    _DDL_STATE_CACHE,
    _DDL_LORE_BOOK,
    _DDL_FACTS,
    _DDL_OBSERVATIONS,
    _DDL_MENTAL_MODELS,
    _DDL_SNAPSHOTS,
    _DDL_MODIFIER_SNAPSHOTS,
    _DDL_TIMELINE,
    _DDL_SCHEDULED_EVENTS,
    _DDL_FIRED_SCHEDULED_EVENTS,
    _DDL_ITEM_DEFINITIONS,
    _DDL_ITEMS_INVENTORY,
    _DDL_STORY_SETUP,
    _DDL_LOCATIONS,
    _DDL_LOCATION_CONNECTIONS,
]

# Canonical set of table names produced by create_universe_db
EXPECTED_TABLES: frozenset[str] = frozenset({
    "Universe_Meta",
    "Entities",
    "Entity_Stats",
    "Rules",
    "Stat_Definitions",
    "Active_Modifiers",
    "Saves",
    "Event_Log",
    "State_Cache",
    "Lore_Book",
    "Facts",
    "Observations",
    "Mental_Models",
    "Snapshots",
    "Modifier_Snapshots",
    "Timeline",
    "Scheduled_Events",
    "Fired_Scheduled_Events",
    "Item_Definitions",
    "Items_Inventory",
    "Story_Setup",
    "Locations",
    "Location_Connections",
})


# Secondary indexes for the per-turn hot path. SQLite only auto-indexes PRIMARY
# KEY / UNIQUE columns, so without these the queries below full-scan a table that
# grows by (at least) one row every turn → cost rises linearly over a long game:
#   - Event_Log      : get_events() filters WHERE save_id=? AND turn_id>? each turn.
#   - Active_Modifiers: the decay tick filters WHERE save_id=? each turn.
#   - Timeline       : time resolution filters WHERE save_id=? (AND turn_id<=?).
# State_Cache / Snapshots / Fired_Scheduled_Events already lead their PRIMARY KEY
# with save_id, so the same lookups are already index-backed — no extra index.
# These index columns double as the FK child index, so cascade deletes of a Save
# stop scanning the child tables too.
_DDL_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_event_log_save_turn ON Event_Log(save_id, turn_id);",
    "CREATE INDEX IF NOT EXISTS idx_active_modifiers_save ON Active_Modifiers(save_id);",
    "CREATE INDEX IF NOT EXISTS idx_timeline_save_turn ON Timeline(save_id, turn_id);",
    "CREATE INDEX IF NOT EXISTS idx_facts_save_turn ON Facts(save_id, turn_id);",
    "CREATE INDEX IF NOT EXISTS idx_observations_save_turn ON Observations(save_id, updated_turn_id);",
    "CREATE INDEX IF NOT EXISTS idx_mental_models_save_turn ON Mental_Models(save_id, updated_turn_id);",
]


def ensure_facts_table(conn: "sqlite3.Connection") -> None:
    """Create the Facts table + index on an already-open connection if missing.

    Lets the facts storage layer (and rewind) self-migrate save DBs provisioned
    before the Facts table existed, without a central migration runner. Idempotent
    (CREATE … IF NOT EXISTS); reuses the caller's transaction.
    """
    conn.execute(_DDL_FACTS)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_facts_save_turn ON Facts(save_id, turn_id);"
    )


def ensure_observations_table(conn: "sqlite3.Connection") -> None:
    """Create the Observations table + index on an open connection if missing.

    Self-migration for save DBs provisioned before the beliefs layer existed
    (Phase 3), mirroring ensure_facts_table. Idempotent; reuses the caller's
    transaction so rewind can roll beliefs back atomically with facts/events.
    """
    conn.execute(_DDL_OBSERVATIONS)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_observations_save_turn "
        "ON Observations(save_id, updated_turn_id);"
    )


def ensure_mental_models_table(conn: "sqlite3.Connection") -> None:
    """Create the Mental_Models table + index on an open connection if missing.

    Self-migration for save DBs provisioned before the mental-models layer existed
    (Hindsight §7.8), mirroring ensure_observations_table. Idempotent; reuses the
    caller's transaction so rewind can roll models back atomically with beliefs.
    """
    conn.execute(_DDL_MENTAL_MODELS)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mental_models_save_turn "
        "ON Mental_Models(save_id, updated_turn_id);"
    )


def ensure_modifier_snapshots_table(conn: "sqlite3.Connection") -> None:
    """Create the Modifier_Snapshots table on an open connection if missing.

    Self-migration for save DBs provisioned before the modifier-rewind support
    existed (TICKET-074), mirroring ensure_facts_table. Idempotent; reuses the
    caller's transaction so rewind can restore modifiers atomically with the rest.
    """
    conn.execute(_DDL_MODIFIER_SNAPSHOTS)


def ensure_fired_event_turn_column(conn: "sqlite3.Connection") -> None:
    """Add ``fired_turn_id`` to Fired_Scheduled_Events on an open connection.

    Records the turn at which a scheduled event fired so rewind can "un-fire"
    events whose firing turn is now in the future (TICKET-075), mirroring how
    Event_Log/Facts roll back. Self-migration for save DBs provisioned before
    this column existed; idempotent and reuses the caller's transaction.

    Legacy rows (fired before the column existed) default to ``0`` and therefore
    stay fired across any rewind to a non-negative turn — the conservative choice
    when the real firing turn is unknown.
    """
    cols = {row[1] for row in conn.execute(
        "PRAGMA table_info(Fired_Scheduled_Events);"
    ).fetchall()}
    if "fired_turn_id" not in cols:
        conn.execute(
            "ALTER TABLE Fired_Scheduled_Events "
            "ADD COLUMN fired_turn_id INTEGER NOT NULL DEFAULT 0;"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_universe_db(db_path: str) -> None:
    """Provision a fresh Axiom AI universe database at the given path.

    Creates the file (and any missing parent directories) if it does not
    already exist, then executes all DDL statements inside a single
    transaction.  Calling this function on an already-provisioned database
    is idempotent (CREATE TABLE IF NOT EXISTS).

    Args:
        db_path: Absolute or relative filesystem path for the .db file.

    Raises:
        sqlite3.Error: If the database cannot be opened or the DDL fails.
        OSError: If parent directories cannot be created.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # closing() (et pas seulement `with conn:`) : `with sqlite3.connect()` ne
    # ferme PAS la connexion, il ne gère que la transaction. En WAL, le `-shm`
    # reste mappé en mémoire tant que la connexion vit ; sous Windows ce handle
    # persistant bloque le renommage atomique du .tmp (WinError 32). On ferme
    # donc explicitement, sans dépendre du refcount du GC.
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        for ddl in _ALL_DDL:
            conn.execute(ddl)
        for ddl in _DDL_INDEXES:
            conn.execute(ddl)
        conn.commit()


def create_global_db(db_path: str) -> None:
    """Provision the global user database (personas, etc).

    Args:
        db_path: Path to the global .db file.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path))) as conn:
        conn.execute(_DDL_GLOBAL_PERSONAS)
        conn.commit()


def migrate_indexes(db_path: str) -> None:
    """Create the per-turn hot-path indexes on an already-provisioned database.

    Idempotent (CREATE INDEX IF NOT EXISTS): brings databases provisioned before
    the indexes existed up to date, so long games stop full-scanning Event_Log /
    Active_Modifiers / Timeline every turn (see ``_DDL_INDEXES``). A missing
    target table (older / partial schema) is skipped rather than raised.
    """
    with closing(sqlite3.connect(str(db_path))) as conn:
        for ddl in _DDL_INDEXES:
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError as exc:
                # "no such table" on a partial/legacy schema — the index simply
                # gets created the next time that table exists. Anything else is
                # a real error and must surface.
                if "no such table" not in str(exc).lower():
                    raise
        conn.commit()


def migrate_entities_table(db_path: str) -> None:
    """Add the description column to an existing Entities table if absent."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        try:
            conn.execute(
                "ALTER TABLE Entities ADD COLUMN description TEXT NOT NULL DEFAULT '';"
            )
            conn.commit()
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    migrate_entities_origin_column(db_path)


def migrate_entities_origin_column(db_path: str) -> bool:
    """Add the `origin` provenance column to Entities if absent.

    `origin` distingue les entités issues de la **définition** (compilées depuis
    l'arbo texte / créées au Creator Studio) de celles créées **en jeu** (entité
    joueur, PNJ découverts par extraction). Le hot reload (`axiom.dev`) ne
    gère que les lignes `definition` — sans cette colonne il supprimerait le
    joueur à la première resynchronisation.

    Returns:
        True si la colonne vient d'être ajoutée (DB d'avant la migration) —
        l'appelant peut alors « amnistier » les lignes existantes au lieu de
        les traiter en strictes lignes de définition.
    """
    with closing(sqlite3.connect(str(db_path))) as conn:
        try:
            conn.execute(
                "ALTER TABLE Entities ADD COLUMN origin TEXT NOT NULL DEFAULT 'definition' "
                "CHECK(origin IN ('definition', 'runtime'));"
            )
            conn.commit()
            return True
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
            return False


def migrate_saves_table(db_path: str) -> None:
    """Add the player_persona and created_at columns to an existing Saves table if absent.

    Idempotent — safe to call on databases provisioned before Phase 5.
    Silently succeeds if the columns already exist.

    Args:
        db_path: Path to an existing universe .db file.

    Raises:
        sqlite3.Error: If the ALTER TABLE statement fails for a reason other
                       than the column already existing.
    """
    with closing(sqlite3.connect(str(db_path))) as conn:
        try:
            conn.execute(
                "ALTER TABLE Saves ADD COLUMN player_persona TEXT NOT NULL DEFAULT '';"
            )
            conn.commit()
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise

        try:
            conn.execute(
                "ALTER TABLE Saves ADD COLUMN created_at TEXT NOT NULL DEFAULT '';"
            )
            conn.execute(
                "UPDATE Saves SET created_at = last_updated WHERE created_at = '';"
            )
            conn.commit()
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def migrate_active_modifiers_table(db_path: str) -> None:
    """Add the save_id column to an existing Active_Modifiers table if absent (TICKET-024).

    Avant ce correctif, `Active_Modifiers` n'avait pas de `save_id` : les modifiers
    étaient partagés entre toutes les saves d'un univers. La migration ajoute la colonne
    (les rows héritées prennent save_id='' → orphelines, ignorées par le filtrage par save).
    Idempotent.
    """
    with closing(sqlite3.connect(str(db_path))) as conn:
        try:
            conn.execute(
                "ALTER TABLE Active_Modifiers ADD COLUMN save_id TEXT NOT NULL DEFAULT '';"
            )
            conn.commit()
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def migrate_lore_book_table(db_path: str) -> None:
    """Create the Lore_Book table if it does not exist in an older database.

    Idempotent — safe to call on any universe database, regardless of age.
    Uses CREATE TABLE IF NOT EXISTS so it silently succeeds when the table
    already exists.

    Args:
        db_path: Path to an existing universe .db file.

    Raises:
        sqlite3.Error: If the statement fails for an unexpected reason.
    """
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(_DDL_LORE_BOOK)
        conn.commit()


def migrate_stat_definitions_table(db_path: str) -> None:
    """Create the Stat_Definitions table if it does not exist in an older database."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(_DDL_STAT_DEFINITIONS)
        conn.commit()


def migrate_timeline_table(db_path: str) -> None:
    """Create the Timeline table if it does not exist in an older database.

    Idempotent — safe to call on any universe database.
    Uses CREATE TABLE IF NOT EXISTS so it silently succeeds when the table
    already exists.

    Args:
        db_path: Path to an existing universe .db file.
    """
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(_DDL_TIMELINE)
        conn.commit()


def migrate_scheduled_events_table(db_path: str) -> None:
    """Create the Scheduled_Events table if it does not exist in an older database.

    Idempotent — safe to call on any universe database.
    Uses CREATE TABLE IF NOT EXISTS so it silently succeeds when the table
    already exists.

    Args:
        db_path: Path to an existing universe .db file.
    """
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(_DDL_SCHEDULED_EVENTS)
        conn.commit()


def migrate_inventory_tables(db_path: str) -> None:
    """Create Item_Definitions and Items_Inventory tables if they do not exist."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(_DDL_ITEM_DEFINITIONS)
        conn.execute(_DDL_ITEMS_INVENTORY)
        conn.commit()


def migrate_story_setup_table(db_path: str) -> None:
    """Create the Story_Setup table if it does not exist in an older database."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute(_DDL_STORY_SETUP)
        conn.commit()


def migrate_location_tables(db_path: str) -> None:
    """Create Locations and Location_Connections tables if they do not exist, or migrate them if constraints changed."""
    with closing(sqlite3.connect(str(db_path))) as conn:
        # Check if table exists
        row_loc = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='Locations';").fetchone()
        row_conn = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='Location_Connections';").fetchone()
        
        if not row_loc:
            # Table doesn't exist, just create them
            conn.execute(_DDL_LOCATIONS)
            conn.execute(_DDL_LOCATION_CONNECTIONS)
        else:
            # Table exists, check for migration needs:
            # 1. New scales (room/poi)
            # 2. Unit change (minutes to km)
            # 3. Corruption (dangling FKs pointing to Locations_Old)
            current_sql_loc = row_loc[0]
            current_sql_conn = row_conn[0] if row_conn else ""
            
            needs_scale_update = ("'room'" not in current_sql_loc or "'poi'" not in current_sql_loc)
            needs_unit_update = ("distance_minutes" in current_sql_conn)
            is_corrupted = ("Locations_Old" in current_sql_conn)
            
            if needs_scale_update or needs_unit_update or is_corrupted:
                # Migration needed or corruption detected
                conn.execute("PRAGMA foreign_keys=OFF;")
                try:
                    conn.execute("BEGIN TRANSACTION;")
                    
                    # A. Migrate Locations
                    conn.execute("DROP TABLE IF EXISTS Locations_Old;")
                    conn.execute("ALTER TABLE Locations RENAME TO Locations_Old;")
                    conn.execute(_DDL_LOCATIONS)
                    # Copy data safely
                    conn.execute(
                        "INSERT INTO Locations (location_id, name, scale, parent_id, description, x, y) "
                        "SELECT location_id, name, scale, parent_id, description, x, y FROM Locations_Old;"
                    )
                    conn.execute("DROP TABLE Locations_Old;")
                    
                    # B. Migrate Location_Connections
                    if row_conn:
                        # Detect which column to copy from
                        info = conn.execute("PRAGMA table_info(Location_Connections);").fetchall()
                        cols = [i[1] for i in info]
                        source_col = "distance_km" if "distance_km" in cols else "distance_minutes"
                        
                        conn.execute("DROP TABLE IF EXISTS Location_Connections_Old;")
                        conn.execute("ALTER TABLE Location_Connections RENAME TO Location_Connections_Old;")
                        conn.execute(_DDL_LOCATION_CONNECTIONS)
                        # Map the old column (minutes or km) to the new distance_km
                        conn.execute(
                            f"INSERT INTO Location_Connections (source_id, target_id, distance_km) "
                            f"SELECT source_id, target_id, {source_col} FROM Location_Connections_Old;"
                        )
                        conn.execute("DROP TABLE Location_Connections_Old;")
                    else:
                        conn.execute(_DDL_LOCATION_CONNECTIONS)
                    
                    conn.execute("COMMIT;")
                    logger.debug("[SCHEMA] Location tables successfully migrated/repaired.")
                except Exception as e:
                    conn.execute("ROLLBACK;")
                    logger.error(f"[SCHEMA] Migration failed, rolled back: {e}")
                    # If migration fails, we don't raise here to avoid blocking app start, 
                    # but the DB task worker will likely fail again on usage.
                finally:
                    conn.execute("PRAGMA foreign_keys=ON;")
        
        conn.commit()


def migrate_saves_difficulty_constraint(db_path: str) -> None:
    """Migrate the Saves table to update the difficulty CHECK constraint.
    
    To avoid breaking foreign keys in child tables, we MUST NOT rename the 
    original table to something else (like Saves_Old), because child tables
    will update their references to point to the new name.
    
    Instead, we create a temp table, copy data, drop the original, and 
    rename temp to original.
    """
    with closing(sqlite3.connect(str(db_path))) as conn:
        # Check current constraint
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='Saves';").fetchone()
        if not row:
            return
        
        sql = row[0]
        if "'Companion'" in sql:
            # Already updated
            return
            
        conn.execute("PRAGMA foreign_keys=OFF;")
        try:
            conn.execute("BEGIN TRANSACTION;")
            
            # 1. Create temporary table with NEW schema
            # We replace 'CREATE TABLE IF NOT EXISTS Saves' with 'CREATE TABLE Saves_Temp'
            new_ddl = _DDL_SAVES.replace("CREATE TABLE IF NOT EXISTS Saves", "CREATE TABLE Saves_Temp")
            conn.execute(new_ddl)
            
            # 2. Copy data
            conn.execute(
                "INSERT INTO Saves_Temp (save_id, player_name, difficulty, last_updated, player_persona) "
                "SELECT save_id, player_name, difficulty, last_updated, player_persona FROM Saves;"
            )
            
            # 3. Drop original table (FKs in child tables now point to a dangling 'Saves')
            conn.execute("DROP TABLE Saves;")
            
            # 4. Rename temp to original (FKs reconnect)
            conn.execute("ALTER TABLE Saves_Temp RENAME TO Saves;")
            
            conn.execute("COMMIT;")
            logger.debug("[SCHEMA] Saves table successfully migrated to support 'Companion' mode.")
        except Exception as e:
            conn.execute("ROLLBACK;")
            logger.error(f"[SCHEMA] Saves constraint migration failed: {e}")
        finally:
            conn.execute("PRAGMA foreign_keys=ON;")


class _ClosingConnection(sqlite3.Connection):
    """A connection whose ``with`` block **closes** it on exit (not just commit).

    Plain ``with sqlite3.connect(...) as conn:`` only commits/rolls back the
    transaction — the connection (and, in WAL mode, the memory-mapped ``-shm``
    handle) stays open until the garbage collector reclaims it. On Windows that
    lingering handle locks the ``.db`` file, so any later ``os.replace`` /
    ``unlink`` on it fails with ``PermissionError`` (WinError 32). On POSIX an
    open handle never blocks a rename/unlink, which is why this stayed hidden in
    Linux testing.

    Closing on block exit makes every ``with get_connection(...) as conn:``
    site Windows-safe without touching the ~75 call sites. All callers use the
    connection inside a single ``with`` block and discard it afterwards, so
    closing eagerly is always correct here.
    """

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            super().__exit__(exc_type, exc_val, exc_tb)  # commit or rollback
        finally:
            self.close()
        return False


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open and return a configured SQLite connection to an existing universe db.

    The connection is meant to be used as a context manager
    (``with get_connection(...) as conn:``): exiting the block commits (or rolls
    back) **and closes** it — releasing the file handle immediately, which
    Windows requires before the db can be renamed or deleted. Foreign-key
    enforcement and WAL journal mode are enabled automatically.

    Args:
        db_path: Path to an existing .db file created by create_universe_db().

    Returns:
        An open sqlite3.Connection with FK enforcement and WAL enabled.

    Raises:
        FileNotFoundError: If db_path does not point to an existing file.
        sqlite3.Error: If the connection cannot be established.
    """
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Universe database not found: {db_path}")

    conn = sqlite3.connect(str(db_path), factory=_ClosingConnection)
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn
