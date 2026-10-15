"""Bootstrap script to create database tables and initialize chat sessions."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from common.db.base import Base
from common.db.session import engine

print("Creating database tables...")
Base.metadata.create_all(bind=engine)
print("Database tables created successfully!")
print("\nCreated tables:")
for table in Base.metadata.sorted_tables:
    print(f"  - {table.name}")
