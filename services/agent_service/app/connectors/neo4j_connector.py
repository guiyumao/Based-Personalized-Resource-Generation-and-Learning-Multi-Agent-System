"""Neo4j connector and commonly used graph queries."""

from __future__ import annotations

import logging
import re
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
        self._driver = None
        if not settings.neo4j_enabled:
            logger.info("Neo4j disabled; using knowledge graph fallback.")
            return
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
            )
        except Exception:
            logger.warning("Neo4j driver unavailable; using knowledge graph fallback.")

    def close(self) -> None:
        """Close the underlying Neo4j driver."""

        if self._driver is not None:
            self._driver.close()

    def _fallback_graph_seed(self, knowledge_point: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        article = self.knowledge_base.get_article(knowledge_point)
        if article is None:
            matches = self.knowledge_base.search_by_keywords(knowledge_point, top_k=1)
            article = matches[0] if matches else None
        if article is None:
            blueprint = self._fallback_topic_blueprint(knowledge_point)
            if blueprint is not None:
                return blueprint["nodes"], blueprint["edges"]

        current_label = article.title if article is not None else knowledge_point
        nodes = [{"id": current_label, "label": current_label, "category": "current"}]
        edges: list[dict[str, Any]] = []

        if article is not None:
            for prerequisite in self._fallback_prerequisites(article.title):
                nodes.append({"id": prerequisite, "label": prerequisite, "category": "prerequisite"})
                edges.append({"source": current_label, "target": prerequisite, "label": "DEPENDS_ON"})

            for concept in article.concepts[:3]:
                concept_name = concept.split("：", 1)[0].strip("` ").strip()
                if len(concept_name) < 2:
                    continue
                if any(node["id"] == concept_name for node in nodes):
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
        return self._merge_with_topic_blueprint(
            knowledge_point,
            {"nodes": list({node["id"]: node for node in nodes}.values()), "edges": edges},
        )

    def _merge_with_topic_blueprint(
        self,
        knowledge_point: str,
        graph: dict[str, list[dict[str, Any]]],
        min_nodes: int = 8,
        min_edges: int = 6,
    ) -> dict[str, list[dict[str, Any]]]:
        """Enrich sparse broad-topic graphs with curated course structure."""

        blueprint = self._fallback_topic_blueprint(knowledge_point)
        if blueprint is None:
            return graph

        if len(graph.get("nodes", [])) >= min_nodes and len(graph.get("edges", [])) >= min_edges:
            return graph

        nodes_by_id: dict[str, dict[str, Any]] = {}
        for node in blueprint["nodes"] + graph.get("nodes", []):
            node_id = node.get("id")
            if node_id:
                nodes_by_id[str(node_id)] = node

        seen_edges: set[tuple[str, str, str]] = set()
        merged_edges: list[dict[str, Any]] = []
        for edge in blueprint["edges"] + graph.get("edges", []):
            source = edge.get("source")
            target = edge.get("target")
            label = edge.get("label", "")
            if not source or not target:
                continue
            signature = (str(source), str(target), str(label))
            if signature in seen_edges:
                continue
            seen_edges.add(signature)
            merged_edges.append(edge)

        return {"nodes": list(nodes_by_id.values()), "edges": merged_edges}

    def _fallback_dependency_paths(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Return deterministic dependency paths from curated knowledge content."""

        article = self.knowledge_base.get_article(knowledge_point)
        if article is None:
            matches = self.knowledge_base.search_by_keywords(knowledge_point, top_k=1)
            article = matches[0] if matches else None
        if article is None:
            blueprint = self._fallback_topic_blueprint(knowledge_point)
            if blueprint is None:
                return []
            return blueprint["dependencies"]

        paths: list[dict[str, Any]] = []
        for prerequisite in self._fallback_prerequisites(article.title):
            paths.append({"path": [prerequisite, article.title]})

        for concept in article.concepts[:3]:
            concept_name = concept.split("：", 1)[0].strip("` ").strip()
            if len(concept_name) < 2:
                continue
            if any(item["path"][0] == concept_name for item in paths):
                continue
            paths.append({"path": [concept_name, article.title]})
        return paths

    def _fallback_topic_blueprint(self, knowledge_point: str) -> dict[str, list[dict[str, Any]]] | None:
        """Return a richer course-level graph for broad topics."""

        normalized = re.sub(r"\s+", "", knowledge_point.lower())
        aliases = {
            "高数",
            "高等数学",
            "大学数学",
            "微积分",
            "calculus",
            "advancedmath",
            "highermath",
        }
        if normalized not in aliases:
            return None

        current_id = knowledge_point.strip() or "高等数学"
        nodes: list[dict[str, Any]] = [
            {"id": current_id, "label": current_id, "category": "current"},
        ]
        edges: list[dict[str, Any]] = []

        prerequisites = ["函数与图像", "三角函数", "数列与极限直觉", "解析几何"]
        core_modules = ["极限与连续", "导数与微分", "微分中值定理", "不定积分", "定积分及应用", "无穷级数"]
        advanced_modules = ["多元函数微分", "重积分", "微分方程", "线性代数衔接", "概率统计衔接"]
        resource_nodes = ["微积分公式与例题", "典型错题复盘", "综合应用训练"]

        for item in prerequisites:
            nodes.append({"id": item, "label": item, "category": "prerequisite"})
            edges.append({"source": current_id, "target": item, "label": "前置基础"})

        previous = current_id
        for item in core_modules:
            nodes.append({"id": item, "label": item, "category": "recommended"})
            edges.append({"source": previous, "target": item, "label": "核心顺序"})
            previous = item

        for item in advanced_modules:
            nodes.append({"id": item, "label": item, "category": "recommended"})
            edges.append({"source": "定积分及应用", "target": item, "label": "进阶拓展"})

        for item in resource_nodes:
            nodes.append({"id": item, "label": item, "category": "resource"})
            edges.append({"source": current_id, "target": item, "label": "学习资源"})

        dependencies = [
            {"path": ["函数与图像", "极限与连续", "导数与微分"]},
            {"path": ["三角函数", "极限与连续", "微分中值定理"]},
            {"path": ["导数与微分", "不定积分", "定积分及应用"]},
            {"path": ["定积分及应用", "多元函数微分", "重积分"]},
            {"path": ["导数与微分", "微分方程"]},
            {"path": ["无穷级数", "概率统计衔接"]},
        ]
        return {"nodes": nodes, "edges": edges, "dependencies": dependencies}

    def _fallback_topic_resources(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Return resources for broad topic blueprints."""

        blueprint = self._fallback_topic_blueprint(knowledge_point)
        if blueprint is None:
            return []

        return [
            {"name": "高等数学知识路线图", "type": "learning-path", "uri": "/student/learning-path"},
            {"name": "极限、导数、积分重点公式表", "type": "notes", "uri": "/student/courseware"},
            {"name": "高数典型错题与变式训练", "type": "exercise", "uri": "/student/mistakes"},
            {"name": "微积分综合应用题训练", "type": "practice", "uri": "/student/exercise"},
        ]

    def _fallback_prerequisites(self, title: str) -> list[str]:
        """Return curated prerequisite labels when Neo4j is unavailable."""

        prerequisites_by_title = {
            "Python 循环": ["顺序结构", "条件判断"],
            "Python 条件判断": ["布尔表达式", "比较运算"],
            "递归": ["函数调用", "条件判断"],
            "二分查找": ["顺序结构", "条件判断", "循环"],
            "动态规划": ["递归", "数组", "状态转移"],
        }
        return prerequisites_by_title.get(title, [])

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
        else:
            resources.extend(self._fallback_topic_resources(knowledge_point))
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
            return self._fallback_related_resources(knowledge_point)
        try:
            with self._driver.session() as session:
                result = session.run(query, knowledge_point=knowledge_point)
                resources = [record.data() for record in result]
                return resources or self._fallback_related_resources(knowledge_point)
        except Exception:
            logger.exception("Knowledge graph resource query failed, using fallback resources.")
            return self._fallback_related_resources(knowledge_point)

    def recommend_next_points(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Recommend next knowledge points via `RECOMMENDS` links."""

        query = """
        MATCH (kp:KnowledgePoint {name: $knowledge_point})-[:RECOMMENDS]->(next:KnowledgePoint)
        RETURN next.name AS name, next.difficulty AS difficulty, next.importance AS importance
        ORDER BY next.importance DESC, next.difficulty ASC
        """
        if self._driver is None:
            return self._fallback_recommendations(knowledge_point)
        try:
            with self._driver.session() as session:
                result = session.run(query, knowledge_point=knowledge_point)
                recommendations = [record.data() for record in result]
                return recommendations or self._fallback_recommendations(knowledge_point)
        except Exception:
            logger.exception("Knowledge graph recommendation query failed, using fallback recommendations.")
            return self._fallback_recommendations(knowledge_point)

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
                return self._merge_with_topic_blueprint(
                    knowledge_point,
                    {"nodes": unique_nodes, "edges": edges},
                )
        except Exception:
            logger.exception("Knowledge graph visualization query failed, using fallback graph.")
            return self._fallback_visualization_graph(knowledge_point)
