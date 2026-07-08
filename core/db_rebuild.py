"""
Database rebuild helper shared by the CLI script and PyWebView API.
"""
import os
import sqlite3
from datetime import datetime

from core.db import DatabaseManager


def _sidecar_paths(db_path: str) -> list[str]:
    return [db_path, f"{db_path}-wal", f"{db_path}-shm"]


def backup_database(db_path: str, backup_dir: str | None = None) -> str | None:
    if not os.path.exists(db_path):
        return None

    backup_dir = backup_dir or os.path.dirname(db_path)
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"{os.path.basename(db_path)}.{timestamp}.bak")

    source = sqlite3.connect(db_path)
    try:
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()

    return backup_path


def rebuild_database(db_path: str, backup: bool = True, backup_dir: str | None = None) -> dict:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    backup_path = backup_database(db_path, backup_dir) if backup else None

    for path in _sidecar_paths(db_path):
        if os.path.exists(path):
            os.remove(path)

    db_manager = DatabaseManager(db_path)
    try:
        db_manager.initialize()
    finally:
        db_manager.close()

    return {
        "db_path": db_path,
        "backup_path": backup_path,
    }
