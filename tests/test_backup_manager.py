"""tests/test_backup_manager.py

TICKET-028 (cosmétique) : `create_auto_backup` produit des backups en UN seul
fichier (WAL vidé avant copie, pas de sidecars -wal/-shm), et absorbe les
sidecars laissés par les anciens backups dans `auto_backups/`.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from database.backup_manager import create_auto_backup


def _open_wal_db(path: Path) -> sqlite3.Connection:
    """Une base WAL avec une écriture encore dans les sidecars.

    La connexion est laissée OUVERTE par l'appelant : fermer la dernière
    connexion checkpointerait et supprimerait le -wal.
    """
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("CREATE TABLE t (x INTEGER);")
    conn.execute("INSERT INTO t VALUES (42);")
    conn.commit()
    return conn


def test_backup_en_un_seul_fichier(tmp_path: Path):
    db = tmp_path / "demo.db"
    conn = _open_wal_db(db)
    try:
        assert db.with_name(db.name + "-wal").exists()

        backup = create_auto_backup(str(db), "test")
        assert backup is not None
        backup = Path(backup)
        assert backup.exists()
        assert not Path(str(backup) + "-wal").exists()
        assert not Path(str(backup) + "-shm").exists()

        # Le backup contient bien la donnée qui n'était que dans le WAL.
        with sqlite3.connect(str(backup)) as check:
            assert check.execute("SELECT x FROM t;").fetchone() == (42,)
    finally:
        conn.close()


def test_absorbe_les_sidecars_historiques(tmp_path: Path):
    db = tmp_path / "demo.db"
    conn = _open_wal_db(db)

    # Simule un ancien backup en trois fichiers (copie brute, donnée dans le WAL).
    backup_dir = tmp_path / "auto_backups"
    backup_dir.mkdir()
    old_main = backup_dir / "20250101_000000_old_demo.db"
    shutil.copy2(db, old_main)
    for suffix in ("-wal", "-shm"):
        sidecar = db.with_name(db.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, backup_dir / (old_main.name + suffix))
    conn.close()
    # Sidecar orphelin (base principale disparue).
    (backup_dir / "ghost.db-shm").write_bytes(b"")
    assert any(backup_dir.glob("*.db-wal"))

    create_auto_backup(str(db), "test")

    assert not any(backup_dir.glob("*.db-wal"))
    assert not any(backup_dir.glob("*.db-shm"))
    # L'ancien backup absorbé reste lisible, donnée du WAL incluse.
    with sqlite3.connect(str(old_main)) as check:
        assert check.execute("SELECT x FROM t;").fetchone() == (42,)


def test_source_introuvable(tmp_path: Path):
    assert create_auto_backup(str(tmp_path / "nope.db"), "test") is None
