#!/usr/bin/env python3
"""Incrementally index crawled resources into the configured Chroma collection.

Unchanged documents are skipped using a content/configuration fingerprint, so a
normal run never recomputes every document embedding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import Settings, get_settings
from services.agent_service.app.services.rag import ChromaRetriever
from services.agent_service.app.services.tag_analysis import TagAnalysisService

ROOT_DIR = Path(__file__).resolve().parent.parent
CRAWLED_DIR = ROOT_DIR / "knowledge_base" / "corpus"


def get_md_files(subject: str | None = None) -> list[Path]:
    search_dir = CRAWLED_DIR / subject if subject else CRAWLED_DIR
    if not search_dir.exists():
        return []
    return sorted(search_dir.rglob("*.md"))


def chunk_document(content: str, *, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """Create heading-aware chunks with sentence-safe overlap for Chinese Markdown."""

    size = max(200, chunk_size)
    overlap_size = min(max(0, overlap), size // 3)
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in re.split(r"\n{2,}", normalized) if block.strip()]
    heading_stack: list[str] = []
    units: list[str] = []

    def split_long_block(text: str) -> list[str]:
        if len(text) <= size:
            return [text]
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？；.!?;])\s*|\n+", text)
            if sentence.strip()
        ]
        parts: list[str] = []
        current = ""
        for sentence in sentences or [text]:
            if len(sentence) > size:
                if current:
                    parts.append(current)
                    current = ""
                step = max(1, size - overlap_size)
                for start in range(0, len(sentence), step):
                    part = sentence[start:start + size].strip()
                    if part:
                        parts.append(part)
                    if start + size >= len(sentence):
                        break
                continue
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= size:
                current = candidate
            else:
                parts.append(current)
                current = sentence
        if current:
            parts.append(current)
        return parts

    for block in blocks:
        heading_match = re.match(r"^(#{1,4})\s+(.+)$", block.splitlines()[0])
        if heading_match:
            level = len(heading_match.group(1))
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(f"{'#' * level} {heading_match.group(2).strip()}")
            units.append(block)
            continue

        context = "\n".join(heading_stack[-2:])
        contextual_block = f"{context}\n\n{block}" if context else block
        units.extend(split_long_block(contextual_block))

    chunks: list[str] = []
    current_parts: list[str] = []
    for unit in units:
        candidate = "\n\n".join([*current_parts, unit]).strip()
        if len(candidate) <= size:
            current_parts.append(unit)
            continue

        if current_parts:
            chunks.append("\n\n".join(current_parts).strip())
        overlap_parts: list[str] = []
        overlap_chars = 0
        for previous in reversed(current_parts):
            if overlap_chars >= overlap_size:
                break
            overlap_parts.insert(0, previous)
            overlap_chars += len(previous)
        current_parts = overlap_parts
        while current_parts and len("\n\n".join([*current_parts, unit])) > size:
            current_parts.pop(0)
        current_parts.append(unit)

    if current_parts:
        chunks.append("\n\n".join(current_parts).strip())
    return [chunk for chunk in chunks if chunk]


def _manifest_path(settings: Settings) -> Path:
    if settings.chroma_mode == "persistent":
        return Path(settings.chroma_persist_directory) / "index_manifest.json"
    return ROOT_DIR / ".cache" / f"chroma-index-{settings.chroma_collection_name}.json"


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "documents": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "documents": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), dict):
        return {"schema_version": 1, "documents": {}}
    return payload


def _save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _fingerprint(content: str, settings: Settings) -> tuple[str, str]:
    document_version = hashlib.sha256(content.encode("utf-8")).hexdigest()
    config = {
        "document_version": document_version,
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "chunker_version": settings.rag_chunker_version,
        "embedding_model_version": settings.embedding_model_version,
        "corpus_version": settings.corpus_version,
        "collection_version": settings.chroma_collection_version,
    }
    raw = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return document_version, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_title(content: str, filepath: Path) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return filepath.stem.replace("_", " ")


def _extract_source_metadata(content: str) -> dict[str, str]:
    """Read normalized provenance fields written by the crawler."""

    labels = {
        "文档ID": "document_id",
        "来源": "source_url",
        "来源站点": "source_site",
        "来源类型": "source_type",
        "大学": "university",
        "课程": "course",
        "作者或机构": "author",
        "授权": "license",
        "采集范围": "crawl_scope",
        "语言": "language",
        "爬取时间": "crawl_time",
        "更新时间": "update_time",
        "内容哈希": "content_hash",
    }
    metadata: dict[str, str] = {}
    for line in content.splitlines()[:30]:
        match = re.match(r"^>\s*([^:：]+)[:：]\s*(.*?)\s*$", line)
        if not match:
            continue
        label, value = match.groups()
        if label in labels:
            metadata[labels[label]] = value
        elif label == "学科":
            subject_match = re.match(r"(.+?)\s*\|\s*难度[:：]\s*(.+)", value)
            if subject_match:
                metadata["declared_subject"] = subject_match.group(1).strip()
                metadata["difficulty"] = subject_match.group(2).strip()
    return metadata


def index_file(
    filepath: Path,
    retriever: ChromaRetriever,
    tag_service: TagAnalysisService,
    settings: Settings,
    *,
    dry_run: bool = False,
    defer_upsert: bool = False,
) -> dict[str, Any]:
    content = filepath.read_text(encoding="utf-8")
    title = _extract_title(content, filepath)
    source_metadata = _extract_source_metadata(content)
    relative_path = filepath.relative_to(CRAWLED_DIR).as_posix()
    subject = relative_path.split("/", 1)[0] if "/" in relative_path else filepath.parent.name
    document_version, index_version = _fingerprint(content, settings)
    chunks = chunk_document(
        content,
        chunk_size=settings.rag_chunk_size,
        overlap=settings.rag_chunk_overlap,
    )
    source_id = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:20]
    document_id = source_metadata.get("document_id") or source_id
    ids = [f"{source_id}_{index:04d}" for index in range(len(chunks))]
    if not chunks:
        return {"chunks": 0, "ids": [], "document_version": document_version, "index_version": index_version}

    tags = tag_service.analyze_tags(content, title, subject)
    metadatas: list[dict[str, Any]] = []
    if not dry_run:
        metadatas = [
            {
                "source": relative_path,
                "source_id": source_id,
                "document_id": document_id,
                "source_url": source_metadata.get("source_url", ""),
                "source_site": source_metadata.get("source_site", ""),
                "source_type": source_metadata.get("source_type", ""),
                "university": source_metadata.get("university", ""),
                "course": source_metadata.get("course", title),
                "author": source_metadata.get("author", ""),
                "license": source_metadata.get("license", ""),
                "crawl_scope": source_metadata.get("crawl_scope", ""),
                "language": source_metadata.get("language", ""),
                "crawl_time": source_metadata.get("crawl_time", ""),
                "update_time": source_metadata.get("update_time", ""),
                "content_hash": source_metadata.get("content_hash", document_version),
                "difficulty": source_metadata.get("difficulty", ""),
                "title": title,
                "subject": subject,
                "grade": "",
                "chapter": title,
                "section": "",
                "knowledge_point_id": source_id,
                "knowledge_point_name": title,
                "teacher_scope": "public",
                "version": document_version[:16],
                "document_version": document_version,
                "chunk_version": index_version,
                "embedding_model_version": settings.embedding_model_version,
                "corpus_version": settings.corpus_version,
                "tags": json.dumps(tags, ensure_ascii=False),
                "chunk_index": index,
                "total_chunks": len(chunks),
            }
            for index in range(len(chunks))
        ]
        if not defer_upsert:
            retriever.upsert_documents(ids=ids, documents=chunks, metadatas=metadatas)
    return {
        "chunks": len(chunks),
        "ids": ids,
        "document_version": document_version,
        "index_version": index_version,
        "tags": tags,
        "documents": chunks if defer_upsert else [],
        "metadatas": metadatas if defer_upsert else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally index crawled resources into ChromaDB")
    parser.add_argument("--subject", type=str, help="Index only one subject folder")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing")
    parser.add_argument("--force", action="store_true", help="Re-index matching files even when unchanged")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Maximum chunks per Chroma upsert batch (default: 128)",
    )
    args = parser.parse_args()

    settings = get_settings()
    retriever = ChromaRetriever(settings)
    if not args.dry_run and not retriever.is_available:
        raise SystemExit(
            "Chroma is unavailable; indexing stopped before writing the manifest. "
            "Install chromadb or verify CHROMA_MODE/CHROMA_HOST/CHROMA_PORT."
        )
    tag_service = TagAnalysisService(settings)
    manifest_path = _manifest_path(settings)
    manifest = _load_manifest(manifest_path)
    documents: dict[str, Any] = manifest.setdefault("documents", {})
    files = get_md_files(args.subject)
    print(f"Knowledge base: {json.dumps(retriever.describe(), ensure_ascii=False)}")
    print(f"Found {len(files)} Markdown files; chunk={settings.rag_chunk_size}, overlap={settings.rag_chunk_overlap}")

    indexed_files = skipped_files = total_chunks = 0
    batch_size = max(16, args.batch_size)
    pending_ids: list[str] = []
    pending_documents: list[str] = []
    pending_metadatas: list[dict[str, Any]] = []
    pending_updates: list[tuple[str, dict[str, Any], list[str]]] = []

    def flush_pending() -> None:
        if not pending_ids:
            return
        retriever.upsert_documents(
            ids=pending_ids,
            documents=pending_documents,
            metadatas=pending_metadatas,
        )
        for relative_path, manifest_entry, stale_ids in pending_updates:
            if stale_ids:
                retriever.delete_documents(stale_ids)
            documents[relative_path] = manifest_entry
        print(f"  FLUSH {len(pending_ids)} chunks from {len(pending_updates)} files")
        pending_ids.clear()
        pending_documents.clear()
        pending_metadatas.clear()
        pending_updates.clear()
    seen: set[str] = set()
    for index, filepath in enumerate(files, 1):
        relative_path = filepath.relative_to(CRAWLED_DIR).as_posix()
        seen.add(relative_path)
        content = filepath.read_text(encoding="utf-8")
        document_version, index_version = _fingerprint(content, settings)
        previous = documents.get(relative_path, {})
        if not args.force and previous.get("index_version") == index_version:
            skipped_files += 1
            print(f"[{index}/{len(files)}] SKIP unchanged {relative_path}")
            continue

        result = index_file(
            filepath,
            retriever,
            tag_service,
            settings,
            dry_run=args.dry_run,
            defer_upsert=not args.dry_run,
        )
        old_ids = previous.get("ids", []) if isinstance(previous, dict) else []
        stale_ids = sorted(set(old_ids) - set(result["ids"]))
        print(f"[{index}/{len(files)}] {'PLAN' if args.dry_run else 'INDEX'} {relative_path}: {result['chunks']} chunks")
        total_chunks += int(result["chunks"])
        indexed_files += 1
        if not args.dry_run:
            pending_ids.extend(result["ids"])
            pending_documents.extend(result["documents"])
            pending_metadatas.extend(result["metadatas"])
            pending_updates.append((relative_path, {
                "document_version": document_version,
                "index_version": index_version,
                "ids": result["ids"],
                "updated_at": datetime.now(UTC).isoformat(),
            }, stale_ids))
            if len(pending_ids) >= batch_size:
                flush_pending()

    if not args.dry_run:
        flush_pending()

    if not args.subject:
        removed = sorted(set(documents) - seen)
        for relative_path in removed:
            old_ids = documents[relative_path].get("ids", [])
            if not args.dry_run:
                retriever.delete_documents(old_ids)
                documents.pop(relative_path, None)
            print(f"{'PLAN DELETE' if args.dry_run else 'DELETE'} removed source {relative_path}")

    if not args.dry_run:
        manifest.update({
            "schema_version": 1,
            "collection": settings.chroma_collection_name,
            "collection_version": settings.chroma_collection_version,
            "corpus_version": settings.corpus_version,
            "embedding_model_version": settings.embedding_model_version,
            "chunk_size": settings.rag_chunk_size,
            "chunk_overlap": settings.rag_chunk_overlap,
            "chunker_version": settings.rag_chunker_version,
            "updated_at": datetime.now(UTC).isoformat(),
        })
        _save_manifest(manifest_path, manifest)

    print(
        f"Done. indexed={indexed_files}, skipped={skipped_files}, chunks={total_chunks}, "
        f"manifest={manifest_path}"
    )


if __name__ == "__main__":
    main()
