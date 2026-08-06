"""Prove the migrations actually run: upgrade → downgrade → upgrade, checking the schema each time.

`alembic upgrade head` exits 0 whether it created the schema or silently rolled it back (an env.py
that leaves a transaction open does exactly that), so the round trip is only worth running if
something looks at the tables afterwards. Runs against the *test* database, never the dev one.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "api" / "alembic.ini"
CORE_TABLES = {"source", "harbour", "field", "spot", "nav_aid", "issue"}
AVAILABILITY_TABLES = {"observation", "spot_status", "field_status", "feed"}


def tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def main() -> int:
    url = os.environ.get("BALISE_TEST_DATABASE_URL") or os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = url
    from balise_api.config import get_settings

    get_settings.cache_clear()
    sync_url = get_settings().sync_database_url

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))

    command.upgrade(config, "head")
    present = tables(sync_url)
    missing = (CORE_TABLES | AVAILABILITY_TABLES) - present
    if missing:
        print(f"FAILED: upgrade left these tables uncreated: {sorted(missing)}")
        return 1

    command.downgrade(config, "base")
    left = CORE_TABLES & tables(sync_url)
    if left:
        print(f"FAILED: downgrade left these tables behind: {sorted(left)}")
        return 1

    command.upgrade(config, "head")
    if (CORE_TABLES | AVAILABILITY_TABLES) - tables(sync_url):
        print("FAILED: the second upgrade did not rebuild the schema")
        return 1

    print(
        f"round trip OK: {len(CORE_TABLES | AVAILABILITY_TABLES)} tables created, dropped, rebuilt"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
