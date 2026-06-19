"""Create all SQLAlchemy tables directly from metadata."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.db.base import Base
from common.db.session import engine
from common.models import learning  # noqa: F401


def main() -> None:
    """Create all tables for local development or quick bootstrap."""

    Base.metadata.create_all(bind=engine)
    print("All tables created successfully.")


if __name__ == "__main__":
    main()
