"""Read-only SQLite schema inventory; never create, stamp or migrate the source."""
import argparse
import json
import sqlite3
from pathlib import Path

from sqlalchemy.engine import make_url

import common.models  # noqa: F401
from common.config import get_settings
from common.db.base import Base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise SystemExit("This inventory supports SQLite only")
    source = Path(url.database).resolve(strict=True)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing_tables = sorted(set(Base.metadata.tables) - tables)
        missing_columns = {}
        for name, table in Base.metadata.tables.items():
            if name not in tables:
                continue
            quoted = name.replace('"', '""')
            columns = {row[1] for row in db.execute(f'PRAGMA table_info("{quoted}")')}
            missing = sorted(set(table.columns.keys()) - columns)
            if missing:
                missing_columns[name] = missing
        versions = [row[0] for row in db.execute("SELECT version_num FROM alembic_version")] if "alembic_version" in tables else []
        result = {"source": str(source), "read_only": True, "alembic_versions": versions,
                  "target_head": "20261020_0031", "missing_tables": missing_tables,
                  "missing_columns": missing_columns, "compatible": not missing_tables and not missing_columns,
                  "source_migrated": False, "business_rows_read": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("read_only", "alembic_versions", "compatible", "source_migrated")}))


if __name__ == "__main__":
    main()
