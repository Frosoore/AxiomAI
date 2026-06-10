"""
database/backup_manager.py

Utility for automated Axiom AI database backups before destructive operations.
"""

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# See database/schema.py: the database layer avoids importing `core` at module
# load time to prevent a circular import; use the configured named logger.
logger = logging.getLogger("Axiom AI")

def create_auto_backup(db_path: str, reason: str) -> str | None:
    """Create a timestamped backup of the universe database.

    Copies the .db file to an 'auto_backups' subdirectory within the
    same directory as the database.

    Args:
        db_path: Absolute path to the .db file.
        reason:  Short string identifying why the backup was triggered
                 (e.g., 'rewind', 'hardcore_death').

    Returns:
        The path to the created backup file, or None if it failed.
    """
    try:
        source_path = Path(db_path)
        if not source_path.exists():
            logger.error(f"Backup failed: Source database not found at {db_path}")
            return None

        # Create auto_backups dir next to the DB
        backup_dir = source_path.parent / "auto_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename: 20231027_153000_rewind_myuniverse.db
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_name = source_path.name
        backup_filename = f"{timestamp}_{reason}_{db_name}"
        backup_path = backup_dir / backup_filename

        # TICKET-028 : vide le WAL dans le fichier principal avant la copie,
        # pour que chaque backup tienne en UN seul fichier (pas de sidecars).
        checkpointed = _checkpoint_wal(source_path)

        # Copy the main DB file
        shutil.copy2(source_path, backup_path)

        if not checkpointed:
            # Base verrouillée : on retombe sur l'ancienne copie avec sidecars
            # plutôt que de produire un backup potentiellement incomplet.
            for suffix in ["-wal", "-shm"]:
                aux_file = source_path.with_name(source_path.name + suffix)
                if aux_file.exists():
                    shutil.copy2(aux_file, backup_path.with_name(backup_filename + suffix))

        _absorb_legacy_sidecars(backup_dir)

        logger.info(f"Automated backup created: {backup_path} (Reason: {reason})")
        return str(backup_path)

    except Exception as e:
        logger.error(f"Failed to create automated backup for {db_path}: {e}")
        return None


def _checkpoint_wal(db_path: Path) -> bool:
    """Merge the WAL into the main file. Returns False if the db was locked."""
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
        finally:
            conn.close()
        # row[0] == 1 → checkpoint bloqué (writer/reader concurrent).
        return bool(row) and row[0] == 0
    except sqlite3.Error as e:
        logger.warning(f"WAL checkpoint failed for {db_path}: {e}")
        return False


def _absorb_legacy_sidecars(backup_dir: Path) -> None:
    """Fold leftover `-wal`/`-shm` sidecars of past backups into their main file.

    Les anciens backups étaient copiés en trois fichiers ; ouvrir la base
    rejoue son WAL, le checkpoint l'absorbe, puis les sidecars sont supprimés.
    Un sidecar orphelin (base principale disparue) est supprimé tel quel.
    """
    for wal in backup_dir.glob("*.db-wal"):
        main = wal.with_name(wal.name[: -len("-wal")])
        if not main.exists() or _checkpoint_wal(main):
            for suffix in ["-wal", "-shm"]:
                sidecar = main.with_name(main.name + suffix)
                if sidecar.exists():
                    sidecar.unlink()
    for shm in backup_dir.glob("*.db-shm"):
        main = shm.with_name(shm.name[: -len("-shm")])
        # Un -shm sans -wal (ou sans base) ne porte aucune donnée.
        if not main.exists() or not main.with_name(main.name + "-wal").exists():
            shm.unlink()
