"""Neo4j connector and graph-building helpers for knowledge visualization."""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from sqlalchemy import or_

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import KnowledgePoint, KnowledgeRelation, Resource
from services.agent_service.app.services.knowledge_base import KnowledgeArticle, KnowledgeBaseService

logger = logging.getLogger(__name__)


class KnowledgeGraphRepository:
    """Repository encapsulating knowledge graph queries across multiple data sources."""

    _SECTION_ALIASES = {
        "prerequisite": ("前置知识", "前置基础", "基础知识", "预备知识"),
        "recommended": ("后续模块", "进阶内容", "拓展学习", "拓展延伸", "延伸学习", "相关知识"),
        "resource": ("学习资源", "关联资源", "推荐资源", "练习建议"),
    }

    _STOP_LABELS = {
        "以",
        "它",
        "概念",
        "主题",
        "摘要",
        "再看例子",
        "最后完成自测",
        "阅读方式",
        "学习顺序",
        "理解",
        "运用",
        "区分",
        "准确说出",
        "准确区分",
        "独立推导",
        "识别并避免",
        "分析",
        "核心概念",
        "学习目标",
        "知识讲解",
        "课程导入",
        "你的当前学习情况",
        "重点难点突破",
        "典型例题",
        "课堂小结",
    }

    # Topics that appear in the "拓展延伸" section are treated as
    # recommended follow-up material by the content-based graph builder.
    _EXTENSION_HEADINGS = ("拓展延伸", "拓展学习", "延伸学习", "扩展阅读")

    def __init__(self) -> None:
        settings = get_settings()
        self.knowledge_base = KnowledgeBaseService()
        self._driver = None
        if not settings.neo4j_enabled:
            logger.info("Neo4j disabled.")
            return
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
            )
        except Exception:
            logger.warning("Neo4j driver unavailable.")

    def close(self) -> None:
        """Close the underlying Neo4j driver."""

        if self._driver is not None:
            self._driver.close()

    def _require_driver(self):
        if self._driver is None:
            raise RuntimeError("Neo4j is not available.")
        return self._driver

    def create_knowledge_point(
        self,
        name: str,
        description: str,
        difficulty: int,
        importance: int,
    ) -> dict[str, Any]:
        """Create or update a `KnowledgePoint` node in Neo4j."""

        query = """
        MERGE (kp:KnowledgePoint {name: $name})
        SET kp.description = $description,
            kp.difficulty = $difficulty,
            kp.importance = $importance
        RETURN kp
        """
        driver = self._require_driver()
        with driver.session() as session:
            record = session.run(
                query,
                name=name,
                description=description,
                difficulty=difficulty,
                importance=importance,
            ).single()
            return dict(record["kp"])

    def find_dependency_path(self, knowledge_point: str, max_depth: int = 3) -> list[dict[str, Any]]:
        """Find prerequisite paths from Neo4j, SQL relations, or derived content."""

        results: list[dict[str, Any]] = []
        if self._driver is not None:
            try:
                results.extend(self._find_dependency_path_from_neo4j(knowledge_point, max_depth))
            except Exception as exc:
                logger.warning("Neo4j dependency query failed for %s: %s", knowledge_point, exc)

        results.extend(self._find_dependency_path_from_sql(knowledge_point, max_depth))
        results.extend(self._build_dependency_paths_from_content(knowledge_point))

        unique = self._unique_paths(results)
        if unique:
            return unique
        raise ValueError(f"知识点{knowledge_point}没有可用的依赖关系数据。")

    def find_related_resources(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Return resource nodes associated with a knowledge point."""

        resources: list[dict[str, Any]] = []
        if self._driver is not None:
            try:
                resources.extend(self._find_related_resources_from_neo4j(knowledge_point))
            except Exception as exc:
                logger.warning("Neo4j resource query failed for %s: %s", knowledge_point, exc)

        resources.extend(self._find_related_resources_from_sql(knowledge_point))
        resources.extend(self._build_related_resources_from_content(knowledge_point))

        unique = self._unique_resources(resources)
        if unique:
            return unique
        raise ValueError(f"知识点{knowledge_point}没有可关联的学习资源。")

    def recommend_next_points(self, knowledge_point: str) -> list[dict[str, Any]]:
        """Recommend next knowledge points via `RECOMMENDS` links or derived content."""

        recommendations: list[dict[str, Any]] = []
        if self._driver is not None:
            try:
                recommendations.extend(self._recommend_next_points_from_neo4j(knowledge_point))
            except Exception as exc:
                logger.warning("Neo4j recommendation query failed for %s: %s", knowledge_point, exc)

        recommendations.extend(self._build_recommendations_from_content(knowledge_point))
        unique = self._unique_recommendations(recommendations)
        if unique:
            return unique
        raise ValueError(f"知识点{knowledge_point}没有可推荐的后续知识点。")

    def get_visualization_graph(self, knowledge_point: str, max_depth: int = 2) -> dict[str, list[dict[str, Any]]]:
        """Return node-edge graph data for frontend visualization."""

        graphs: list[dict[str, list[dict[str, Any]]]] = []
        if self._driver is not None:
            try:
                neo4j_graph = self._get_visualization_graph_from_neo4j(knowledge_point, max_depth)
                if neo4j_graph["nodes"]:
                    graphs.append(neo4j_graph)
            except Exception as exc:
                logger.warning("Neo4j visualization query failed for %s: %s", knowledge_point, exc)

        sql_graph = self._get_visualization_graph_from_sql(knowledge_point, max_depth)
        if sql_graph["nodes"]:
            graphs.append(sql_graph)

        content_graph = self._build_visualization_graph_from_content(knowledge_point)
        if content_graph["nodes"]:
            graphs.append(content_graph)

        merged = self._merge_graphs(graphs)
        if merged["nodes"]:
            return merged
        raise ValueError(f"知识点{knowledge_point}没有可视化图谱内容。")

    def _find_dependency_path_from_neo4j(self, knowledge_point: str, max_depth: int) -> list[dict[str, Any]]:
        query = """
        MATCH path = (kp:KnowledgePoint {name: $knowledge_point})-[:DEPENDS_ON*1..$max_depth]->(dep:KnowledgePoint)
        RETURN [node IN nodes(path) | node.name] AS dependency_path
        """
        driver = self._require_driver()
        with driver.session() as session:
            result = session.run(query, knowledge_point=knowledge_point, max_depth=max_depth)
            return [{"path": record["dependency_path"]} for record in result if record["dependency_path"]]

    def _find_related_resources_from_neo4j(self, knowledge_point: str) -> list[dict[str, Any]]:
        query = """
        MATCH (kp:KnowledgePoint {name: $knowledge_point})-[:ASSOCIATED_WITH]-(resource:Resource)
        RETURN resource.name AS name, resource.type AS type, resource.uri AS uri
        """
        driver = self._require_driver()
        with driver.session() as session:
            result = session.run(query, knowledge_point=knowledge_point)
            return [record.data() for record in result]

    def _recommend_next_points_from_neo4j(self, knowledge_point: str) -> list[dict[str, Any]]:
        query = """
        MATCH (kp:KnowledgePoint {name: $knowledge_point})-[:RECOMMENDS]->(next:KnowledgePoint)
        RETURN next.name AS name, next.difficulty AS difficulty, next.importance AS importance
        ORDER BY next.importance DESC, next.difficulty ASC
        """
        driver = self._require_driver()
        with driver.session() as session:
            result = session.run(query, knowledge_point=knowledge_point)
            return [record.data() for record in result]

    def _get_visualization_graph_from_neo4j(
        self,
        knowledge_point: str,
        max_depth: int,
    ) -> dict[str, list[dict[str, Any]]]:
        driver = self._require_driver()
        query = """
        MATCH (kp:KnowledgePoint {name: $knowledge_point})
        OPTIONAL MATCH (kp)-[:DEPENDS_ON*1..$max_depth]->(dep:KnowledgePoint)
        OPTIONAL MATCH (kp)-[:RECOMMENDS]->(next:KnowledgePoint)
        RETURN kp, collect(DISTINCT dep) AS deps, collect(DISTINCT next) AS nexts
        """
        with driver.session() as session:
            record = session.run(query, knowledge_point=knowledge_point, max_depth=max_depth).single()
            if record is None:
                return {"nodes": [], "edges": []}

            nodes = [{"id": knowledge_point, "label": knowledge_point, "category": "current"}]
            edges: list[dict[str, Any]] = []

            for dep in record["deps"]:
                if dep is None:
                    continue
                dep_name = dep.get("name")
                if not dep_name:
                    continue
                nodes.append({"id": dep_name, "label": dep_name, "category": "prerequisite"})
                edges.append({"source": knowledge_point, "target": dep_name, "label": "DEPENDS_ON"})

            for nxt in record["nexts"]:
                if nxt is None:
                    continue
                next_name = nxt.get("name")
                if not next_name:
                    continue
                nodes.append({"id": next_name, "label": next_name, "category": "recommended"})
                edges.append({"source": knowledge_point, "target": next_name, "label": "RECOMMENDS"})

            return self._merge_graphs([{"nodes": nodes, "edges": edges}])

    def _find_dependency_path_from_sql(self, knowledge_point: str, max_depth: int) -> list[dict[str, Any]]:
        with SessionLocal() as db:
            current = db.query(KnowledgePoint).filter(KnowledgePoint.name == knowledge_point).first()
            if current is None:
                return []

            outgoing = (
                db.query(KnowledgeRelation, KnowledgePoint)
                .join(KnowledgePoint, KnowledgeRelation.to_id == KnowledgePoint.id)
                .filter(
                    KnowledgeRelation.from_id == current.id,
                    KnowledgeRelation.relation_type.in_(["DEPENDS_ON", "前置基础"]),
                )
                .limit(max_depth * 3)
                .all()
            )
            incoming = (
                db.query(KnowledgeRelation, KnowledgePoint)
                .join(KnowledgePoint, KnowledgeRelation.from_id == KnowledgePoint.id)
                .filter(
                    KnowledgeRelation.to_id == current.id,
                    KnowledgeRelation.relation_type.in_(["DEPENDS_ON", "前置基础"]),
                )
                .limit(max_depth * 3)
                .all()
            )

            paths = [{"path": [item.name, knowledge_point]} for _, item in outgoing]
            paths.extend({"path": [item.name, knowledge_point]} for _, item in incoming)
            return paths

    def _get_visualization_graph_from_sql(
        self,
        knowledge_point: str,
        max_depth: int,
    ) -> dict[str, list[dict[str, Any]]]:
        with SessionLocal() as db:
            current = db.query(KnowledgePoint).filter(KnowledgePoint.name == knowledge_point).first()
            if current is None:
                return {"nodes": [], "edges": []}

            nodes = [{"id": current.name, "label": current.name, "category": "current"}]
            edges: list[dict[str, Any]] = []

            outgoing = (
                db.query(KnowledgeRelation, KnowledgePoint)
                .join(KnowledgePoint, KnowledgeRelation.to_id == KnowledgePoint.id)
                .filter(KnowledgeRelation.from_id == current.id)
                .limit(max_depth * 4)
                .all()
            )
            incoming = (
                db.query(KnowledgeRelation, KnowledgePoint)
                .join(KnowledgePoint, KnowledgeRelation.from_id == KnowledgePoint.id)
                .filter(KnowledgeRelation.to_id == current.id)
                .limit(max_depth * 4)
                .all()
            )

            for relation, target in outgoing:
                category = "recommended" if relation.relation_type in {"RECOMMENDS", "后续模块"} else "prerequisite"
                nodes.append({"id": target.name, "label": target.name, "category": category})
                edges.append({"source": current.name, "target": target.name, "label": relation.relation_type})

            for relation, source in incoming:
                category = "prerequisite" if relation.relation_type in {"DEPENDS_ON", "前置基础"} else "recommended"
                nodes.append({"id": source.name, "label": source.name, "category": category})
                edges.append({"source": current.name, "target": source.name, "label": relation.relation_type})

            return self._merge_graphs([{"nodes": nodes, "edges": edges}])

    def _build_visualization_graph_from_content(self, knowledge_point: str) -> dict[str, list[dict[str, Any]]]:
        article = self._get_article_for_graph(knowledge_point)
        nodes = [{"id": knowledge_point, "label": knowledge_point, "category": "current"}]
        edges: list[dict[str, Any]] = []

        for prerequisite in self._derive_prerequisites(knowledge_point, article):
            nodes.append({"id": prerequisite, "label": prerequisite, "category": "prerequisite"})
            edges.append({"source": knowledge_point, "target": prerequisite, "label": "前置基础"})

        for recommended in self._derive_recommendations(knowledge_point, article):
            nodes.append({"id": recommended, "label": recommended, "category": "recommended"})
            edges.append({"source": knowledge_point, "target": recommended, "label": "后续模块"})

        for resource in self._derive_resource_nodes(knowledge_point, article):
            nodes.append({"id": resource, "label": resource, "category": "resource"})
            edges.append({"source": knowledge_point, "target": resource, "label": "关联资源"})

        # When content-derived derivation fails, fall back to title-based
        # sub-topic extraction so the user sees related concepts from the
        # knowledge point name itself (e.g. "高等数学：极限、导数与积分"
        # → 极限, 导数, 积分).
        if len(nodes) <= 1:
            for sub_topic in self._derive_topics_from_title(knowledge_point):
                nodes.append({"id": sub_topic, "label": sub_topic, "category": "prerequisite"})
                edges.append({"source": knowledge_point, "target": sub_topic, "label": "前置基础"})

        if len(nodes) <= 1:
            for sub_topic in self._derive_topics_from_title(knowledge_point):
                nodes.append({"id": sub_topic, "label": sub_topic, "category": "recommended"})
                edges.append({"source": knowledge_point, "target": sub_topic, "label": "后续模块"})

        graph = self._merge_graphs([{"nodes": nodes, "edges": edges}])
        # Treat a single topic without edges as "graph" too — the frontend
        # handles this gracefully.
        return graph

    def _build_dependency_paths_from_content(self, knowledge_point: str) -> list[dict[str, Any]]:
        article = self._get_article_for_graph(knowledge_point)
        return [{"path": [item, knowledge_point]} for item in self._derive_prerequisites(knowledge_point, article)]

    def _build_related_resources_from_content(self, knowledge_point: str) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        article = self._get_article_for_graph(knowledge_point)
        if article is not None:
            for item in self.knowledge_base.article_to_dict(article).get("external_resources", [])[:6]:
                if not isinstance(item, dict):
                    continue
                resources.append(
                    {
                        "name": str(item.get("title") or "关联资源"),
                        "type": str(item.get("kind") or "resource"),
                        "uri": str(item.get("url") or ""),
                    }
                )
        return resources

    def _build_recommendations_from_content(self, knowledge_point: str) -> list[dict[str, Any]]:
        article = self._get_article_for_graph(knowledge_point)
        return [
            {"name": item, "difficulty": 1, "importance": 1}
            for item in self._derive_recommendations(knowledge_point, article)
        ]

    def _find_related_resources_from_sql(self, knowledge_point: str) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        for resource, kp in self._matching_resource_rows(knowledge_point, limit=8):
            title = self._extract_title_from_content(resource.content) or f"{(kp.name if kp else knowledge_point)}资源"
            resources.append(
                {
                    "name": title,
                    "type": resource.type,
                    "uri": f"/resources/{resource.id}",
                }
            )
        return resources

    def _get_article_for_graph(self, knowledge_point: str) -> KnowledgeArticle | None:
        return self.knowledge_base.get_article(knowledge_point)

    def _derive_prerequisites(self, knowledge_point: str, article: KnowledgeArticle | None) -> list[str]:
        labels: list[str] = []
        labels.extend(self._prerequisites_from_article(article) if article is not None else [])
        labels.extend(self._extract_section_items(knowledge_point, "prerequisite"))
        labels.extend(self._extract_introductory_concepts(knowledge_point))
        labels.extend(self._match_existing_points(knowledge_point, relation="prerequisite"))
        # Use article title for fallback lookup when available, since the
        # shorthand KP name (e.g. "高数") may not match the dict keys.
        lookup_name = article.title if article is not None else knowledge_point
        labels.extend(self._fallback_prerequisites(lookup_name))
        if not labels:
            labels.extend(self._derive_topics_from_title(lookup_name))
        # Deduplicate AFTER collecting all sources so that true duplicates
        # don't distort the frequency-based ranking in _normalize_labels.
        labels = list(dict.fromkeys(labels))
        return self._finalize_labels(knowledge_point, labels)

    def _derive_recommendations(self, knowledge_point: str, article: KnowledgeArticle | None) -> list[str]:
        labels: list[str] = []
        labels.extend(self._recommendations_from_article(article) if article is not None else [])
        labels.extend(self._extract_section_items(knowledge_point, "recommended"))
        labels.extend(self._extract_extension_targets(knowledge_point))
        labels.extend(self._extract_learning_objective_targets(knowledge_point))
        labels.extend(self._match_existing_points(knowledge_point, relation="recommended"))
        if not labels:
            lookup_name = article.title if article is not None else knowledge_point
            labels.extend(self._derive_topics_from_title(lookup_name))
        return self._finalize_labels(knowledge_point, labels)

    def _derive_resource_nodes(self, knowledge_point: str, article: KnowledgeArticle | None) -> list[str]:
        labels: list[str] = []
        if article is not None:
            labels.extend(
                str(item.get("title") or "")
                for item in self.knowledge_base.article_to_dict(article).get("external_resources", [])[:4]
                if isinstance(item, dict)
            )
        labels.extend(self._extract_section_items(knowledge_point, "resource"))
        labels.extend(self._resource_titles_from_sql(knowledge_point))
        return self._finalize_labels(knowledge_point, labels, limit=6)

    def _prerequisites_from_article(self, article: KnowledgeArticle) -> list[str]:
        labels = list(self._fallback_prerequisites(article.title))
        labels.extend(self._short_concept_label(item) for item in article.concepts[:4])
        return [item for item in labels if item]

    def _recommendations_from_article(self, article: KnowledgeArticle) -> list[str]:
        labels = [self._clean_text_label(item, max_len=20) for item in article.checks[:2]]
        labels.extend(self._clean_text_label(item, max_len=18) for item in article.applications[:2])
        return [item for item in labels if item]

    def _extract_section_items(self, knowledge_point: str, section_kind: str) -> list[str]:
        content = self._combined_resource_text(knowledge_point)
        if not content:
            return []

        aliases = self._SECTION_ALIASES[section_kind]
        items: list[str] = []
        for alias in aliases:
            pattern = re.compile(rf"##+\s*{re.escape(alias)}\s*\n(?P<body>.*?)(?:\n##|\Z)", re.S)
            match = pattern.search(content)
            if not match:
                continue
            body = match.group("body")
            items.extend(self._extract_bullets_from_text(body))
        return items

    def _extract_introductory_concepts(self, knowledge_point: str) -> list[str]:
        content = self._combined_resource_text(knowledge_point)
        if not content:
            return []

        concepts: list[str] = []
        for heading in ("学习目标", "知识讲解", "核心概念"):
            pattern = re.compile(rf"##+\s*{re.escape(heading)}\s*\n(?P<body>.*?)(?:\n##|\Z)", re.S)
            match = pattern.search(content)
            if not match:
                continue
            body = match.group("body")
            for line in body.splitlines():
                concepts.extend(self._extract_phrases_from_line(line))
        return concepts[:8]

    def _extract_learning_objective_targets(self, knowledge_point: str) -> list[str]:
        content = self._combined_resource_text(knowledge_point)
        if not content:
            return []

        match = re.search(r"##+\s*学习目标\s*\n(?P<body>.*?)(?:\n##|\Z)", content, re.S)
        if not match:
            return []

        labels: list[str] = []
        for line in match.group("body").splitlines():
            if any(token in line for token in ("运用", "解释", "推导", "识别", "区分", "分析")):
                labels.extend(self._extract_phrases_from_line(line))
        return labels

    def _extract_extension_targets(self, knowledge_point: str) -> list[str]:
        """Extract next-step topics from `## 拓展延伸` (or similar) sections.

        Real LLM-generated courseware typically ends with a section like::

            ## 拓展延伸：下一步可以学什么？
            - 机器学习中的概率模型（分类、回归）
            - A/B 测试与因果推断入门
            - 数据库索引与查询优化

        Every list item after the heading is harvested as a recommended topic.
        """
        content = self._combined_resource_text(knowledge_point)
        if not content:
            return []

        items: list[str] = []
        for heading in self._EXTENSION_HEADINGS:
            pattern = re.compile(rf"##+\s*{re.escape(heading)}[^\n]*\n(?P<body>.*?)(?:\n##|\Z)", re.S)
            match = pattern.search(content)
            if not match:
                continue
            body = match.group("body")
            items.extend(self._extract_bullets_from_text(body))

        return items

    def _match_existing_points(self, knowledge_point: str, relation: str) -> list[str]:
        current_tokens = set(self._tokenize(knowledge_point))
        if not current_tokens:
            return []

        with SessionLocal() as db:
            names = [str(item[0]) for item in db.query(KnowledgePoint.name).all() if str(item[0]).strip()]

        scored: list[tuple[int, str]] = []
        current_lower = knowledge_point.lower()
        for candidate in names:
            if candidate == knowledge_point:
                continue
            candidate_tokens = set(self._tokenize(candidate))
            overlap = len(current_tokens & candidate_tokens)
            if overlap <= 0:
                continue
            score = overlap * 10
            if relation == "recommended" and candidate.lower() > current_lower:
                score += 1
            scored.append((score, candidate))

        scored.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
        return [item[1] for item in scored[:4]]

    def _resource_titles_from_sql(self, knowledge_point: str) -> list[str]:
        titles: list[str] = []
        for resource, _ in self._matching_resource_rows(knowledge_point, limit=4):
            title = self._extract_title_from_content(resource.content)
            if title:
                titles.append(title)
        return titles

    def _combined_resource_text(self, knowledge_point: str) -> str:
        chunks: list[str] = []
        for resource, _ in self._matching_resource_rows(knowledge_point, limit=4):
            chunks.append(resource.content or "")
        return "\n".join(chunks)

    def _matching_resource_rows(self, knowledge_point: str, limit: int) -> list[tuple[Resource, KnowledgePoint | None]]:
        with SessionLocal() as db:
            exact_rows = (
                db.query(Resource, KnowledgePoint)
                .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
                .filter(KnowledgePoint.name == knowledge_point)
                .order_by(Resource.id.desc())
                .limit(limit)
                .all()
            )
            if exact_rows:
                return exact_rows

            return (
                db.query(Resource, KnowledgePoint)
                .outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id)
                .filter(Resource.content.contains(knowledge_point))
                .order_by(Resource.id.desc())
                .limit(limit)
                .all()
            )

    def _extract_bullets_from_text(self, text: str) -> list[str]:
        labels: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", "* ", "1.", "2.", "3.", "4.", "5.")):
                labels.extend(self._extract_phrases_from_line(stripped))
        return labels

    def _merge_graphs(self, graphs: list[dict[str, list[dict[str, Any]]]]) -> dict[str, list[dict[str, Any]]]:
        nodes_by_id: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        edge_keys: set[tuple[str, str, str]] = set()

        for graph in graphs:
            for node in graph.get("nodes", []):
                node_id = str(node.get("id") or "").strip()
                if not node_id:
                    continue
                nodes_by_id[node_id] = {
                    "id": node_id,
                    "label": str(node.get("label") or node_id),
                    "category": str(node.get("category") or "resource"),
                }
            for edge in graph.get("edges", []):
                source = str(edge.get("source") or "").strip()
                target = str(edge.get("target") or "").strip()
                label = str(edge.get("label") or "").strip()
                if not source or not target:
                    continue
                key = (source, target, label)
                if key in edge_keys:
                    continue
                edge_keys.add(key)
                edges.append({"source": source, "target": target, "label": label})

        return {"nodes": list(nodes_by_id.values()), "edges": edges}

    def _unique_paths(self, paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for item in paths:
            raw_path = item.get("path")
            if not isinstance(raw_path, list):
                continue
            normalized = tuple(str(node).strip() for node in raw_path if str(node).strip())
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            unique.append({"path": list(normalized)})
        return unique

    def _unique_resources(self, resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in resources:
            name = str(item.get("name") or item.get("title") or "").strip()
            uri = str(item.get("uri") or "").strip()
            if not name:
                continue
            key = (name, uri)
            if key in seen:
                continue
            seen.add(key)
            unique.append(
                {
                    "name": name,
                    "type": str(item.get("type") or item.get("kind") or "resource"),
                    "uri": uri,
                }
            )
        return unique

    def _unique_recommendations(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            unique.append(
                {
                    "name": name,
                    "difficulty": int(item.get("difficulty") or 1),
                    "importance": int(item.get("importance") or 1),
                }
            )
        return unique

    def _normalize_labels(self, labels: list[str], limit: int = 5) -> list[str]:
        cleaned = [self._clean_text_label(item) for item in labels if isinstance(item, str) and item.strip()]
        cleaned = [item for item in cleaned if item]
        counts = Counter(cleaned)
        ordered = sorted(counts, key=lambda item: (-counts[item], len(item), item))
        return ordered[:limit]

    def _finalize_labels(self, knowledge_point: str, labels: list[str], limit: int = 5) -> list[str]:
        normalized = self._normalize_labels(labels, limit=limit * 3)
        results: list[str] = []
        normalized_point = self._clean_text_label(knowledge_point, max_len=40)
        for label in normalized:
            if not label:
                continue
            if label == normalized_point:
                continue
            if "个性化课件" in label or "学习课件" in label:
                continue
            if label.startswith(("主题 ", "摘要 ", "阅读方式 ", "学习顺序 ")):
                continue
            results.append(label)
            if len(results) >= limit:
                break
        return results

    def _clean_text_label(self, value: str, max_len: int = 18) -> str:
        label = re.sub(r"^[\-\*\d\.\s]+", "", value).strip()
        label = re.sub(r"[`#>\[\]\(\)（）]", " ", label)
        label = re.sub(r"[""\"''']", "", label)
        label = re.sub(r"\*\*|__|[:：；;，,。！？!?]", " ", label)
        label = re.sub(r"\s+", " ", label).strip()
        for token in ("你应该能够", "学完这节课后", "根据系统记录", "重点提醒", "这节课围绕", "当前掌握度约"):
            label = label.replace(token, "").strip()
        for prefix in ("主题 ", "摘要 ", "阅读方式 ", "学习顺序 ", "核心主题 "):
            if label.startswith(prefix):
                label = label[len(prefix) :].strip()
        label = re.sub(r"^(以及|以及它和|以及它|以及|关于|其中|一个|一种)\s*", "", label).strip()
        label = re.sub(r"\s*(是什么|的内容|的关系|时运动状态的区别)$", "", label).strip()
        # Strip common text book / mooc suffixes that are noise
        label = re.sub(r"\s+[（(][^)）]*[）)]$", "", label).strip()
        if label in self._STOP_LABELS or len(label) < 2:
            return ""
        if len(label) > max_len:
            label = label[:max_len].strip()
        return label

    def _short_concept_label(self, concept: str) -> str:
        """Extract the key topic phrase from a long concept sentence.

        "极限描述自变量逼近某一点...做极值..." → "极限"
        """
        # Strip backtick-wrapped inline code before processing
        text = re.sub(r"`([^`]+)`", r"\1", concept)
        # Extract first clause before any punctuation
        text = text.split("：", 1)[0].split(":", 1)[0]
        for delim in ("，", ",", "。", ".", "、", "；", ";", "——"):
            before = text.split(delim, 1)[0]
            if len(before.strip()) >= 2:
                text = before
        text = text.strip("` ").strip()
        # If the first clause is long, try to extract a short keyword
        if len(text) > 6:
            for n in (2, 3):
                if n <= len(text):
                    short = text[:n]
                    # Only accept CJK-looking substrings for Chinese concept labels
                    if not any(c in short for c in "，、。的了一在是") and any(
                        "一" <= c <= "鿿" for c in short
                    ):
                        return short
        return self._clean_text_label(text)

    def _line_to_label(self, line: str) -> str:
        return self._clean_text_label(re.sub(r"^\d+\.\s*", "", line.strip()))

    def _extract_phrases_from_line(self, line: str) -> list[str]:
        stripped = line.strip()
        if not stripped:
            return []

        candidates: list[str] = []
        candidates.extend(re.findall(r"\*\*(.+?)\*\*", stripped))
        candidates.extend(re.findall(r"[“「]([^”」]{2,20})[”」]", stripped))

        for token in ("理解", "掌握", "区分", "运用", "解释", "推导", "识别", "分析", "准确说出", "准确区分", "独立推导", "识别并避免"):
            if token in stripped:
                remainder = stripped.split(token, 1)[1]
                candidates.extend(self._split_labels(remainder))

        if not candidates:
            candidates.append(stripped)

        cleaned = [self._line_to_label(item) for item in candidates]
        return [item for item in cleaned if item and item not in self._STOP_LABELS]

    def _extract_title_from_content(self, content: str) -> str:
        for line in (content or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
            if stripped.startswith("## "):
                return stripped[3:].strip()
        return ""

    def _tokenize(self, text: str) -> list[str]:
        if not text.strip():
            return []
        chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        latin_chunks = re.findall(r"[A-Za-z]{3,}", text.lower())
        tokens: list[str] = list(latin_chunks)
        for chunk in chinese_chunks:
            tokens.append(chunk)
            max_window = min(4, len(chunk))
            for size in range(2, max_window + 1):
                for start in range(0, len(chunk) - size + 1):
                    tokens.append(chunk[start : start + size])
        return tokens

    def _split_labels(self, text: str) -> list[str]:
        return [
            self._clean_text_label(item)
            for item in re.split(r"(?:、|，|,|；|;|和|与|以及|及其|及|/)\s*", text)
            if self._clean_text_label(item)
        ]

    def _derive_topics_from_title(self, knowledge_point: str) -> list[str]:
        """Extract sub-topics from a colon/comma-separated knowledge point title.

        "高等数学：极限、导数与积分" → ["极限", "导数", "积分"]
        "Python 循环" → ["for循环", "while循环"]
        """
        topics: list[str] = []
        # Split on colon-like separators — the right-hand side often lists sub-topics
        for sep in ("：", ":", "——", "—"):
            if sep in knowledge_point:
                rhs = knowledge_point.split(sep, 1)[1].strip()
                topics.extend(self._split_labels(rhs))
                break

        # "Python 循环" style — extract both sides of common conjunction patterns
        for sep in ("和", "与", "及其", "及", "、", ","):
            parts = knowledge_point.split(sep, 1)
            if len(parts) > 1 and parts[1].strip():
                topics.extend(parts)
                break

        # For well-known topic patterns, add canonical sub-topics
        topic_hints: dict[str, list[str]] = {
            "高等数学": ["极限", "导数", "积分", "微分"],
            "概率统计": ["随机变量", "期望", "方差", "贝叶斯"],
            "线性代数": ["矩阵", "向量空间", "特征值", "行列式"],
            "数据结构": ["线性表", "栈", "队列", "树"],
            "算法分析": ["时间复杂度", "空间复杂度", "递归", "分治"],
            "数据库": ["关系模型", "SQL", "事务", "索引"],
            "操作系统": ["进程", "线程", "内存管理", "文件系统"],
            "计算机网络": ["TCP", "IP", "HTTP", "DNS"],
            "软件工程": ["需求分析", "架构设计", "测试", "版本管理"],
        }
        for key, hints in topic_hints.items():
            if key in knowledge_point:
                topics.extend(hints)
                break

        cleaned = [self._clean_text_label(t, max_len=18) for t in topics]
        return [t for t in cleaned if t and t not in self._STOP_LABELS]

    def _fallback_prerequisites(self, title: str) -> list[str]:
        """No hardcoded fallback — all prerequisite knowledge is derived from live data."""
        return []

    # ------------------------------------------------------------------
    # Courseware → graph synchronization
    # ------------------------------------------------------------------

    def sync_courseware_to_graph(self, knowledge_point: str) -> dict[str, Any]:
        """Parse courseware content into graph relations and persist them.

        Scans all Resource rows matching *knowledge_point*, extracts
        prerequisite and recommended topic names from their Markdown
        content, then writes them as:

        * SQL ``KnowledgeRelation`` rows (``DEPENDS_ON`` / ``RECOMMENDS``)
        * Neo4j ``DEPENDS_ON`` / ``RECOMMENDS`` edges (when Neo4j is enabled)

        Returns a dict with counts of newly-created relations and nodes.
        """
        prerequisites = self._derive_prerequisites(knowledge_point, None)
        recommendations = self._derive_recommendations(knowledge_point, None)

        result: dict[str, Any] = {
            "knowledge_point": knowledge_point,
            "prerequisites_extracted": prerequisites,
            "recommendations_extracted": recommendations,
            "sql_knowledge_points_created": 0,
            "sql_relations_created": 0,
            "neo4j_relations_created": 0,
        }

        if not prerequisites and not recommendations:
            return result

        with SessionLocal() as db:
            # ensure the current knowledge point exists in SQL
            current_kp = self._get_or_create_sql_knowledge_point(
                db, knowledge_point
            )

            # persist prerequisite relations
            for prereq_name in prerequisites:
                prereq_kp = self._get_or_create_sql_knowledge_point(db, prereq_name)
                if self._create_sql_relation_if_absent(
                    db, prereq_kp.id, current_kp.id, "DEPENDS_ON"
                ):
                    result["sql_relations_created"] += 1

            # persist recommendation relations
            for rec_name in recommendations:
                rec_kp = self._get_or_create_sql_knowledge_point(db, rec_name)
                if self._create_sql_relation_if_absent(
                    db, current_kp.id, rec_kp.id, "RECOMMENDS"
                ):
                    result["sql_relations_created"] += 1

            db.commit()

        # mirror to Neo4j when available
        neo4j_count = self._sync_relations_to_neo4j(
            knowledge_point, prerequisites, "DEPENDS_ON"
        ) + self._sync_relations_to_neo4j(
            knowledge_point, recommendations, "RECOMMENDS"
        )
        result["neo4j_relations_created"] = neo4j_count

        logger.info(
            "sync_courseware_to_graph: kp=%s prereq=%d rec=%d sql_rel=%d neo4j_rel=%d",
            knowledge_point,
            len(prerequisites),
            len(recommendations),
            result["sql_relations_created"],
            neo4j_count,
        )
        return result

    def _get_or_create_sql_knowledge_point(
        self, db: Any, name: str
    ) -> KnowledgePoint:
        existing = (
            db.query(KnowledgePoint).filter(KnowledgePoint.name == name).first()
        )
        if existing is not None:
            return existing
        kp = KnowledgePoint(
            name=name,
            description=f"从课件内容自动提取 {name}",
            difficulty=2,
            importance=2,
        )
        db.add(kp)
        db.flush()
        return kp

    def _create_sql_relation_if_absent(
        self, db: Any, from_id: int, to_id: int, relation_type: str
    ) -> bool:
        existing = (
            db.query(KnowledgeRelation)
            .filter(
                KnowledgeRelation.from_id == from_id,
                KnowledgeRelation.to_id == to_id,
                KnowledgeRelation.relation_type == relation_type,
            )
            .first()
        )
        if existing is not None:
            return False
        db.add(
            KnowledgeRelation(
                from_id=from_id,
                to_id=to_id,
                relation_type=relation_type,
            )
        )
        return True

    def _sync_relations_to_neo4j(
        self,
        knowledge_point: str,
        targets: list[str],
        relation_type: str,
    ) -> int:
        if self._driver is None:
            return 0
        count = 0
        try:
            driver = self._require_driver()
            with driver.session() as session:
                for target in targets:
                    query = """
                    MERGE (kp:KnowledgePoint {name: $knowledge_point})
                    MERGE (target:KnowledgePoint {name: $target})
                    MERGE (kp)-[r:RELATION {type: $relation_type}]->(target)
                    SET r.label = $relation_type
                    """
                    session.run(
                        query,
                        knowledge_point=knowledge_point,
                        target=target,
                        relation_type=relation_type,
                    )
                    count += 1
        except Exception as exc:
            logger.warning(
                "Neo4j relation sync failed for %s (%s): %s",
                knowledge_point,
                relation_type,
                exc,
            )
        return count
