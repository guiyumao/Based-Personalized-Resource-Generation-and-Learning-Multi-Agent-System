"""Database-backed resource manager for generated assets and imported courseware."""

from __future__ import annotations

import json
import math
import mimetypes
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

import httpx
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from common.models.learning import KnowledgePoint, Resource, ResourceInteraction, UserProfile
from services.resource_service.app.schemas.resource import (
    ExternalResourceImportRequest,
    ResourceInteractionSummary,
    ResourceItem,
    ResourceRecommendationItem,
)


class ResourceManager:
    """Read and manage stored learning resources."""

    _repo_root = Path(__file__).resolve().parents[4]
    _storage_root = _repo_root / "storage" / "resources"
    _interaction_weights = {"view": 1.0, "open_source": 1.5, "download": 3.0}
    _max_cf_interactions = 20_000

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

    def list_visible_resources(self, user_id: int | None) -> list[ResourceItem]:
        """Public catalog plus resources generated specifically for this user."""
        visibility = Resource.generated_for_user_id.is_(None)
        if user_id is not None:
            visibility = or_(visibility, Resource.generated_for_user_id == user_id)
        rows = (
            self.db.query(Resource, KnowledgePoint)
            .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
            .filter(visibility)
            .order_by(Resource.id.desc())
            .all()
        )
        return [self._to_item(resource, knowledge_point) for resource, knowledge_point in rows]

    def get_resource(self, resource_id: int) -> ResourceItem | None:
        """Return one resource by ID, including its generated payload."""

        row = (
            self.db.query(Resource, KnowledgePoint)
            .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
            .filter(Resource.id == resource_id)
            .first()
        )
        if row is None:
            return None
        resource, knowledge_point = row
        item = self._to_item(resource, knowledge_point)
        item.content = resource.content
        structured_payload = self._parse_structured_payload(resource)
        if structured_payload is not None:
            item.structured = structured_payload.get("structured") or None
            validation = structured_payload.get("content_validation")
            item.content_validation = validation if isinstance(validation, dict) else None
        return item

    @staticmethod
    def _parse_structured_payload(resource: Resource) -> dict[str, Any] | None:
        """Decode the stored structured payload, tolerating bad/absent data.

        A malformed payload must never make a stored resource unreadable: the
        detail endpoint degrades to "no structured view" instead of raising.
        """

        raw = getattr(resource, "structured_json", None)
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def recommend_resources(self, user_id: int, limit: int = 6) -> list[ResourceRecommendationItem]:
        """Rank visible resources from learner interest, ownership, recency, and real usage."""

        rows = (
            self.db.query(Resource, KnowledgePoint)
            .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
            .filter(Resource.publish_status != "archived")
            .filter(or_(Resource.generated_for_user_id.is_(None), Resource.generated_for_user_id == user_id))
            .all()
        )
        if not rows:
            return []

        resource_ids = [resource.id for resource, _ in rows]
        counters = self._interaction_counts(resource_ids)
        interest_weights = self._learner_interest_weights(user_id)
        collaborative_signals = self._collaborative_signals(user_id, resource_ids)
        now = datetime.utcnow()
        ranked: list[tuple[float, ResourceRecommendationItem]] = []

        for resource, knowledge_point in rows:
            is_public = resource.publish_status == "published" and resource.audit_status == "passed"
            is_owned_generated = (
                resource.generated_for_user_id == user_id
                and resource.generation_status == "generated"
                and resource.audit_status != "rejected"
            )
            metadata = self._parse_external_metadata(resource)
            is_valid_legacy_import = metadata is not None and self.get_download_info(resource.id) is not None
            if not (is_public or is_owned_generated or is_valid_legacy_import):
                continue

            item = self._to_item(resource, knowledge_point)
            point_key = self._normalise_interest_key(item.knowledge_point)
            interest_score = interest_weights.get(point_key, 0.0)
            counts = counters.get(resource.id, {"view": 0, "download": 0, "open_source": 0})
            popularity = counts["view"] + counts["open_source"] * 1.5 + counts["download"] * 3
            popularity_score = math.log1p(popularity) * 1.7
            owner_score = 4.0 if resource.generated_for_user_id == user_id else 0.0
            age_days = max((now - resource.created_at).total_seconds() / 86_400, 0) if resource.created_at else 365
            freshness_score = 1.5 / (1 + age_days / 30)
            signals = collaborative_signals.get(
                resource.id,
                {"collaborative": 0.0, "user_cf": 0.0, "item_cf": 0.0},
            )
            collaborative_score = signals["collaborative"]
            user_cf_score = signals["user_cf"]
            item_cf_score = signals["item_cf"]
            has_history = bool(collaborative_signals.get("has_history", False))
            strategy = (
                "hybrid_collaborative"
                if collaborative_score > 0
                else "personalized_heuristic"
                if has_history or interest_score > 0
                else "cold_start_popularity"
            )
            score = (
                interest_score * 4
                + collaborative_score * 5
                + popularity_score
                + owner_score
                + freshness_score
            )

            if resource.generated_for_user_id == user_id:
                reason = "为你的学习画像生成"
            elif user_cf_score >= 0.25 and user_cf_score >= item_cf_score:
                reason = "与你学习行为相似的学习者也关注"
            elif item_cf_score >= 0.25:
                reason = "与你已学习资源相似"
            elif interest_score > 0:
                reason = f"延续你对“{item.knowledge_point}”的学习"
            elif popularity > 0:
                reason = "近期学习者常用"
            else:
                reason = f"补充“{item.knowledge_point}”相关资料"

            ranked.append(
                (
                    score,
                    ResourceRecommendationItem(
                        **item.model_dump(),
                        recommendation_score=round(score, 3),
                        recommendation_reason=reason,
                        recommendation_strategy=strategy,
                        collaborative_score=round(collaborative_score, 4),
                        user_cf_score=round(user_cf_score, 4),
                        item_cf_score=round(item_cf_score, 4),
                        view_count=counts["view"],
                        download_count=counts["download"],
                    ),
                )
            )

        ranked.sort(key=lambda value: (value[0], value[1].id), reverse=True)
        return [item for _, item in ranked[:limit]]

    def record_interaction(self, user_id: int, resource_id: int, action: str) -> ResourceInteractionSummary | None:
        """Store a de-duplicated learner action and return the updated counters."""

        row = (
            self.db.query(Resource, KnowledgePoint)
            .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
            .filter(Resource.id == resource_id)
            .filter(or_(Resource.generated_for_user_id.is_(None), Resource.generated_for_user_id == user_id))
            .first()
        )
        if row is None:
            return None

        resource, knowledge_point = row
        duplicate = (
            self.db.query(ResourceInteraction.id)
            .filter(
                ResourceInteraction.user_id == user_id,
                ResourceInteraction.resource_id == resource_id,
                ResourceInteraction.action == action,
                ResourceInteraction.created_at >= datetime.utcnow() - timedelta(seconds=30),
            )
            .first()
        )
        recorded = duplicate is None
        if recorded:
            self.db.add(
                ResourceInteraction(
                    user_id=user_id,
                    resource_id=resource_id,
                    action=action,
                    knowledge_point=knowledge_point.name if knowledge_point is not None else "",
                )
            )
            self.db.commit()

        counts = self._interaction_counts([resource_id]).get(
            resource_id,
            {"view": 0, "download": 0, "open_source": 0},
        )
        return ResourceInteractionSummary(
            resource_id=resource_id,
            recorded=recorded,
            view_count=counts["view"],
            download_count=counts["download"],
        )

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
            title=payload.title.strip(),
            type="courseware",
            content=json.dumps(metadata, ensure_ascii=False),
            format=downloaded["format"],
            knowledge_point_id=knowledge_point.id,
            generated_for_user_id=payload.owner_user_id,
            generation_status="generated",
            audit_status="passed",
            publish_status="published",
            audit_reason="external_import_download_validated",
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

        publish_status = {"draft": "draft", "ready": "published", "archived": "archived"}[status]
        if publish_status == "published" and resource.audit_status != "passed":
            raise ValueError("Only audit-passed resources can be published")
        resource.publish_status = publish_status
        self.db.commit()
        self.db.refresh(resource)
        return self.get_resource(resource_id)

    def delete_resource(self, resource_id: int) -> bool:
        """Delete one managed resource and its downloaded file when present."""

        resource = self.db.query(Resource).filter(Resource.id == resource_id).first()
        if resource is None:
            return False

        metadata = self._parse_external_metadata(resource)
        if metadata is not None:
            relative_path = str(metadata.get("local_path") or "").strip()
            if relative_path:
                absolute_path = (self._repo_root / relative_path).resolve()
                try:
                    if absolute_path.is_file():
                        absolute_path.unlink()
                except OSError:
                    pass

        self.db.query(ResourceInteraction).filter(ResourceInteraction.resource_id == resource_id).delete()
        self.db.delete(resource)
        self.db.commit()
        return True

    def delete_all_resources(self, source_type: str | None = None) -> int:
        """Delete all managed resources, optionally filtered by source type."""

        rows = self.db.query(Resource).all()
        if not rows:
            return 0

        deleted_count = 0
        for resource in rows:
            metadata = self._parse_external_metadata(resource)
            current_source_type = "external_import" if metadata is not None else "generated"
            if source_type is not None and current_source_type != source_type:
                continue

            if metadata is not None:
                relative_path = str(metadata.get("local_path") or "").strip()
                if relative_path:
                    absolute_path = (self._repo_root / relative_path).resolve()
                    try:
                        if absolute_path.is_file():
                            absolute_path.unlink()
                    except OSError:
                        pass

            self.db.query(ResourceInteraction).filter(ResourceInteraction.resource_id == resource.id).delete()
            self.db.delete(resource)
            deleted_count += 1

        self.db.commit()
        return deleted_count

    def _interaction_counts(self, resource_ids: list[int]) -> dict[int, dict[str, int]]:
        if not resource_ids:
            return {}

        rows = (
            self.db.query(
                ResourceInteraction.resource_id,
                func.sum(case((ResourceInteraction.action == "view", 1), else_=0)),
                func.sum(case((ResourceInteraction.action == "download", 1), else_=0)),
                func.sum(case((ResourceInteraction.action == "open_source", 1), else_=0)),
            )
            .filter(ResourceInteraction.resource_id.in_(resource_ids))
            .group_by(ResourceInteraction.resource_id)
            .all()
        )
        return {
            resource_id: {
                "view": int(view_count or 0),
                "download": int(download_count or 0),
                "open_source": int(open_source_count or 0),
            }
            for resource_id, view_count, download_count, open_source_count in rows
        }

    def _collaborative_signals(
        self,
        user_id: int,
        resource_ids: list[int],
    ) -> dict[int | str, dict[str, float] | bool]:
        """Build implicit-feedback User-CF and Item-CF signals for one learner.

        The project stores views, source opens, and downloads rather than explicit
        ratings.  Those actions are converted into weighted, recency-aware
        preferences.  Cosine similarity with overlap shrinkage keeps one shared
        click from producing an overconfident recommendation.
        """

        if not resource_ids:
            return {}

        rows = (
            self.db.query(
                ResourceInteraction.user_id,
                ResourceInteraction.resource_id,
                ResourceInteraction.action,
                ResourceInteraction.created_at,
            )
            .filter(ResourceInteraction.resource_id.in_(resource_ids))
            .order_by(ResourceInteraction.created_at.desc())
            .limit(self._max_cf_interactions)
            .all()
        )
        if not rows:
            return {"has_history": False}

        user_items: dict[int, dict[int, float]] = defaultdict(dict)
        item_users: dict[int, dict[int, float]] = defaultdict(dict)
        for interaction_user_id, resource_id, action, created_at in rows:
            signal = self._interaction_signal(action, created_at)
            if signal <= 0:
                continue
            user_items[interaction_user_id][resource_id] = min(
                12.0,
                user_items[interaction_user_id].get(resource_id, 0.0) + signal,
            )
            item_users[resource_id][interaction_user_id] = user_items[interaction_user_id][resource_id]

        target_items = user_items.get(user_id, {})
        if not target_items:
            return {"has_history": False}

        user_scores: dict[int, float] = defaultdict(float)
        neighbours: list[tuple[float, int]] = []
        for other_user_id, other_items in user_items.items():
            if other_user_id == user_id:
                continue
            overlap = len(set(target_items).intersection(other_items))
            if overlap == 0:
                continue
            similarity = self._cosine_similarity(target_items, other_items)
            similarity *= overlap / (overlap + 2.0)
            if similarity >= 0.05:
                neighbours.append((similarity, other_user_id))

        for similarity, other_user_id in sorted(neighbours, reverse=True)[:30]:
            for resource_id, signal in user_items[other_user_id].items():
                user_scores[resource_id] += similarity * signal

        item_scores: dict[int, float] = defaultdict(float)
        for seed_resource_id, seed_signal in target_items.items():
            seed_users = item_users.get(seed_resource_id, {})
            for candidate_resource_id in resource_ids:
                if candidate_resource_id == seed_resource_id:
                    continue
                candidate_users = item_users.get(candidate_resource_id, {})
                overlap = len(set(seed_users).intersection(candidate_users))
                if overlap == 0:
                    continue
                similarity = self._cosine_similarity(seed_users, candidate_users)
                similarity *= overlap / (overlap + 2.0)
                if similarity >= 0.05:
                    item_scores[candidate_resource_id] += similarity * seed_signal

        normalized_user_scores = self._normalize_scores(user_scores)
        normalized_item_scores = self._normalize_scores(item_scores)
        output: dict[int | str, dict[str, float] | bool] = {"has_history": True}
        for resource_id in resource_ids:
            user_score = normalized_user_scores.get(resource_id, 0.0)
            item_score = normalized_item_scores.get(resource_id, 0.0)
            output[resource_id] = {
                "user_cf": round(user_score, 6),
                "item_cf": round(item_score, 6),
                "collaborative": round(0.55 * user_score + 0.45 * item_score, 6),
            }
        return output

    def _interaction_signal(self, action: str, created_at: datetime | None) -> float:
        """Convert an implicit action into a bounded recency-aware signal."""

        base_weight = self._interaction_weights.get(action, 0.5)
        if created_at is None:
            return base_weight * 0.5
        try:
            age_days = max((datetime.utcnow() - created_at).total_seconds() / 86_400, 0.0)
        except TypeError:
            age_days = max(
                (datetime.utcnow() - created_at.replace(tzinfo=None)).total_seconds() / 86_400,
                0.0,
            )
        return base_weight / (1.0 + age_days / 90.0)

    def _vector_norm(self, vector: dict[int, float]) -> float:
        return math.sqrt(sum(value * value for value in vector.values()))

    def _cosine_similarity(self, left: dict[int, float], right: dict[int, float]) -> float:
        if not left or not right:
            return 0.0
        smaller, larger = (left, right) if len(left) <= len(right) else (right, left)
        dot = sum(value * larger.get(key, 0.0) for key, value in smaller.items())
        denominator = self._vector_norm(left) * self._vector_norm(right)
        return dot / denominator if denominator else 0.0

    def _normalize_scores(self, scores: dict[int, float]) -> dict[int, float]:
        if not scores:
            return {}
        maximum = max(scores.values())
        if maximum <= 0:
            return {}
        return {resource_id: min(1.0, value / maximum) for resource_id, value in scores.items()}

    def _learner_interest_weights(self, user_id: int) -> dict[str, float]:
        weights: dict[str, float] = {}
        rows = (
            self.db.query(
                ResourceInteraction.knowledge_point,
                ResourceInteraction.action,
                func.count(ResourceInteraction.id),
            )
            .filter(ResourceInteraction.user_id == user_id, ResourceInteraction.knowledge_point != "")
            .group_by(ResourceInteraction.knowledge_point, ResourceInteraction.action)
            .all()
        )
        for knowledge_point, action, count in rows:
            key = self._normalise_interest_key(knowledge_point)
            weights[key] = weights.get(key, 0.0) + self._interaction_weights.get(action, 0.5) * int(count)

        profile = self.db.get(UserProfile, user_id)
        if profile is not None and isinstance(profile.mastery_json, dict):
            for knowledge_point, raw_value in profile.mastery_json.items():
                if not isinstance(raw_value, (int, float)):
                    continue
                mastery = float(raw_value) / 100 if float(raw_value) > 1 else float(raw_value)
                weakness = max(0.0, min(1.0, 1 - mastery))
                key = self._normalise_interest_key(str(knowledge_point))
                weights[key] = weights.get(key, 0.0) + weakness * 2
        return weights

    def _normalise_interest_key(self, value: str) -> str:
        return re.sub(r"\s+", "", value).casefold()

    def _to_item(self, resource: Resource, knowledge_point: KnowledgePoint | None) -> ResourceItem:
        metadata = self._parse_external_metadata(resource)
        point_name = knowledge_point.name if knowledge_point is not None else "未关联知识点"
        if metadata is None:
            status = self._legacy_status(resource)
            return ResourceItem(
                id=resource.id,
                title=self._build_generated_title(resource, knowledge_point),
                type=resource.type,  # type: ignore[arg-type]
                format=resource.format,
                status=status,  # type: ignore[arg-type]
                knowledge_point=point_name,
                owner_user_id=resource.generated_for_user_id,
                source_type="generated",
                generation_status=resource.generation_status,  # type: ignore[arg-type]
                audit_status=resource.audit_status,  # type: ignore[arg-type]
                publish_status=resource.publish_status,  # type: ignore[arg-type]
                audit_reason=resource.audit_reason or "",
            )

        return ResourceItem(
            id=resource.id,
            title=str(metadata.get("title") or self._build_generated_title(resource, knowledge_point)),
            type="courseware",
            format=str(metadata.get("format") or resource.format or "file"),
            status=self._legacy_status(resource),  # type: ignore[arg-type]
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
            generation_status=resource.generation_status,  # type: ignore[arg-type]
            audit_status=resource.audit_status,  # type: ignore[arg-type]
            publish_status=resource.publish_status,  # type: ignore[arg-type]
            audit_reason=resource.audit_reason or "",
        )

    def _legacy_status(self, resource: Resource) -> str:
        if resource.publish_status == "archived":
            return "archived"
        if resource.publish_status == "published" and resource.audit_status == "passed":
            return "ready"
        return "draft"

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
