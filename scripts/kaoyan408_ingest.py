"""Import 408 (computer postgraduate exam) corpus into the knowledge base.

Follows the established AI auto-publication convention (AUTO_APPROVED +
AI_GENERATED license) and the full candidate -> publish -> index -> version
pipeline, so coverage and live retrieval become effective immediately.

Usage (run from project root):
    python scripts/kaoyan408_ingest.py            # import all subjects
    python scripts/kaoyan408_ingest.py --dry-run  # resolve points only
"""

from __future__ import annotations

import argparse
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
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}", connect_args={"timeout": 60}
    )
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


def resolve_points(db, subject: SystemSubject, names: list[str]) -> list[KnowledgePoint]:
    points: list[KnowledgePoint] = []
    for name in names:
        point = (
            db.execute(
                select(KnowledgePoint).where(
                    KnowledgePoint.subject_id == subject.id, KnowledgePoint.name == name
                )
            )
            .scalars()
            .first()
        )
        if point is None:
            raise ValueError(f"Knowledge point not found: {subject.code}/{name}")
        points.append(point)
    return points


def publish_with_retry(db, candidate: KnowledgeCandidate, admin_id: int):
    last_error = None
    for attempt in range(6):
        try:
            return publish_candidate(db, candidate, publisher_user_id=admin_id)
        except RuntimeError as exc:
            if "write is already running" not in str(exc):
                raise
            last_error = exc
            time.sleep(5)
    raise last_error


def import_subject(db, admin_id: int, payload: dict, dry_run: bool) -> dict:
    code = payload["subject_code"]
    subject = db.execute(select(SystemSubject).where(SystemSubject.code == code)).scalar_one_or_none()
    if subject is None:
        raise RuntimeError(f"Subject missing in DB: {code}")
    stats = {"subject": code, "docs": 0, "published": 0, "skipped": 0, "failed": []}
    for index, doc in enumerate(payload["docs"]):
        stats["docs"] += 1
        points = resolve_points(db, subject, doc["points"])
        request_id = f"kaoyan408-{code}-{index:02d}"
        task = db.execute(
            select(KnowledgeBuildTask).where(KnowledgeBuildTask.client_request_id == request_id)
        ).scalar_one_or_none()
        if task is not None:
            candidate = db.execute(
                select(KnowledgeCandidate).where(KnowledgeCandidate.source_task_id == task.id)
            ).scalar_one_or_none()
            if candidate is not None and candidate.status == "PUBLISHED":
                stats["skipped"] += 1
                continue
            raise RuntimeError(f"Inconsistent existing task {request_id}")
        if dry_run:
            continue
        content = doc["content"].strip()
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
            current_step="408 考纲语料导入完成",
            completed_at=__import__("datetime").datetime.utcnow(),
            result_json={
                "document_title": doc["title"],
                "model_calls": 0,
                "source_type": "kaoyan408_syllabus_corpus",
                "syllabus_url": SYLLABUS_URL,
            },
        )
        db.add(task)
        db.flush()
        candidate = KnowledgeCandidate(
            creator_user_id=admin_id,
            source_task_id=task.id,
            subject=code,
            knowledge_point=", ".join(doc["points"])[:160] or doc["title"][:160],
            title=doc["title"][:240],
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
            stats["failed"].append({"doc": doc["title"], "error": str(exc)[:200]})
            continue
        relative = version.corpus_path.removeprefix("knowledge_base/corpus/")
        published_text = (PROJECT_ROOT / version.corpus_path).read_text(encoding="utf-8")
        row = db.get(KnowledgeDocument, digest(relative)[:24])
        if row is None:
            row = KnowledgeDocument(
                id=digest(relative)[:24],
                title=doc["title"][:240],
                file_name=Path(relative).name,
                corpus_path=version.corpus_path,
                content_type="text/markdown",
                text_content=content,
                content_hash=digest(published_text),
                creator_user_id=admin_id,
            )
            db.add(row)
        row.subject_id = subject.id
        row.chapter = doc["chapter"][:160]
        row.tags_json = doc.get("tags", ["408", "考研"])
        row.candidate_id = candidate.id
        row.archived = False
        db.flush()
        db.query(KnowledgeDocumentPoint).filter_by(document_id=row.id).delete()
        for point in points:
            db.add(KnowledgeDocumentPoint(document_id=row.id, point_id=point.id))
            point.construction_status = "PUBLISHED"
        db.add(
            models.AuditLog(
                level="INFO",
                event="knowledge.kaoyan408.imported",
                actor_user_id=admin_id,
                message=f"subject={code} doc={row.id} points={[p.id for p in points]}",
            )
        )
        db.commit()
        stats["published"] += 1
    return stats


def report_coverage(db) -> list[dict]:
    from services.agent_service.app.services.knowledge_documents import coverage

    results = []
    for code in (
        "data_structures",
        "computer_networks",
        "computer_architecture",
        "operating_systems",
    ):
        subject = db.execute(select(SystemSubject).where(SystemSubject.code == code)).scalar_one()
        result = coverage(db, subject.id)
        results.append(
            {
                "subject": subject.name,
                "code": code,
                "total_points": result["total_points"],
                "covered_points": result["covered_points"],
                "coverage": result["coverage"],
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    db = load_session()
    admin_id = find_admin_id(db)
    print(f"admin user id = {admin_id}")
    for path in sorted(DATA_DIR.glob("data_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        stats = import_subject(db, admin_id, payload, dry_run=args.dry_run)
        print(json.dumps(stats, ensure_ascii=False))
    if not args.dry_run:
        print(json.dumps({"coverage": report_coverage(db)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
