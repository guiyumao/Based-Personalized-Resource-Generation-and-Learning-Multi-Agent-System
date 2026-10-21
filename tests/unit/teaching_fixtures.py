"""Explicit server catalog for report tests that formerly submitted invented IDs.

The untrusted/imported-question behavior is covered independently in
test_teaching_evidence. These report scenarios need confirmed exercises.
"""
import json
import pytest

from common.models.learning import Exercise
from services.evaluation_service.app.services.report_service import ReportService


@pytest.fixture(autouse=True)
def registered_catalog(monkeypatch):
    original = ReportService._prepare_submission

    def prepare(service, payload):
        prepared = original(service, payload)
        with service._session_factory() as db:
            if db.get(Exercise, prepared.exercise_id_int) is None:
                exercise = service._upsert_exercise(db, prepared)
                content = json.loads(exercise.content)
                content["classification_status"] = "confirmed"
                exercise.content = json.dumps(content, ensure_ascii=False)
                db.commit()
        return original(service, payload)

    monkeypatch.setattr(ReportService, "_prepare_submission", prepare)
