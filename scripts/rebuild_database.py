"""
Rebuild the application SQLite database from scripts/init_db.sql.

Examples:
    python scripts/rebuild_database.py --backup
    python scripts/rebuild_database.py --db-path data/wallet.db --yes
"""
import argparse
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.db_rebuild import rebuild_database


def parse_args():
    parser = argparse.ArgumentParser(description="Rebuild AllWalletManager4 database.")
    parser.add_argument(
        "--db-path",
        default=os.path.join(ROOT_DIR, "data", "wallet.db"),
        help="SQLite database path. Defaults to data/wallet.db.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a SQLite backup before rebuilding.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = os.path.abspath(args.db_path)

    if not args.yes:
        print(f"This will delete and rebuild: {db_path}")
        print("Type RESET to continue.")
        if input("> ").strip() != "RESET":
            print("Canceled.")
            return 1

    result = rebuild_database(db_path, backup=args.backup)
    print(f"Database rebuilt: {result['db_path']}")
    if result.get("backup_path"):
        print(f"Backup created: {result['backup_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
