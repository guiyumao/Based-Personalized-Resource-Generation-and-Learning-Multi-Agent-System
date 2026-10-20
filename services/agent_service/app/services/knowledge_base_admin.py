"""Operational helpers for the crawled knowledge corpus and Chroma index."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from common.config import get_settings
from common.knowledge_lock import knowledge_write_lock
from common.knowledge_paths import KNOWLEDGE_ROOT
from scripts.crawl_resources import CRAWLED_DIR, TARGETS, _output_path, crawl_page
from services.agent_service.app.services.rag import ChromaRetriever

ROOT_DIR = Path(__file__).resolve().parents[4]

_SUBJECT_LABELS = {
    "algorithms": "算法",
    "artificial_intelligence": "人工智能",
    "c_lang": "C语言",
    "compilers": "编译原理",
    "computer_architecture": "计算机组成原理",
    "computer_networks": "计算机网络",
    "computer_science": "计算机科学",
    "cpp": "C++",
    "data_structures": "数据结构",
    "databases": "数据库",
    "deep_learning": "深度学习",
    "developer_tools": "开发工具",
    "discrete_math": "离散数学",
    "distributed_systems": "分布式系统",
    "java": "Java",
    "linear_algebra": "线性代数",
    "machine_learning": "机器学习",
    "math": "数学基础",
    "operating_systems": "操作系统",
    "probability": "概率论",
    "python": "Python",
    "software_eng": "软件工程",
    "web_development": "Web开发",
}


def list_knowledge_subject_catalog() -> list[dict[str, Any]]:
    """List every subject that currently has documents in the knowledge corpus."""

    if not CRAWLED_DIR.exists():
        return []
    counts = Counter(path.parent.name for path in CRAWLED_DIR.rglob("*.md"))
    return [
        {
            "value": subject,
            "label": _SUBJECT_LABELS.get(subject, subject.replace("_", " ").title()),
            "resource_count": counts[subject],
        }
        for subject in sorted(counts)
    ]


def _read_manifest() -> dict[str, Any]:
    settings = get_settings()
    from scripts.index_resources import _manifest_path
    path = _manifest_path(settings)
    if not path.is_absolute():
        path = ROOT_DIR / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def knowledge_base_status() -> dict[str, Any]:
    """Return corpus, provenance and live vector-index statistics."""

    files = list(CRAWLED_DIR.rglob("*.md")) if CRAWLED_DIR.exists() else []
    subject_counts = Counter(path.parent.name for path in files)
    total_chars = 0
    for path in files:
        try:
            total_chars += len(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    manifest = _read_manifest()
    retriever = ChromaRetriever()
    chunk_count = 0
    if retriever.collection is not None:
        try:
            chunk_count = int(retriever.collection.count())
        except Exception:
            chunk_count = 0
    indexed_documents = manifest.get("documents")
    return {
        "available": retriever.is_available,
        "configuration": retriever.describe(),
        "corpus": {
            "documents": len(files),
            "characters": total_chars,
            "subjects": dict(sorted(subject_counts.items())),
        },
        "index": {
            "documents": len(indexed_documents) if isinstance(indexed_documents, dict) else 0,
            "chunks": chunk_count,
            "chunker_version": manifest.get("chunker_version", ""),
            "updated_at": manifest.get("updated_at", ""),
        },
        "sources": {
            "configured": len(TARGETS),
            "universities": sorted({target.university for target in TARGETS if target.university}),
        },
        "checked_at": datetime.now(UTC).isoformat(),
    }


def list_knowledge_sources() -> list[dict[str, Any]]:
    """List the allow-listed sources and their local crawl state."""

    sources: list[dict[str, Any]] = []
    for target in TARGETS:
        output_path = _output_path(target)
        exists = output_path.exists()
        sources.append({
            "id": hashlib.sha256(target.url.encode("utf-8")).hexdigest()[:16],
            "url": target.url,
            "subject": target.subject,
            "topic": target.topic,
            "difficulty": target.difficulty,
            "tags": target.tags,
            "university": target.university,
            "course": target.course,
            "author": target.author,
            "license": target.license,
            "language": target.language,
            "source_type": target.source_type,
            "crawl_scope": target.crawl_scope,
            "status": "available" if exists else "not_crawled",
            "local_path": output_path.relative_to(KNOWLEDGE_ROOT).as_posix() if exists else "",
            "size_bytes": output_path.stat().st_size if exists else 0,
            "modified_at": (
                datetime.fromtimestamp(output_path.stat().st_mtime, UTC).isoformat()
                if exists else ""
            ),
        })
    return sources


def _run_index_command(*, subject: str | None, force: bool, lock_token: str) -> dict[str, Any]:
    if get_settings().chroma_mode == "persistent":
        # A subprocess writer with an already-open embedded Chroma client can
        # leave its parent's HNSW handles stale. Reuse the API's client instead.
        from scripts.index_resources import _main
        started = time.perf_counter()
        arguments = ["--batch-size", "128"]
        if subject:
            arguments.extend(["--subject", subject])
        if force:
            arguments.append("--force")
        _main(arguments)
        return {"elapsed_seconds": round(time.perf_counter() - started, 3), "output": ["Embedded index updated in the current process"], "status": knowledge_base_status()}
    command = [sys.executable, str(ROOT_DIR / "scripts" / "index_resources.py"), "--batch-size", "128"]
    if subject:
        command.extend(["--subject", subject])
    if force:
        command.append("--force")
    started = time.perf_counter()
    environment = dict(__import__("os").environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["KNOWLEDGE_WRITE_LOCK_TOKEN"] = lock_token
    process = subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
        env=environment,
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout or "index command failed")[-2000:]
        raise RuntimeError(detail)
    return {
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "output": process.stdout.strip().splitlines()[-8:],
        "status": knowledge_base_status(),
    }


def reindex_knowledge_base(*, subject: str | None = None, force: bool = False) -> dict[str, Any]:
    """Run the existing deterministic indexer under a single-operation lock."""

    with knowledge_write_lock(KNOWLEDGE_ROOT) as token:
        return _run_index_command(subject=subject, force=force, lock_token=token)


def publish_document_and_reindex(*, target: Path, content: str, subject: str, lock_token: str = "", retire_paths: list[Path] | None = None, verify: Callable[[], None] | None = None) -> dict[str, Any]:
    """Atomically expose one reviewed document and index it under the shared lock."""

    try:
        target.resolve().relative_to(CRAWLED_DIR.resolve())
    except ValueError as exc:
        raise ValueError("Publication path must stay inside the knowledge corpus") from exc
    with knowledge_write_lock(KNOWLEDGE_ROOT, inherited_token=lock_token) as token:
        retired = []
        for old in retire_paths or []:
            old.resolve().relative_to(CRAWLED_DIR.resolve())
            if old != target and old.exists():
                old.replace(old.with_suffix(".archived"))
                retired.append(old)
        target.parent.mkdir(parents=True, exist_ok=True)
        target_existed = target.exists()
        if not target.exists():
            temporary = target.with_suffix(".pending")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(target)
        try:
            result = _run_index_command(subject=subject, force=False, lock_token=token)
            from services.agent_service.app.services.rag import clear_retrieval_runtime_caches
            clear_retrieval_runtime_caches()
            if verify:
                verify()
            return result
        except Exception:
            if not target_existed and target.exists():
                target.replace(target.with_suffix(".pending"))
            for old in retired:
                old.with_suffix(".archived").replace(old)
            # Repair any partially committed vector writes before releasing.
            _run_index_command(subject=subject, force=False, lock_token=token)
            clear_retrieval_runtime_caches()
            raise


def crawl_knowledge_sources(
    *,
    subjects: list[str],
    topics: list[str],
    skip_existing: bool,
    reindex: bool,
) -> dict[str, Any]:
    """Crawl only allow-listed sources, then optionally update the index."""

    with knowledge_write_lock(KNOWLEDGE_ROOT) as token:
        selected = [
            target
            for target in TARGETS
            if (not subjects or target.subject in subjects)
            and (not topics or target.topic in topics)
        ]
        if not selected:
            raise ValueError("No configured knowledge source matched the requested selection")
        if len(selected) > 30:
            raise ValueError("One API crawl request may include at most 30 configured sources")
        results: list[dict[str, str]] = []
        changed_subjects: set[str] = set()
        for index, target in enumerate(selected):
            path = crawl_page(target, skip_existing=skip_existing)
            state = "succeeded" if path else "failed_or_disallowed"
            results.append({"topic": target.topic, "subject": target.subject, "status": state})
            if path:
                changed_subjects.add(target.subject)
            if index + 1 < len(selected):
                time.sleep(1.5)
        index_result: dict[str, Any] | None = None
        if reindex and changed_subjects:
            only_subject = next(iter(changed_subjects)) if len(changed_subjects) == 1 else None
            index_result = _run_index_command(subject=only_subject, force=False, lock_token=token)
        return {
            "selected": len(selected),
            "succeeded": sum(item["status"] == "succeeded" for item in results),
            "failed_or_disallowed": sum(item["status"] != "succeeded" for item in results),
            "results": results,
            "index": index_result,
        }
