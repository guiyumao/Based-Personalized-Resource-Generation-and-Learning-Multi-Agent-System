"""Unit tests for admin-side system manager capabilities."""

from services.system_service.app.schemas.system import RoleAssignment, SubjectCreate
from services.system_service.app.services.system_manager import SystemManager


def test_system_manager_can_create_subject() -> None:
    """Admin should be able to add a new subject."""

    manager = SystemManager()
    created = manager.create_subject(
        SubjectCreate(name="操作系统", description="进程、线程、内存与调度")
    )

    assert created.id >= 1
    assert created.name == "操作系统"
    assert any(item.name == "操作系统" for item in manager.list_subjects())


def test_system_manager_can_update_config() -> None:
    """Admin should be able to update a config entry."""

    manager = SystemManager()
    updated = manager.update_config("qa_response_timeout", "8")

    assert updated.key == "qa_response_timeout"
    assert updated.value == "8"


def test_system_manager_can_filter_logs() -> None:
    """Admin log filtering should return only matching levels."""

    manager = SystemManager()
    # Trigger a WARN-level log entry
    manager.update_config("llm_default_model", "qwen-plus")
    manager.assign_role(RoleAssignment(user_id=3, role="teacher"))

    warn_logs = manager.list_logs("WARN")
    assert warn_logs
    assert all(item.level == "WARN" for item in warn_logs)
