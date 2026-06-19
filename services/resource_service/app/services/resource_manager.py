"""Database-backed resource manager for generated assets and imported courseware."""

from __future__ import annotations

from datetime import datetime
import json
import mimetypes
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from common.models.learning import KnowledgePoint, Resource
from services.resource_service.app.schemas.resource import ExternalResourceImportRequest, ResourceItem


class ResourceManager:
    """Read and manage stored learning resources."""

    _status_overrides: dict[int, str] = {}
    _repo_root = Path(__file__).resolve().parents[4]
    _storage_root = _repo_root / "storage" / "resources"

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_resources(self) -> list[ResourceItem]:
        """Return all managed resources ordered by newest first."""

        rows = (
            self.db.query(Resource, KnowledgePoint)
            .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
            .order_by(Resource.id.desc())
            .all()
        )
        return [self._to_item(resource, knowledge_point) for resource, knowledge_point in rows]

    def get_resource(self, resource_id: int) -> ResourceItem | None:
        """Return one resource by ID."""

        row = (
            self.db.query(Resource, KnowledgePoint)
            .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
            .filter(Resource.id == resource_id)
            .first()
        )
        if row is None:
            return None
        resource, knowledge_point = row
        return self._to_item(resource, knowledge_point)

    def import_external_resource(self, payload: ExternalResourceImportRequest) -> ResourceItem:
        """Download one external courseware asset and persist it as a managed resource."""

        knowledge_point = self._resolve_or_create_knowledge_point(payload.knowledge_point)
        downloaded = self._download_external_asset(payload.url, payload.title)
        metadata = {
            "mode": "external_import",
            "title": payload.title.strip(),
            "provider": payload.provider.strip(),
            "external_url": payload.url.strip(),
            "source_kind": payload.kind.strip(),
            "license": payload.license.strip(),
            "notes": payload.notes.strip(),
            "knowledge_point": knowledge_point.name,
            "local_path": downloaded["relative_path"],
            "file_name": downloaded["file_name"],
            "mime_type": downloaded["mime_type"],
            "format": downloaded["format"],
            "imported_at": datetime.utcnow().isoformat(),
        }
        resource = Resource(
            type="courseware",
            content=json.dumps(metadata, ensure_ascii=False),
            format=downloaded["format"],
            knowledge_point_id=knowledge_point.id,
            generated_for_user_id=payload.owner_user_id,
        )
        self.db.add(resource)
        self.db.commit()
        self.db.refresh(resource)
        return self._to_item(resource, knowledge_point)

    def get_download_info(self, resource_id: int) -> dict[str, str] | None:
        """Return file download metadata for an imported resource."""

        resource = self.db.query(Resource).filter(Resource.id == resource_id).first()
        if resource is None:
            return None

        metadata = self._parse_external_metadata(resource)
        if metadata is None:
            return None

        relative_path = str(metadata.get("local_path") or "").strip()
        if not relative_path:
            return None

        absolute_path = (self._repo_root / relative_path).resolve()
        if not absolute_path.is_file():
            return None

        return {
            "absolute_path": str(absolute_path),
            "file_name": str(metadata.get("file_name") or absolute_path.name),
            "media_type": str(metadata.get("mime_type") or "application/octet-stream"),
        }

    def update_status(self, resource_id: int, status: str) -> ResourceItem | None:
        """Update the lightweight in-service status for a resource."""

        resource = self.db.query(Resource).filter(Resource.id == resource_id).first()
        if resource is None:
            return None

        self._status_overrides[resource_id] = status
        return self.get_resource(resource_id)

    def _to_item(self, resource: Resource, knowledge_point: KnowledgePoint | None) -> ResourceItem:
        metadata = self._parse_external_metadata(resource)
        point_name = knowledge_point.name if knowledge_point is not None else "未关联知识点"
        if metadata is None:
            return ResourceItem(
                id=resource.id,
                title=self._build_generated_title(resource, knowledge_point),
                type=resource.type,  # type: ignore[arg-type]
                format=resource.format,
                status=self._status_overrides.get(resource.id, "ready"),  # type: ignore[arg-type]
                knowledge_point=point_name,
                owner_user_id=resource.generated_for_user_id,
                source_type="generated",
            )

        return ResourceItem(
            id=resource.id,
            title=str(metadata.get("title") or self._build_generated_title(resource, knowledge_point)),
            type="courseware",
            format=str(metadata.get("format") or resource.format or "file"),
            status=self._status_overrides.get(resource.id, "ready"),  # type: ignore[arg-type]
            knowledge_point=str(metadata.get("knowledge_point") or point_name),
            owner_user_id=resource.generated_for_user_id,
            source_type="external_import",
            provider=str(metadata.get("provider") or "") or None,
            source_kind=str(metadata.get("source_kind") or "") or None,
            external_url=str(metadata.get("external_url") or "") or None,
            download_url=f"/resources/{resource.id}/download" if metadata.get("local_path") else None,
            notes=str(metadata.get("notes") or "") or None,
            file_name=str(metadata.get("file_name") or "") or None,
            is_downloadable=bool(metadata.get("local_path")),
        )

    def _build_generated_title(self, resource: Resource, knowledge_point: KnowledgePoint | None) -> str:
        lines = (resource.content or "").strip().splitlines()
        if lines:
            heading = lines[0].strip()
            if heading.startswith("# "):
                return heading[2:].strip()

        point_name = knowledge_point.name if knowledge_point is not None else "学习资源"
        suffix_map = {
            "courseware": "课件",
            "exercise": "练习",
            "notes": "笔记",
            "exam": "试卷",
        }
        return f"{point_name}{suffix_map.get(resource.type, '资源')}"

    def _parse_external_metadata(self, resource: Resource) -> dict[str, Any] | None:
        raw = (resource.content or "").strip()
        if not raw.startswith("{"):
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("mode") != "external_import":
            return None
        return payload

    def _resolve_or_create_knowledge_point(self, knowledge_point: str) -> KnowledgePoint:
        existing = self.db.query(KnowledgePoint).filter(KnowledgePoint.name == knowledge_point).first()
        if existing is not None:
            return existing

        record = KnowledgePoint(
            name=knowledge_point,
            description=f"{knowledge_point} 导入的外部课件资源",
            difficulty=2,
            importance=2,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def _download_external_asset(self, url: str, title: str) -> dict[str, str]:
        self._storage_root.mkdir(parents=True, exist_ok=True)
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            response = client.get(url)
            response.raise_for_status()

        final_url = str(response.url)
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        extension = self._infer_extension(response, final_url, content_type)
        format_name = self._infer_format(extension, content_type)
        file_name = self._build_file_name(response, final_url, title, extension)
        stored_name = f"{datetime.utcnow():%Y%m%d%H%M%S}-{uuid4().hex[:8]}-{file_name}"
        stored_path = self._storage_root / stored_name

        if format_name in {"html", "text"}:
            stored_path.write_text(response.text, encoding="utf-8")
        else:
            stored_path.write_bytes(response.content)

        relative_path = stored_path.relative_to(self._repo_root).as_posix()
        mime_type = content_type or mimetypes.guess_type(stored_path.name)[0] or "application/octet-stream"
        return {
            "relative_path": relative_path,
            "file_name": file_name,
            "mime_type": mime_type,
            "format": format_name,
        }

    def _infer_extension(self, response: httpx.Response, final_url: str, content_type: str) -> str:
        disposition_name = self._extract_content_disposition_name(response.headers.get("content-disposition", ""))
        candidate_names = [disposition_name, Path(unquote(urlparse(final_url).path)).name]
        for candidate in candidate_names:
            if candidate:
                suffix = Path(candidate).suffix.lower()
                if suffix:
                    return suffix

        if "pdf" in content_type:
            return ".pdf"
        if "word" in content_type or "document" in content_type:
            return ".docx"
        if "presentation" in content_type or "powerpoint" in content_type:
            return ".pptx"
        if "zip" in content_type or "compressed" in content_type:
            return ".zip"
        if "html" in content_type:
            return ".html"
        if content_type.startswith("text/"):
            return ".txt"
        return ".bin"

    def _infer_format(self, extension: str, content_type: str) -> str:
        if extension == ".pdf" or "pdf" in content_type:
            return "pdf"
        if extension in {".doc", ".docx"} or "word" in content_type:
            return "word"
        if extension in {".ppt", ".pptx"} or "powerpoint" in content_type or "presentation" in content_type:
            return "ppt"
        if extension in {".zip", ".rar", ".7z", ".tar", ".gz"} or "zip" in content_type or "compressed" in content_type:
            return "archive"
        if extension in {".html", ".htm"} or "html" in content_type:
            return "html"
        if content_type.startswith("text/"):
            return "text"
        return "file"

    def _build_file_name(self, response: httpx.Response, final_url: str, title: str, extension: str) -> str:
        disposition_name = self._extract_content_disposition_name(response.headers.get("content-disposition", ""))
        url_name = Path(unquote(urlparse(final_url).path)).name
        raw_name = disposition_name or url_name or title
        safe_stem = self._slugify(Path(raw_name).stem or title)
        safe_extension = Path(raw_name).suffix or extension
        return f"{safe_stem}{safe_extension.lower()}"

    def _extract_content_disposition_name(self, header: str) -> str:
        if not header:
            return ""

        filename_star_match = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", header, flags=re.IGNORECASE)
        if filename_star_match:
            return unquote(filename_star_match.group(1)).strip().strip('"')

        filename_match = re.search(r'filename\s*=\s*"([^"]+)"', header, flags=re.IGNORECASE)
        if filename_match:
            return filename_match.group(1).strip()

        plain_match = re.search(r"filename\s*=\s*([^;]+)", header, flags=re.IGNORECASE)
        if plain_match:
            return plain_match.group(1).strip().strip('"')
        return ""

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"\s+", "-", value.strip())
        cleaned = re.sub(r"[^A-Za-z0-9\-_\.一-龥]+", "-", normalized)
        return cleaned.strip("-._") or f"resource-{uuid4().hex[:8]}"
