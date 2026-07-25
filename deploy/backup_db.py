#!/usr/bin/env python
"""Snapshot the listings database.

Uses sqlite3's online backup API, which is safe to run while the bot is
writing. A plain `cp` of a live SQLite file can capture a torn copy.

Run from cron with the project venv:

    /home/pipi/ticket-bot/.venv/bin/python /home/pipi/ticket-bot/deploy/backup_db.py

Optional first argument overrides the database path. Backups land in
`backups/` next to the database and are pruned after RETENTION_DAYS.
"""

import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

RETENTION_DAYS = 14


def backup(db_path: Path) -> Path:
    if not db_path.exists():
        raise SystemExit(f"No database at {db_path}")

    dest_dir = db_path.parent / "backups"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / f"{db_path.stem}-{date.today().isoformat()}.db"

    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()

    return dest


def prune(db_path: Path) -> int:
    dest_dir = db_path.parent / "backups"
    if not dest_dir.exists():
        return 0

    cutoff = time.time() - RETENTION_DAYS * 86400
    removed = 0
    for old in dest_dir.glob(f"{db_path.stem}-*.db"):
        if old.stat().st_mtime < cutoff:
            old.unlink()
            removed += 1
    return removed


def main():
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1]).resolve()
    else:
        # Default to tickets.db in the project root, one level up from deploy/.
        db_path = Path(__file__).resolve().parent.parent / "tickets.db"

    dest = backup(db_path)
    removed = prune(db_path)
    size_kb = dest.stat().st_size / 1024
    print(f"Backed up {db_path} -> {dest} ({size_kb:.0f} KB), pruned {removed}")


if __name__ == "__main__":
    main()
