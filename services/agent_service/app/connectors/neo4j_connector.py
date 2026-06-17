"""Neo4j connector and commonly used graph queries."""

from __future__ import annotations

import logging
from typing import Any

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import KnowledgePoint, Resource
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService

logger = logging.getLogger(__name__)


class KnowledgeGraphRepository:
    """Repository encapsulating common Neo4j knowledge graph operations."""

    def __init__(self) -> None:
        settings = get_settings()
        self.knowledge_base = KnowledgeBaseService()
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
            )
        except ImportError:
            self._driver = None

    def close(self) -> None:
        """Close the underlying Neo4j driver."""

        if self._driver is not None:
            self._driver.close()

    def _fallback_graph_seed(self, knowledge_point: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        article = self.knowledge_base.get_article(knowledge_point)
        if article is None:
            matches = self.knowledge_base.search_by_keywords(knowledge_point, top_k=1)
            article = matches[0] if matches else None

        current_label = article.title if article is not None else knowledge_point
        nodes = [{"id": current_label, "label": current_label, "category": "current"}]
        edges: list[dict[str, Any]] = []

        if article is not None:
            for concept in article.concepts[:3]:
                concept_name = concept.split("：", 1)[0].strip("` ").strip()
                if len(concept_name) < 2:
                    continue
                nodes.append({"id": concept_name, "label": concept_name, "category": "prerequisite"})
                edges.append({"source": current_label, "target": concept_name, "label": "RELATED_CONCEPT"})

            for check in article.checks[:2]:
                check_name = check[:24]
                nodes.append({"id": check_name, "label": check_name, "category": "recommended"})
                edges.append({"source": current_label, "target": check_name, "label": "SELF_CHECK"})

        return nodes, edges

    def _fallback_visualization_graph(self, knowledge_point: str) -> dict[str, list[dict[str, Any]]]:
        """Return a deterministic graph shell when Neo4j is unavailable."""

        nodes, edges = self._fallback_graph_seed(knowledge_point)
        return {"nodes": list({node["id"]: node for node in nodes}.values()), "edges": edges}

    def _fallback_dependency_paths(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Return deterministic dependency paths from curated knowledge content."""

        article = self.knowledge_base.get_article(knowledge_point)
        if article is None:
            matches = self.knowledge_base.search_by_keywords(knowledge_point, top_k=1)
            article = matches[0] if matches else None
        if article is None:
            return []

        paths: list[dict[str, Any]] = []
        for concept in article.concepts[:3]:
            concept_name = concept.split("：", 1)[0].strip("` ").strip()
            if len(concept_name) < 2:
                continue
            paths.append({"path": [concept_name, article.title]})
        return paths

    def _fallback_related_resources(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Return related resources from generated resources and curated links."""

        resources: list[dict[str, Any]] = []
        with SessionLocal() as db:
            rows = db.query(Resource, KnowledgePoint).outerjoin(
                KnowledgePoint,
                Resource.knowledge_point_id == KnowledgePoint.id,
            ).filter(
                (KnowledgePoint.name == knowledge_point) if knowledge_point else False
            ).order_by(Resource.id.desc()).limit(5).all()
            for resource, kp in rows:
                title = (resource.content or "").strip().splitlines()
                heading = title[0][2:].strip() if title and title[0].startswith("# ") else f"{kp.name if kp else knowledge_point}资源"
                resources.append(
                    {
                        "name": heading,
                        "type": resource.type,
                        "uri": f"/resources/{resource.id}",
                    }
                )

        article = self.knowledge_base.get_article(knowledge_point)
        if article is not None:
            for item in self.knowledge_base.article_to_dict(article).get("external_resources", [])[:4]:
                if not isinstance(item, dict):
                    continue
                resources.append(
                    {
                        "name": item.get("title") or "参考资源",
                        "type": item.get("kind") or "resource",
                        "uri": item.get("url") or "",
                    }
                )
        return resources

    def _fallback_recommendations(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Return next-point recommendations from checks/applications."""

        article = self.knowledge_base.get_article(knowledge_point)
        if article is None:
            return []
        return [
            {"name": item[:30], "difficulty": 1, "importance": 1}
            for item in (article.applications[:2] + article.checks[:2])
        ]

    def create_knowledge_point(
        self,
        name: str,
        description: str,
        difficulty: int,
        importance: int,
    ) -> dict[str, Any]:
        """Create or update a `KnowledgePoint` node."""

        query = """
        MERGE (kp:KnowledgePoint {name: $name})
        SET kp.description = $description,
            kp.difficulty = $difficulty,
            kp.importance = $importance
        RETURN kp
        """
        if self._driver is None:
            return {
                "name": name,
                "description": description,
                "difficulty": difficulty,
                "importance": importance,
            }
        with self._driver.session() as session:
            record = session.run(
                query,
                name=name,
                description=description,
                difficulty=difficulty,
                importance=importance,
            ).single()
            return dict(record["kp"])

    def find_dependency_path(self, knowledge_point: str, max_depth: int = 3) -> list[dict[str, Any]]:
        """Find prerequisite paths using `DEPENDS_ON` relationships."""

        query = """
        MATCH path = (kp:KnowledgePoint {name: $knowledge_point})-[:DEPENDS_ON*1..$max_depth]->(dep:KnowledgePoint)
        RETURN [node IN nodes(path) | node.name] AS dependency_path
        """
        if self._driver is None:
            return self._fallback_dependency_paths(knowledge_point)
        try:
            with self._driver.session() as session:
                result = session.run(query, knowledge_point=knowledge_point, max_depth=max_depth)
                dependency_paths = [{"path": record["dependency_path"]} for record in result]
                return dependency_paths or self._fallback_dependency_paths(knowledge_point)
        except Exception:
            logger.exception("Knowledge graph dependency query failed, using fallback paths.")
            return self._fallback_dependency_paths(knowledge_point)

    def find_related_resources(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Return resource nodes associated with a knowledge point."""

        query = """
        MATCH (kp:KnowledgePoint {name: $knowledge_point})-[:ASSOCIATED_WITH]-(resource:Resource)
        RETURN resource.name AS name, resource.type AS type, resource.uri AS uri
        """
        if self._driver is None:
            return self._fallback_related_resources()
        try:
            with self._driver.session() as session:
                result = session.run(query, knowledge_point=knowledge_point)
                resources = [record.data() for record in result]
                return resources or self._fallback_related_resources()
        except Exception:
            logger.exception("Knowledge graph resource query failed, using fallback resources.")
            return self._fallback_related_resources()

    def recommend_next_points(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Recommend next knowledge points via `RECOMMENDS` links."""

        query = """
        MATCH (kp:KnowledgePoint {name: $knowledge_point})-[:RECOMMENDS]->(next:KnowledgePoint)
        RETURN next.name AS name, next.difficulty AS difficulty, next.importance AS importance
        ORDER BY next.importance DESC, next.difficulty ASC
        """
        if self._driver is None:
            return self._fallback_recommendations()
        try:
            with self._driver.session() as session:
                result = session.run(query, knowledge_point=knowledge_point)
                recommendations = [record.data() for record in result]
                return recommendations or self._fallback_recommendations()
        except Exception:
            logger.exception("Knowledge graph recommendation query failed, using fallback recommendations.")
            return self._fallback_recommendations()

    def get_visualization_graph(self, knowledge_point: str, max_depth: int = 2) -> dict[str, list[dict[str, Any]]]:
        """Return node-edge graph data for frontend visualization."""

        if self._driver is None:
            return self._fallback_visualization_graph(knowledge_point)

        query = """
        MATCH (kp:KnowledgePoint {name: $knowledge_point})
        OPTIONAL MATCH (kp)-[:DEPENDS_ON*1..$max_depth]->(dep:KnowledgePoint)
        OPTIONAL MATCH (kp)-[:RECOMMENDS]->(next:KnowledgePoint)
        RETURN kp, collect(DISTINCT dep) AS deps, collect(DISTINCT next) AS nexts
        """
        try:
            with self._driver.session() as session:
                record = session.run(query, knowledge_point=knowledge_point, max_depth=max_depth).single()
                if record is None:
                    return self._fallback_visualization_graph(knowledge_point)

                nodes = [{"id": knowledge_point, "label": knowledge_point, "category": "current"}]
                edges: list[dict[str, Any]] = []

                for dep in record["deps"]:
                    if dep is None:
                        continue
                    dep_name = dep.get("name")
                    nodes.append({"id": dep_name, "label": dep_name, "category": "prerequisite"})
                    edges.append({"source": knowledge_point, "target": dep_name, "label": "DEPENDS_ON"})

                for nxt in record["nexts"]:
                    if nxt is None:
                        continue
                    next_name = nxt.get("name")
                    nodes.append({"id": next_name, "label": next_name, "category": "recommended"})
                    edges.append({"source": knowledge_point, "target": next_name, "label": "RECOMMENDS"})

                unique_nodes = list({node["id"]: node for node in nodes}.values())
                return {"nodes": unique_nodes, "edges": edges}
        except Exception:
            logger.exception("Knowledge graph visualization query failed, using fallback graph.")
            return self._fallback_visualization_graph(knowledge_point)
