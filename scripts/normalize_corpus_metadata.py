#!/usr/bin/env python3
"""Backfill standardized provenance headers without re-downloading documents."""

from __future__ import annotations

import re
from collections import defaultdict

from crawl_resources import CRAWLED_DIR, TARGETS, CrawlTarget, _output_path, render_document


def main() -> None:
    updated = skipped = 0
    targets_by_path = defaultdict(list)
    for configured_target in TARGETS:
        targets_by_path[_output_path(configured_target)].append(configured_target)
    for path, candidates in targets_by_path.items():
        if not path.exists():
            skipped += 1
            continue
        content = path.read_text(encoding="utf-8")
        source_match = re.search(r"^>\s*来源:\s*(.+?)\s*$", content, flags=re.MULTILINE)
        source_url = source_match.group(1) if source_match else ""
        target = next((item for item in candidates if item.url == source_url), candidates[0])
        parts = re.split(r"^---\s*$", content, maxsplit=1, flags=re.MULTILINE)
        body = parts[1].strip() if len(parts) == 2 else content
        crawl_match = re.search(r"^>\s*爬取时间:\s*(.+?)\s*$", content, flags=re.MULTILINE)
        update_match = re.search(r"^>\s*更新时间:\s*(.+?)\s*$", content, flags=re.MULTILINE)
        normalized = render_document(
            target,
            body,
            crawled_at=crawl_match.group(1) if crawl_match else None,
            updated_at=update_match.group(1) if update_match else None,
        )
        if normalized == content:
            skipped += 1
            continue
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(normalized, encoding="utf-8")
        temporary.replace(path)
        updated += 1
    for path in CRAWLED_DIR.rglob("*.md"):
        if path in targets_by_path:
            continue
        content = path.read_text(encoding="utf-8")
        if "> 文档ID:" in content:
            continue
        source_match = re.search(r"^>\s*来源:\s*(.+?)\s*$", content, flags=re.MULTILINE)
        if not source_match:
            skipped += 1
            continue
        title_match = re.search(r"^#\s+(.+?)\s*$", content, flags=re.MULTILINE)
        difficulty_match = re.search(r"^>\s*学科:.*?难度:\s*(.+?)\s*$", content, flags=re.MULTILINE)
        tags_match = re.search(r"^>\s*标签:\s*(.+?)\s*$", content, flags=re.MULTILINE)
        parts = re.split(r"^---\s*$", content, maxsplit=1, flags=re.MULTILINE)
        body = parts[1].strip() if len(parts) == 2 else content
        legacy_target = CrawlTarget(
            url=source_match.group(1),
            subject=path.parent.name,
            topic=title_match.group(1) if title_match else path.stem,
            difficulty=difficulty_match.group(1) if difficulty_match else "基础",
            tags=[item.strip() for item in tags_match.group(1).split(",")] if tags_match else [],
        )
        normalized = render_document(legacy_target, body)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(normalized, encoding="utf-8")
        temporary.replace(path)
        updated += 1
    print(f"Metadata normalization complete: updated={updated}, skipped={skipped}")


if __name__ == "__main__":
    main()
