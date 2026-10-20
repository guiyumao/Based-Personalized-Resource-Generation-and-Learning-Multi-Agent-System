"""Tests for backend-enforced learning-path unlocking.

Both compared upstream projects enforced the learning order only in the browser:
their completion endpoints accepted any node and unlocked the next one
positionally, so a learner could skip ahead by calling the API directly.  These
tests pin the backend gate that closes that hole.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from common.config import get_settings
from services.agent_service.app.services.learning_path import (
    LearningPathPrerequisiteError,
    LearningPathService,
)


def _payload(tasks: list[dict]) -> dict:
    return {"stages": [{"stage_id": "s1", "title": "阶段一", "description": "", "tasks": tasks}]}


def _task(task_id: str, *, status: str = "pending", completed: bool = False, **extra) -> dict:
    task = {
        "task_id": task_id,
        "title": f"任务 {task_id}",
        "task_type": "courseware",
        "knowledge_point": "循环结构",
        "objective": "掌握循环",
        "estimated_minutes": 20,
        "difficulty": "foundation",
        "completed": completed,
        "status": status,
    }
    task.update(extra)
    return task


class _FakeQuery:
    def __init__(self, record):
        self._record = record

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._record


class _FakeDb:
    """Minimal Session stand-in that records the persisted path."""

    def __init__(self, payload: dict):
        self.record = SimpleNamespace(id=1, path_data_json=payload, status="active")
        self.committed = False

    def query(self, *args, **kwargs):
        return _FakeQuery(self.record)

    def commit(self):
        self.committed = True

    def refresh(self, record):
        return None


def _service(payload: dict) -> tuple[LearningPathService, _FakeDb]:
    db = _FakeDb(payload)
    class GateOnlyService(LearningPathService):
        # These tests isolate prerequisite policy. Real revision/CAS persistence
        # and stale writers are exercised with SQLite in test_path_adaptation.
        def commit_path_update(self, record, updated):
            record.path_data_json = updated
            self.db.commit()
    return GateOnlyService(db), db


# --------------------------------------------------------------------------
# prerequisite gating
# --------------------------------------------------------------------------


def test_completing_first_task_is_allowed():
    service, db = _service(_payload([_task("t1"), _task("t2")]))
    updated = service.adjust_path(
        SimpleNamespace(user_id=1, task_id="t1", action="complete")
    )
    assert updated is not None
    assert db.committed is True
    assert updated["stages"][0]["tasks"][0]["status"] == "completed"


def test_completing_a_locked_task_is_refused():
    service, _ = _service(_payload([_task("t1"), _task("t2"), _task("t3")]))
    with pytest.raises(LearningPathPrerequisiteError) as excinfo:
        service.adjust_path(SimpleNamespace(user_id=1, task_id="t3", action="complete"))
    assert excinfo.value.blocked_task_ids == ["t1", "t2"]
    assert excinfo.value.error_code == "LEARNING_PATH_PREREQUISITE_UNMET"


def test_a_skipped_prerequisite_does_not_unlock_the_next_task():
    """Otherwise skipping every task in order would bypass the gate entirely."""

    service, _ = _service(
        _payload([_task("t1", status="skipped"), _task("t2")])
    )
    with pytest.raises(LearningPathPrerequisiteError):
        service.adjust_path(SimpleNamespace(user_id=1, task_id="t2", action="complete"))


def test_explicit_depends_on_overrides_positional_order():
    service, _ = _service(
        _payload(
            [
                _task("t1"),
                _task("t2", depends_on=["t1"]),
                _task("t3", depends_on=["t2"]),
            ]
        )
    )
    with pytest.raises(LearningPathPrerequisiteError) as excinfo:
        service.adjust_path(SimpleNamespace(user_id=1, task_id="t3", action="complete"))
    assert excinfo.value.blocked_task_ids == ["t2"]


def test_dependency_on_a_later_task_is_not_stealthily_satisfied():
    """A forward reference must block until that task is genuinely done."""

    service, _ = _service(_payload([_task("t1", depends_on=["t2"]), _task("t2")]))
    with pytest.raises(LearningPathPrerequisiteError) as excinfo:
        service.adjust_path(SimpleNamespace(user_id=1, task_id="t1", action="complete"))
    assert excinfo.value.blocked_task_ids == ["t2"]


def test_unknown_dependency_reference_does_not_deadlock():
    """A broken reference must not lock a learner out forever."""

    service, _ = _service(_payload([_task("t1", depends_on=["ghost"]), _task("t2")]))
    updated = service.adjust_path(SimpleNamespace(user_id=1, task_id="t1", action="complete"))
    assert updated is not None


def test_self_dependency_cannot_permanently_lock_a_task():
    service, _ = _service(_payload([_task("t1", depends_on=["t1"])]))
    updated = service.adjust_path(SimpleNamespace(user_id=1, task_id="t1", action="complete"))
    assert updated is not None


def test_gate_can_be_disabled_by_configuration(monkeypatch):
    from services.agent_service.app.services import learning_path as module

    real_settings = get_settings()
    relaxed = SimpleNamespace(
        **{
            name: getattr(real_settings, name)
            for name in vars(real_settings)
            if name != "learning_path_enforce_prerequisites"
        },
        learning_path_enforce_prerequisites=False,
    )
    monkeypatch.setattr(module, "get_settings", lambda: relaxed)

    service, _ = _service(_payload([_task("t1"), _task("t2")]))
    updated = service.adjust_path(SimpleNamespace(user_id=1, task_id="t2", action="complete"))
    assert updated is not None
    assert updated["stages"][0]["tasks"][1]["status"] == "completed"


def test_skipping_can_be_disabled_by_configuration(monkeypatch):
    from services.agent_service.app.services import learning_path as module

    real_settings = get_settings()
    relaxed = SimpleNamespace(
        **{
            name: getattr(real_settings, name)
            for name in vars(real_settings)
            if name != "learning_path_allow_skip"
        },
        learning_path_allow_skip=False,
    )
    monkeypatch.setattr(module, "get_settings", lambda: relaxed)

    service, _ = _service(_payload([_task("t1"), _task("t2")]))
    with pytest.raises(LearningPathPrerequisiteError):
        service.adjust_path(SimpleNamespace(user_id=1, task_id="t2", action="skip"))


def test_reset_and_skip_are_not_gated():
    service, _ = _service(_payload([_task("t1"), _task("t2")]))
    skipped = service.adjust_path(SimpleNamespace(user_id=1, task_id="t2", action="skip"))
    assert skipped is not None
    assert skipped["stages"][0]["tasks"][1]["status"] == "skipped"


def test_unknown_task_id_returns_none():
    service, _ = _service(_payload([_task("t1")]))
    assert service.adjust_path(SimpleNamespace(user_id=1, task_id="nope", action="complete")) is None


# --------------------------------------------------------------------------
# dependency-integrity report
# --------------------------------------------------------------------------


def test_find_dependency_problems_reports_a_cycle():
    payload = _payload([_task("a", depends_on=["b"]), _task("b", depends_on=["a"])])
    problems = LearningPathService.find_dependency_problems(payload)
    assert any("cycle" in problem for problem in problems)


def test_find_dependency_problems_reports_unknown_reference():
    payload = _payload([_task("a", depends_on=["ghost"])])
    problems = LearningPathService.find_dependency_problems(payload)
    assert any("unknown task ghost" in problem for problem in problems)


def test_find_dependency_problems_is_empty_for_a_clean_path():
    payload = _payload([_task("a"), _task("b", depends_on=["a"])])
    assert LearningPathService.find_dependency_problems(payload) == []


def test_normalize_payload_backfills_depends_on_for_legacy_paths():
    legacy = {"stages": [{"tasks": [{"task_id": "t1", "completed": True}]}]}
    service, _ = _service(legacy)
    normalized = service._normalize_payload(legacy)
    assert normalized["stages"][0]["tasks"][0]["depends_on"] == []
