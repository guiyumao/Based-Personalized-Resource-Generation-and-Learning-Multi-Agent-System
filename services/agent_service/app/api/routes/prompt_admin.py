"""Administrator prompt-template management (P1-07 管理员专用 Prompt 优化)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from common.dependencies import require_role
from common.models.learning import User
from common.schemas.response import ApiResponse
from services.agent_service.app.services.prompt_registry import (
    list_prompts,
    read_prompt,
    update_prompt,
)

router = APIRouter(prefix="/admin/prompts", tags=["prompt-admin"])


class PromptUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=200_000)


@router.get("", response_model=ApiResponse[list[dict]])
def get_prompt_templates(
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[list[dict]]:
    """List whitelisted prompt templates without their full bodies."""

    return ApiResponse(data=list_prompts(), message="Prompt templates fetched.")


@router.get("/{name}", response_model=ApiResponse[dict])
def get_prompt_template(
    name: str,
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[dict]:
    """Read one prompt template body."""

    try:
        return ApiResponse(data=read_prompt(name), message="Prompt template fetched.")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{name}", response_model=ApiResponse[dict])
def put_prompt_template(
    name: str,
    payload: PromptUpdate,
    _user: User = Depends(require_role("admin")),
) -> ApiResponse[dict]:
    """Replace one prompt template body, preserving its declared placeholders."""

    try:
        return ApiResponse(data=update_prompt(name, payload.content), message="Prompt template updated.")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
