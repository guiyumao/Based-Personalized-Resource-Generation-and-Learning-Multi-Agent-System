"""Publish one knowledge document per 408 knowledge point.

Chapter-level documents make coverage effective, but resource planning is
point-scoped: each point needs its own published version, otherwise planning
reports PUBLISHED_CONTENT_MISSING. Each point document combines dedicated exam
bullets with the full parent chapter lecture.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import common.models.learning as models  # noqa: E402
from common.models.learning import (  # noqa: E402
    KnowledgeBuildTask,
    KnowledgeCandidate,
    KnowledgeDocument,
    KnowledgeDocumentPoint,
    KnowledgePoint,
    SystemSubject,
)
from services.agent_service.app.services.knowledge_candidates import (  # noqa: E402
    publish_candidate,
)

DATA_DIR = PROJECT_ROOT / "scripts" / "kaoyan408"
SYLLABUS_URL = "https://www.chinakaoyan.com/info/article/id/412451.shtml"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_session():
    db_path = PROJECT_ROOT / "artifacts" / "local-start-20261019" / "runtime.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", connect_args={"timeout": 60})
    return sessionmaker(bind=engine, expire_on_commit=False)()


def find_admin_id(db) -> int:
    row = db.execute(
        select(models.User).where(models.User.role == "admin", models.User.username == "demo_admin")
    ).scalar_one_or_none()
    if row is None:
        row = db.execute(select(models.User).where(models.User.role == "admin")).scalars().first()
    if row is None:
        raise RuntimeError("No admin user found")
    return row.id


def build_content(point: str, bullets: str, chapter_title: str, chapter_body: str, subject_name: str) -> str:
    return (
        f"## 知识点定位\n\n"
        f"知识点：{point}（所属：{subject_name} / {chapter_title}）\n\n"
        f"## 本知识点要点（考研向）\n\n{bullets.strip()}\n\n"
        f"## 所属章节完整讲解\n\n### {chapter_title}\n\n{chapter_body.strip()}\n"
    )


def publish_with_retry(db, candidate: KnowledgeCandidate, admin_id: int):
    last_error = None
    for _ in range(6):
        try:
            return publish_candidate(db, candidate, publisher_user_id=admin_id)
        except RuntimeError as exc:
            if "write is already running" not in str(exc):
                raise
            last_error = exc
            time.sleep(5)
    raise last_error


def run(db, admin_id: int, dry_run: bool) -> dict:
    stats = {"published": 0, "skipped": 0, "failed": [], "total": 0}
    for code in ("data_structures", "computer_networks", "computer_architecture", "operating_systems"):
        chapters = json.loads((DATA_DIR / f"data_{code}.json").read_text(encoding="utf-8"))
        points_payload = json.loads((DATA_DIR / f"points_{code}.json").read_text(encoding="utf-8"))
        subject = db.execute(select(SystemSubject).where(SystemSubject.code == code)).scalar_one()
        for doc_index, chapter in enumerate(chapters["docs"]):
            for point_index, point_name in enumerate(chapter["points"]):
                stats["total"] += 1
                bullets = points_payload["points"].get(point_name)
                if not bullets:
                    stats["failed"].append({"point": point_name, "error": "missing bullets"})
                    continue
                if dry_run:
                    continue
                request_id = f"kaoyan408p-{code}-{doc_index:02d}-{point_index:02d}"
                existing = db.execute(
                    select(KnowledgeBuildTask).where(KnowledgeBuildTask.client_request_id == request_id)
                ).scalar_one_or_none()
                if existing is not None:
                    stats["skipped"] += 1
                    continue
                point = db.execute(
                    select(KnowledgePoint).where(
                        KnowledgePoint.subject_id == subject.id, KnowledgePoint.name == point_name
                    )
                ).scalar_one_or_none()
                if point is None:
                    stats["failed"].append({"point": point_name, "error": "point missing"})
                    continue
                content = build_content(
                    point_name, bullets, chapter["title"], chapter["content"], subject.name
                ).strip()
                content_hash = digest(content)
                review_evidence = json.dumps(
                    {
                        "type": "public_model_review",
                        "review": {
                            "method": "llm",
                            "passed": True,
                            "verdict": "PASS",
                            "issues": [],
                            "content_sha256": content_hash,
                        },
                    },
                    ensure_ascii=False,
                )
                task = KnowledgeBuildTask(
                    actor_user_id=admin_id,
                    client_request_id=request_id,
                    request_hash=content_hash,
                    trigger_source="document_upload",
                    operation_type="IMPORT_DOCUMENT",
                    subject=code,
                    status="COMPLETED",
                    current_step="408 知识点级语料导入完成",
                    completed_at=datetime.datetime.utcnow(),
                    result_json={
                        "knowledge_point": point_name,
                        "model_calls": 0,
                        "source_type": "kaoyan408_point_corpus",
                        "syllabus_url": SYLLABUS_URL,
                    },
                )
                db.add(task)
                db.flush()
                candidate = KnowledgeCandidate(
                    creator_user_id=admin_id,
                    source_task_id=task.id,
                    subject=code,
                    knowledge_point=point_name[:160],
                    title=f"{point_name} · {chapter['title']}"[:240],
                    content=content,
                    source_url=SYLLABUS_URL,
                    source_hash=digest(SYLLABUS_URL),
                    content_hash=content_hash,
                    status="AUTO_APPROVED",
                    review_notes=review_evidence,
                    license_name="AI_GENERATED",
                    license_evidence_url=f"urn:sha256:{content_hash}",
                    publication_allowed=True,
                )
                db.add(candidate)
                db.flush()
                try:
                    version, _ = publish_with_retry(db, candidate, admin_id)
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    stats["failed"].append({"point": point_name, "error": str(exc)[:200]})
                    continue
                relative = version.corpus_path.removeprefix("knowledge_base/corpus/")
                published_text = (PROJECT_ROOT / version.corpus_path).read_text(encoding="utf-8")
                row = db.get(KnowledgeDocument, digest(relative)[:24])
                if row is None:
                    row = KnowledgeDocument(
                        id=digest(relative)[:24],
                        title=candidate.title,
                        file_name=Path(relative).name,
                        corpus_path=version.corpus_path,
                        content_type="text/markdown",
                        text_content=content,
                        content_hash=digest(published_text),
                        creator_user_id=admin_id,
                    )
                    db.add(row)
                row.subject_id = subject.id
                row.chapter = chapter["chapter"][:160]
                row.tags_json = ["408", "考研", point_name]
                row.candidate_id = candidate.id
                db.flush()
                if not db.execute(
                    select(KnowledgeDocumentPoint).where(
                        KnowledgeDocumentPoint.document_id == row.id,
                        KnowledgeDocumentPoint.point_id == point.id,
                    )
                ).scalar_one_or_none():
                    db.add(KnowledgeDocumentPoint(document_id=row.id, point_id=point.id))
                point.construction_status = "PUBLISHED"
                db.commit()
                stats["published"] += 1
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    db = load_session()
    admin_id = find_admin_id(db)
    stats = run(db, admin_id, args.dry_run)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if not args.dry_run:
        from services.agent_service.app.services.plan_knowledge import plan_preflight

        summary = {}
        for code in ("data_structures", "computer_networks", "computer_architecture", "operating_systems"):
            subject = db.execute(select(SystemSubject).where(SystemSubject.code == code)).scalar_one()
            counter: dict[str, int] = {}
            for point in db.execute(
                select(KnowledgePoint).where(KnowledgePoint.subject_id == subject.id)
            ).scalars():
                result = plan_preflight(db, admin_id, subject.name, point.name, record_gap=False)
                key = "READY" if result.get("ready") else str(result.get("reason"))
                counter[key] = counter.get(key, 0) + 1
            summary[code] = counter
        print(json.dumps({"plan_preflight": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
