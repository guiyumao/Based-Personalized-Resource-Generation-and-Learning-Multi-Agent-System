#!/usr/bin/env python3
"""Index crawled resources into ChromaDB for RAG retrieval.

Usage:
    python scripts/index_resources.py                    # index all crawled content
    python scripts/index_resources.py --subject python   # index one subject only
    python scripts/index_resources.py --dry-run          # show what would be indexed
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import get_settings
from services.agent_service.app.services.rag import ChromaRetriever
from services.agent_service.app.services.tag_analysis import TagAnalysisService

ROOT_DIR = Path(__file__).resolve().parent.parent
CRAWLED_DIR = ROOT_DIR / "crawled_content"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def get_md_files(subject: str | None = None) -> list[Path]:
    """Get all Markdown files from the crawled content directory."""
    search_dir = CRAWLED_DIR / subject if subject else CRAWLED_DIR
    if not search_dir.exists():
        return []
    files = list(search_dir.rglob("*.md"))
    files.sort()
    return files


def chunk_document(content: str) -> list[str]:
    """Split a document into overlapping chunks using paragraph boundaries."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) < CHUNK_SIZE:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks


def index_file(filepath: Path, retriever: ChromaRetriever, tag_service: TagAnalysisService, dry_run: bool = False) -> int:
    """Index one crawled Markdown file into ChromaDB. Returns number of chunks indexed."""
    content = filepath.read_text(encoding="utf-8")

    # Extract title from first # heading
    title = filepath.stem.replace("_", " ")
    for line in content.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # Generate tags
    subject = filepath.parent.name
    tags = tag_service.analyze_tags(content, title, subject)

    # Chunk
    chunks = chunk_document(content)
    if not chunks:
        print(f"    No chunks generated")
        return 0

    if dry_run:
        print(f"    Would index {len(chunks)} chunks, tags={tags}")
        return len(chunks)

    # Build IDs and metadatas
    base_id = filepath.stem[:30]
    ids = [f"{base_id}_{i:03d}" for i in range(len(chunks))]
    metadatas = [
        {
            "source": str(filepath.relative_to(CRAWLED_DIR)),
            "title": title,
            "subject": subject,
            "tags": json.dumps(tags, ensure_ascii=False),
            "chunk_index": i,
            "total_chunks": len(chunks),
        }
        for i in range(len(chunks))
    ]

    try:
        retriever.upsert_documents(ids=ids, documents=chunks, metadatas=metadatas)
        return len(chunks)
    except Exception as exc:
        print(f"    ERROR upserting: {exc}")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Index crawled resources into ChromaDB")
    parser.add_argument("--subject", type=str, help="Index only one subject folder")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be indexed")
    args = parser.parse_args()

    settings = get_settings()
    retriever = ChromaRetriever(settings)
    tag_service = TagAnalysisService(settings)

    files = get_md_files(args.subject)
    print(f"Found {len(files)} Markdown files to index")

    total_chunks = 0
    indexed_files = 0
    for i, filepath in enumerate(files, 1):
        rel = filepath.relative_to(CRAWLED_DIR)
        print(f"[{i}/{len(files)}] {rel}")
        chunks = index_file(filepath, retriever, tag_service, dry_run=args.dry_run)
        if chunks > 0:
            total_chunks += chunks
            indexed_files += 1

    print(f"\nDone. Indexed {indexed_files}/{len(files)} files → {total_chunks} chunks in ChromaDB")
    print(f"ChromaDB path: {settings.chroma_persist_directory}")


if __name__ == "__main__":
    main()
