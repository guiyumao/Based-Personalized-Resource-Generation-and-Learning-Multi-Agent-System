"""Neo4j connector and commonly used graph queries."""

from __future__ import annotations

import logging
from typing import Any

from common.config import get_settings

logger = logging.getLogger(__name__)


class KnowledgeGraphRepository:
    """Repository encapsulating common Neo4j knowledge graph operations."""

    def __init__(self) -> None:
        settings = get_settings()
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

    def _fallback_visualization_graph(self, knowledge_point: str) -> dict[str, list[dict[str, Any]]]:
        """Return a deterministic fallback graph when Neo4j is unavailable."""

        nodes = [
            {"id": knowledge_point, "label": knowledge_point, "category": "current"},
            {"id": "prerequisite-1", "label": "顺序结构", "category": "prerequisite"},
            {"id": "prerequisite-2", "label": "条件判断", "category": "prerequisite"},
            {"id": "recommended-1", "label": "列表推导式", "category": "recommended"},
        ]
        edges = [
            {"source": knowledge_point, "target": "prerequisite-1", "label": "DEPENDS_ON"},
            {"source": knowledge_point, "target": "prerequisite-2", "label": "DEPENDS_ON"},
            {"source": knowledge_point, "target": "recommended-1", "label": "RECOMMENDS"},
        ]
        return {"nodes": nodes, "edges": edges}

    def _fallback_dependency_paths(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Return deterministic dependency paths when Neo4j is unavailable."""

        return [
            {"path": [knowledge_point, "顺序结构"]},
            {"path": [knowledge_point, "条件判断"]},
        ]

    def _fallback_related_resources(self) -> list[dict[str, Any]]:
        """Return deterministic related resources when Neo4j is unavailable."""

        return [{"name": "示例资源", "type": "courseware", "uri": "/resources/demo"}]

    def _fallback_recommendations(self) -> list[dict[str, Any]]:
        """Return deterministic next-point recommendations when Neo4j is unavailable."""

        return [{"name": "列表推导式", "difficulty": 2, "importance": 5}]

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
