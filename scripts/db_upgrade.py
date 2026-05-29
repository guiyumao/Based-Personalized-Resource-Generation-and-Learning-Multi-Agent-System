"""Run Alembic upgrade programmatically."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    """Upgrade database schema to the latest Alembic revision."""

    config = Config("alembic.ini")
    command.upgrade(config, "head")
    print("Database upgraded to head.")


if __name__ == "__main__":
    main()
