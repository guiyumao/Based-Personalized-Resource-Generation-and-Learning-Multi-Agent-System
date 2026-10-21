"""Routes for resource generation agent."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from common.config import get_settings
from common.dependencies import get_current_user, require_self_or_admin
from common.models.learning import User
from common.performance import set_trace_context
from common.schemas.agent import (
    CoordinationRequest,
    ResourceGenerationRequest,
    ResourceGenerationResponse,
)
from services.agent_service.app.agents.coordinator import CoordinatorWorkflow

router = APIRouter()


class ChapterRevisionRequest(BaseModel):
    expected_version: str = Field(min_length=64, max_length=64)
    client_request_id: str = Field(min_length=8, max_length=80)


@router.get("/{resource_id}/video")
def read_resource_video(resource_id: int, current_user: User = Depends(get_current_user)):
    from common.db.session import SessionLocal
    from common.models.learning import Resource
    from fastapi.responses import FileResponse
    from services.agent_service.app.services.resource_artifacts import resource_video_path
    with SessionLocal() as db:
        resource = db.get(Resource, resource_id)
        if not resource or resource.generated_for_user_id != current_user.id or resource.publish_status == 'archived':
            raise HTTPException(404, '课件不存在')
        path = resource_video_path(resource)
        if not path.is_file():
            raise HTTPException(404, '当前版本尚无视频，可单独制作')
        return FileResponse(path, media_type='video/webm', headers={'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff'}, content_disposition_type='inline')


@router.post("/{resource_id}/video", status_code=202)
def create_resource_video(resource_id: int, payload: ChapterRevisionRequest, background: BackgroundTasks,
                          current_user: User = Depends(get_current_user)):
    from common.db.session import SessionLocal
    from common.models.learning import ChatSession, Resource
    from common.resource_version import resource_version
    from services.agent_service.app.services.assistant_tasks import AssistantTaskRequestConflict, create_task, execute_task, task_execution_mode, task_to_dict
    with SessionLocal() as db:
        resource = db.get(Resource, resource_id)
        if not resource or resource.generated_for_user_id != current_user.id or resource.publish_status == 'archived':
            raise HTTPException(404, '课件不存在')
        if resource.type != 'courseware' or resource.generation_status != 'generated' or resource_version(resource) != payload.expected_version:
            raise HTTPException(409, '课件尚未完成或版本已改变')
        session = ChatSession(user_id=current_user.id, title='课件字幕视频')
        db.add(session); db.flush()
        try:
            task, created = create_task(db, user_id=current_user.id, session=session,
                client_request_id=payload.client_request_id, action='resource_video', message='制作课件字幕视频',
                knowledge_point='', exercise_count=3, allow_session_reuse=True,
                resource_video={'resource_id': resource_id, 'version': payload.expected_version})
        except AssistantTaskRequestConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        if created and task_execution_mode() == 'background':
            background.add_task(execute_task, task.id)
        return task_to_dict(task)


@router.post("/{resource_id}/chapters/{chapter_key}/regenerate", status_code=202)
def regenerate_chapter(resource_id: int, chapter_key: str, payload: ChapterRevisionRequest,
                       background: BackgroundTasks, current_user: User = Depends(get_current_user)):
    import json

    from common.db.session import SessionLocal
    from common.models.learning import ChatSession, Resource
    from common.resource_version import resource_version
    from services.agent_service.app.services.assistant_tasks import (
        AssistantTaskRequestConflict,
        create_task,
        execute_task,
        task_execution_mode,
        task_to_dict,
    )
    with SessionLocal() as db:
        row = db.get(Resource, resource_id)
        if not row or row.generated_for_user_id != current_user.id or row.publish_status == "archived":
            raise HTTPException(404, "课件不存在")
        if row.type != "courseware" or row.generation_status != "generated":
            raise HTTPException(409, "请等待原课件完成或使用原任务续生成")
        if resource_version(row) != payload.expected_version:
            raise HTTPException(409, "课件版本已改变，请重新打开")
        data = json.loads(row.structured_json or "{}")
        if data.get("schema") != "teaching-v2" or chapter_key not in {c["key"] for c in data.get("chapters", [])}:
            raise HTTPException(422, "没有可重新生成的结构化章节")
        session = ChatSession(user_id=current_user.id, title="课件章节修订", subject=data.get("subject", ""))
        db.add(session)
        db.flush()
        try:
            task, created = create_task(db, user_id=current_user.id, session=session,
                client_request_id=payload.client_request_id, action="courseware_revision", message="重新生成课件章节",
                knowledge_point=data["knowledge_point"], exercise_count=3, allow_session_reuse=True,
                chapter_revision={"resource_id": resource_id, "version": payload.expected_version, "chapter_key": chapter_key})
        except AssistantTaskRequestConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        if created and task_execution_mode() == "background":
            background.add_task(execute_task, task.id)
        return task_to_dict(task)


@router.post("/generate")
def generate_resource(
    payload: ResourceGenerationRequest,
    current_user: User = Depends(get_current_user),
) -> ResourceGenerationResponse:
    """Generate a personalized resource through the multi-agent workflow."""
    require_self_or_admin(payload.user_id, current_user)

    settings = get_settings()
    set_trace_context(
        user_id=payload.user_id,
        task_type="courseware_generation",
        deadline_seconds=settings.courseware_deadline_seconds,
        retry_budget=settings.max_total_retries,
    )
    result = CoordinatorWorkflow().run(
        CoordinationRequest(
            user_id=payload.user_id,
            intent="courseware resource generation",
            knowledge_point=payload.knowledge_point,
            payload={
                **payload.model_dump(),
                "execute": True,
                "force_agents": ["learner_profiling_agent", "resource_generation_agent"],
            },
        )
    )
    output = result.get("outputs", {}).get("resource_generation_agent", {})
    if output.get("status") == "failed":
        raise HTTPException(status_code=503, detail=str(output.get("error") or "Resource generation failed"))
    resource = output.get("resource")
    if not isinstance(resource, dict):
        raise HTTPException(status_code=503, detail="Resource generation agent did not return a resource")
    return ResourceGenerationResponse(**resource)
