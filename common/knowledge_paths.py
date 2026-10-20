"""Resolve the existing corpus with an optional isolated runtime root."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = Path(os.getenv("KNOWLEDGE_RUNTIME_ROOT", str(PROJECT_ROOT))).resolve()
CORPUS_DIR = KNOWLEDGE_ROOT / "knowledge_base" / "corpus"
