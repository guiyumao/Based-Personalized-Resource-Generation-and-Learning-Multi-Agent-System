"""Neo4j connector and graph-building helpers for knowledge visualization."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

from sqlalchemy import or_

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import KnowledgePoint, KnowledgeRelation, Resource
from services.agent_service.app.services.knowledge_base import KnowledgeArticle, KnowledgeBaseService
from services.agent_service.app.services.llm_factory import LLMFactory
from services.agent_service.app.services.web_search_service import WebSearchService

logger = logging.getLogger(__name__)

_GRAPH_LLM_PROMPT = """你是知识图谱助手。给定知识点名称和搜索结果，输出前置依赖和后续进阶。

输出JSON(键必须双引号):
{"prereqs": ["前置1"], "recs": ["进阶1"]}

知识点: {kp}
搜索结果: {web}"""


class KnowledgeGraphRepository:
    _SECTION_ALIASES = {
        "prerequisite": ("前置知识", "前置基础", "基础知识", "预备知识"),
        "recommended": ("后续模块", "进阶内容", "拓展学习", "拓展延伸", "延伸学习", "相关知识"),
        "resource": ("学习资源", "关联资源", "推荐资源", "练习建议"),
    }
    _STOP_LABELS = {
        "以", "它", "概念", "主题", "摘要", "再看例子", "最后完成自测",
        "阅读方式", "学习顺序", "理解", "运用", "区分", "准确说出", "准确区分",
        "独立推导", "识别并避免", "分析", "核心概念", "学习目标", "知识讲解",
        "课程导入", "你的当前学习情况", "重点难点突破", "典型例题", "课堂小结",
    }
    _EXTENSION_HEADINGS = ("拓展延伸", "拓展学习", "延伸学习", "扩展阅读")

    def __init__(self) -> None:
        settings = get_settings()
        self.knowledge_base = KnowledgeBaseService()
        self.llm_factory = LLMFactory(settings)
        self.web_search = WebSearchService(settings)
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
        if self._driver is not None: self._driver.close()
    def _require_driver(self):
        if self._driver is None: raise RuntimeError("Neo4j is not available.")
        return self._driver

    def create_knowledge_point(self, name, desc, diff, imp):
        q = """MERGE (kp:KnowledgePoint {name:$n}) SET kp.description=$d,kp.difficulty=$f,kp.importance=$i RETURN kp"""
        with self._require_driver().session() as s:
            return dict(s.run(q, n=name, d=desc, f=diff, i=imp).single()["kp"])

    def find_dependency_path(self, kp, max_depth=3):
        results = []
        if self._driver is not None:
            try: results.extend(self._find_dependency_path_from_neo4j(kp, max_depth))
            except Exception as exc: logger.warning("Neo4j dep query failed: %s", exc)
        results.extend(self._find_dependency_path_from_sql(kp, max_depth))
        results.extend(self._build_dependency_paths_from_content(kp))
        u = self._unique_paths(results)
        if u: return u
        raise ValueError(f"知识点没有依赖数据")

    def find_related_resources(self, kp):
        resources = []
        if self._driver is not None:
            try: resources.extend(self._find_related_resources_from_neo4j(kp))
            except Exception as exc: logger.warning("Neo4j res query failed: %s", exc)
        resources.extend(self._find_related_resources_from_sql(kp))
        resources.extend(self._build_related_resources_from_content(kp))
        u = self._unique_resources(resources)
        if u: return u
        raise ValueError(f"知识点没有关联资源")

    def get_visualization_graph(self, kp, max_depth=2):
        graphs = []
        if self._driver is not None:
            try:
                ng = self._get_visualization_graph_from_neo4j(kp, max_depth)
                if ng["nodes"]: graphs.append(ng)
            except Exception as exc: logger.warning("Neo4j vis failed: %s", exc)
        sg = self._get_visualization_graph_from_sql(kp, max_depth)
        if sg["nodes"]: graphs.append(sg)
        cg = self._build_visualization_graph_from_content(kp)
        if cg["nodes"]: graphs.append(cg)
        merged = self._merge_graphs(graphs)
        if merged["nodes"] and merged["edges"]: return merged
        raise ValueError(f"知识点没有图谱数据")

    def _find_dependency_path_from_neo4j(self, kp, md):
        q = """MATCH path=(kp:KnowledgePoint {name:$kp})-[:DEPENDS_ON*1..$md]->(d) RETURN [n IN nodes(path)|n.name] AS dp"""
        with self._require_driver().session() as s:
            return [{"path": r["dp"]} for r in s.run(q, kp=kp, md=md) if r["dp"]]

    def _find_related_resources_from_neo4j(self, kp):
        q = """MATCH (kp:KnowledgePoint {name:$kp})-[:ASSOCIATED_WITH]-(r:Resource) RETURN r.name AS name,r.type AS type,r.uri AS uri"""
        with self._require_driver().session() as s:
            return [r.data() for r in s.run(q, kp=kp)]

    def _get_visualization_graph_from_neo4j(self, kp, md):
        q = """MATCH (kp:KnowledgePoint {name:$kp}) OPTIONAL MATCH (kp)-[:DEPENDS_ON*1..$md]->(d) OPTIONAL MATCH (kp)-[:RECOMMENDS]->(n) RETURN kp.name AS cur, collect(DISTINCT d.name) AS deps, collect(DISTINCT n.name) AS nexts"""
        with self._require_driver().session() as s:
            r = s.run(q, kp=kp, md=md).single()
            if not r: return {"nodes": [], "edges": []}
            nodes = [{"id":r["cur"],"label":r["cur"],"category":"current"}]
            edges = []
            for d in (r.get("deps") or []):
                if d: nodes.append({"id":d,"label":d,"category":"prerequisite"}); edges.append({"source":r["cur"],"target":d,"label":"DEPENDS_ON"})
            for n in (r.get("nexts") or []):
                if n: nodes.append({"id":n,"label":n,"category":"recommended"}); edges.append({"source":r["cur"],"target":n,"label":"RECOMMENDS"})
            return {"nodes": nodes, "edges": edges}

    def _find_dependency_path_from_sql(self, kp, md):
        with SessionLocal() as db:
            cur = db.query(KnowledgePoint).filter(KnowledgePoint.name == kp).first()
            if not cur: return []
            out = db.query(KnowledgeRelation, KnowledgePoint).join(KnowledgePoint, KnowledgeRelation.to_id == KnowledgePoint.id).filter(KnowledgeRelation.from_id == cur.id, or_(KnowledgeRelation.relation_type == "DEPENDS_ON", KnowledgeRelation.relation_type == "前置基础")).all()
            return [{"path": [kp, t.name]} for _, t in out]

    def _get_visualization_graph_from_sql(self, kp, md):
        with SessionLocal() as db:
            cur = db.query(KnowledgePoint).filter(KnowledgePoint.name == kp).first()
            if not cur: return {"nodes": [], "edges": []}
            nodes = [{"id": kp, "label": kp, "category": "current"}]
            edges = []
            out = db.query(KnowledgeRelation, KnowledgePoint).join(KnowledgePoint, KnowledgeRelation.to_id == KnowledgePoint.id).filter(KnowledgeRelation.from_id == cur.id).all()
            inc = db.query(KnowledgeRelation, KnowledgePoint).join(KnowledgePoint, KnowledgeRelation.from_id == KnowledgePoint.id).filter(KnowledgeRelation.to_id == cur.id).all()
            for r, t in out:
                cat = "recommended" if r.relation_type in {"RECOMMENDS", "后续模块"} else "prerequisite"
                nodes.append({"id": t.name, "label": t.name, "category": cat})
                edges.append({"source": cur.name, "target": t.name, "label": r.relation_type})
            for r, s in inc:
                cat = "prerequisite" if r.relation_type in {"DEPENDS_ON", "前置基础"} else "recommended"
                nodes.append({"id": s.name, "label": s.name, "category": cat})
                edges.append({"source": cur.name, "target": s.name, "label": r.relation_type})
            return self._merge_graphs([{"nodes": nodes, "edges": edges}])

    def _build_visualization_graph_from_content(self, kp):
        article = self._get_article_for_graph(kp)
        nodes = [{"id": kp, "label": kp, "category": "current"}]
        edges = []
        for p in self._derive_prerequisites(kp, article):
            nodes.append({"id": p, "label": p, "category": "prerequisite"})
            edges.append({"source": kp, "target": p, "label": "前置基础"})
        for r in self._derive_recommendations(kp, article):
            nodes.append({"id": r, "label": r, "category": "recommended"})
            edges.append({"source": kp, "target": r, "label": "后续模块"})
        for r in self._derive_resource_nodes(kp, article):
            nodes.append({"id": r, "label": r, "category": "resource"})
            edges.append({"source": kp, "target": r, "label": "关联资源"})
        g = self._merge_graphs([{"nodes": nodes, "edges": edges}])
        return {"nodes": [], "edges": []} if len(g["nodes"]) <= 1 or not g["edges"] else g

    def _build_dependency_paths_from_content(self, kp):
        a = self._get_article_for_graph(kp)
        return [{"path": [i, kp]} for i in self._derive_prerequisites(kp, a)]

    def _build_related_resources_from_content(self, kp):
        r = []; a = self._get_article_for_graph(kp)
        if a:
            for i in self.knowledge_base.article_to_dict(a).get("external_resources", [])[:6]:
                if isinstance(i, dict): r.append({"name": str(i.get("title") or "res"), "type": str(i.get("kind") or "resource"), "uri": str(i.get("url") or "")})
        return r

    def _build_recommendations_from_content(self, kp):
        a = self._get_article_for_graph(kp)
        return [{"name": t, "difficulty": 1, "importance": 1} for t in self._derive_recommendations(kp, a)]

    def _find_related_resources_from_sql(self, kp):
        r = []
        for res, k in self._matching_resource_rows(kp, 8):
            t = self._extract_title_from_content(res.content) or f"{(k.name if k else kp)}资源"
            r.append({"name": t, "type": res.type, "uri": f"/resources/{res.id}"})
        return r

    def _get_article_for_graph(self, kp): return self.knowledge_base.get_article(kp)

    def _derive_prerequisites(self, kp, article):
        labels = []
        if article: labels.extend(self._prerequisites_from_article(article))
        labels.extend(self._extract_section_items(kp, "prerequisite"))
        labels.extend(self._extract_introductory_concepts(kp))
        labels.extend(self._match_existing_points(kp, "prerequisite"))
        lookup = article.title if article else kp
        labels.extend(self._fallback_prerequisites(lookup))
        if not labels: labels.extend(self._derive_topics_from_title(lookup))
        return self._finalize_labels(kp, list(dict.fromkeys(labels)))

    def _derive_recommendations(self, kp, article):
        labels = []
        if article: labels.extend(self._recommendations_from_article(article))
        labels.extend(self._extract_section_items(kp, "recommended"))
        labels.extend(self._extract_extension_targets(kp))
        labels.extend(self._extract_learning_objective_targets(kp))
        labels.extend(self._match_existing_points(kp, "recommended"))
        if not labels:
            lookup = article.title if article else kp
            labels.extend(self._derive_topics_from_title(lookup))
        return self._finalize_labels(kp, labels)

    def _derive_resource_nodes(self, kp, article):
        labels = []
        if article:
            labels.extend(str(i.get("title") or "") for i in self.knowledge_base.article_to_dict(article).get("external_resources", [])[:4] if isinstance(i, dict))
        labels.extend(self._extract_section_items(kp, "resource"))
        labels.extend(self._resource_titles_from_sql(kp))
        return self._finalize_labels(kp, labels, limit=6)

    def _prerequisites_from_article(self, article):
        return [i for i in (list(self._fallback_prerequisites(article.title)) + [self._short_concept_label(c) for c in article.concepts[:4]]) if i]

    def _recommendations_from_article(self, article):
        return [i for i in ([self._clean_text_label(c, 20) for c in article.checks[:2]] + [self._clean_text_label(a, 18) for a in article.applications[:2]]) if i]

    def _extract_section_items(self, kp, kind):
        content = self._combined_resource_text(kp)
        if not content: return []
        items = []
        for alias in self._SECTION_ALIASES[kind]:
            m = re.search(rf"##+\s*{re.escape(alias)}\s*\n(?P<body>.*?)(?:\n##|\Z)", content, re.S)
            if m: items.extend(self._extract_bullets_from_text(m.group("body")))
        return items

    def _extract_introductory_concepts(self, kp):
        content = self._combined_resource_text(kp)
        if not content: return []
        concepts = []
        for h in ("学习目标", "知识讲解", "核心概念"):
            m = re.search(rf"##+\s*{re.escape(h)}\s*\n(?P<body>.*?)(?:\n##|\Z)", content, re.S)
            if m:
                for line in m.group("body").splitlines():
                    concepts.extend(self._extract_phrases_from_line(line))
        return concepts[:8]

    def _extract_learning_objective_targets(self, kp):
        content = self._combined_resource_text(kp)
        if not content: return []
        m = re.search(r"##+\s*学习目标\s*\n(?P<body>.*?)(?:\n##|\Z)", content, re.S)
        if not m: return []
        labels = []
        for line in m.group("body").splitlines():
            if any(t in line for t in ("运用", "解释", "推导", "识别", "区分", "分析")):
                labels.extend(self._extract_phrases_from_line(line))
        return labels

    def _extract_extension_targets(self, kp):
        content = self._combined_resource_text(kp)
        if not content: return []
        items = []
        for h in self._EXTENSION_HEADINGS:
            m = re.search(rf"##+\s*{re.escape(h)}[^\n]*\n(?P<body>.*?)(?:\n##|\Z)", content, re.S)
            if m: items.extend(self._extract_bullets_from_text(m.group("body")))
        return items

    def _match_existing_points(self, kp, relation):
        ct = set(self._tokenize(kp))
        if not ct: return []
        with SessionLocal() as db:
            names = [str(r[0]) for r in db.query(KnowledgePoint.name).all() if str(r[0]).strip()]
        scored = []; kl = kp.lower()
        for c in names:
            if c == kp: continue
            ot = len(ct & set(self._tokenize(c)))
            if ot <= 0: continue
            s = ot * 10
            if relation == "recommended" and c.lower() > kl: s += 1
            scored.append((s, c))
        scored.sort(key=lambda x: (-x[0], len(x[1]), x[1]))
        return [x[1] for x in scored[:4]]

    def _resource_titles_from_sql(self, kp):
        return [t for r, _ in self._matching_resource_rows(kp, 4) if (t := self._extract_title_from_content(r.content))]

    def _combined_resource_text(self, kp):
        return "\n".join(r.content or "" for r, _ in self._matching_resource_rows(kp, 4))

    def _matching_resource_rows(self, kp, limit):
        with SessionLocal() as db:
            er = db.query(Resource, KnowledgePoint).outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id).filter(KnowledgePoint.name == kp).order_by(Resource.id.desc()).limit(limit).all()
            if er: return er
            return db.query(Resource, KnowledgePoint).outerjoin(KnowledgePoint, Resource.knowledge_point_id == KnowledgePoint.id).filter(Resource.content.contains(kp)).order_by(Resource.id.desc()).limit(limit).all()

    def _extract_bullets_from_text(self, text):
        return [p for line in text.splitlines() if line.strip() and line.strip()[0] in "-*12" for p in self._extract_phrases_from_line(line.strip())]

    def _merge_graphs(self, graphs):
        nb = {}; edges = []; ek = set()
        for g in graphs:
            for n in g.get("nodes", []):
                nid = str(n.get("id") or "").strip()
                if nid: nb[nid] = {"id": nid, "label": str(n.get("label") or nid), "category": str(n.get("category") or "resource")}
            for e in g.get("edges", []):
                src = str(e.get("source") or "").strip(); tgt = str(e.get("target") or "").strip(); lbl = str(e.get("label") or "").strip()
                if src and tgt:
                    key = (src, tgt, lbl)
                    if key not in ek: ek.add(key); edges.append({"source": src, "target": tgt, "label": lbl})
        return {"nodes": list(nb.values()), "edges": edges}

    def _unique_paths(self, paths):
        u = []; seen = set()
        for p in paths:
            rp = p.get("path")
            if not isinstance(rp, list): continue
            n = tuple(str(x).strip() for x in rp if str(x).strip())
            if len(n) >= 2 and n not in seen: seen.add(n); u.append({"path": list(n)})
        return u

    def _unique_resources(self, rs):
        u = []; seen = set()
        for r in rs:
            name = str(r.get("name") or r.get("title") or "").strip()
            uri = str(r.get("uri") or "").strip()
            if name and (name, uri) not in seen: seen.add((name, uri)); u.append({"name": name, "type": str(r.get("type") or r.get("kind") or "resource"), "uri": uri})
        return u

    def _unique_recommendations(self, items):
        u = []; seen = set()
        for r in items:
            name = str(r.get("name") or "").strip()
            if name and name not in seen: seen.add(name); u.append({"name": name, "difficulty": int(r.get("difficulty") or 1), "importance": int(r.get("importance") or 1)})
        return u

    def _normalize_labels(self, labels, limit=5):
        cleaned = [self._clean_text_label(i) for i in labels if isinstance(i, str) and i.strip()]
        cleaned = [i for i in cleaned if i]
        counts = Counter(cleaned)
        return sorted(counts, key=lambda i: (-counts[i], len(i), i))[:limit]

    def _finalize_labels(self, kp, labels, limit=5):
        n = self._normalize_labels(labels, limit * 3)
        res = []; nkp = self._clean_text_label(kp, 40)
        for l in n:
            if not l or l == nkp or "个性化课件" in l or "学习课件" in l: continue
            if l.startswith(("主题 ", "摘要 ", "阅读方式 ", "学习顺序 ")): continue
            res.append(l)
            if len(res) >= limit: break
        return res

    def _clean_text_label(self, value, max_len=18):
        l = re.sub(r"^[\-\*\d\.\s]+", "", value).strip()
        l = re.sub(r"[`#>\[\]\(\)（）]", " ", l)
        l = re.sub(r"[""\"''']", "", l)
        l = re.sub(r"\*\*|__|[:：；;，,。！？!?]", " ", l)
        l = re.sub(r"\s+", " ", l).strip()
        for t in ("你应该能够", "学完这节课后", "根据系统记录", "重点提醒", "这节课围绕", "当前掌握度约"):
            l = l.replace(t, "").strip()
        for p in ("主题 ", "摘要 ", "阅读方式 ", "学习顺序 ", "核心主题 "):
            if l.startswith(p): l = l[len(p):].strip()
        l = re.sub(r"^(以及|以及它和|以及它|以及|关于|其中|一个|一种)\s*", "", l).strip()
        l = re.sub(r"\s*(是什么|的内容|的关系|时运动状态的区别)$", "", l).strip()
        l = re.sub(r"\s+[（(][^)）]*[）)]$", "", l).strip()
        if l in self._STOP_LABELS or len(l) < 2: return ""
        return l[:max_len].strip() if len(l) > max_len else l

    def _short_concept_label(self, concept):
        text = re.sub(r"`([^`]+)`", r"\1", concept)
        text = text.split("：", 1)[0].split(":", 1)[0]
        for d in ("，", ",", "。", ".", "、", "；", ";", "——"):
            b = text.split(d, 1)[0]
            if len(b.strip()) >= 2: text = b
        text = text.strip("` ").strip()
        if len(text) > 6:
            for n in (2, 3):
                if n <= len(text):
                    s = text[:n]
                    if not any(c in s for c in "，、。的了一在是") and any("一" <= c <= "鿿" for c in s): return s
        return self._clean_text_label(text)

    def _line_to_label(self, line): return self._clean_text_label(re.sub(r"^\d+\.\s*", "", line.strip()))

    def _extract_phrases_from_line(self, line):
        s = line.strip()
        if not s: return []
        c = []
        c.extend(re.findall(r"\*\*(.+?)\*\*", s))
        c.extend(re.findall(r"[“「]([^”」]{2,20})[”」]", s))
        for t in ("理解", "掌握", "区分", "运用", "解释", "推导", "识别", "分析", "准确说出", "准确区分", "独立推导", "识别并避免"):
            if t in s: c.extend(self._split_labels(s.split(t, 1)[1]))
        if not c: c.append(s)
        cl = [self._line_to_label(i) for i in c]
        return [i for i in cl if i and i not in self._STOP_LABELS]

    def _extract_title_from_content(self, content):
        for line in (content or "").splitlines():
            if line.strip().startswith("# "): return line.strip()[2:].strip()
            if line.strip().startswith("## "): return line.strip()[3:].strip()
        return ""

    def _tokenize(self, text):
        if not text.strip(): return []
        cc = re.findall(r"[一-鿿]{2,}", text)
        lc = re.findall(r"[A-Za-z]{3,}", text.lower())
        tokens = list(lc)
        for chunk in cc:
            tokens.append(chunk)
            for size in range(2, min(4, len(chunk)) + 1):
                for start in range(len(chunk) - size + 1): tokens.append(chunk[start:start + size])
        return tokens

    def _split_labels(self, text):
        return [self._clean_text_label(i) for i in re.split(r"(?:、|，|,|；|;|和|与|以及|及其|及|/)\s*", text) if self._clean_text_label(i)]

    def _derive_topics_from_title(self, knowledge_point: str) -> list[str]:
        """Use LLM + web search to suggest graph nodes for an unknown topic."""
        return self._llm_suggest_nodes(knowledge_point)

    def _llm_suggest_nodes(self, knowledge_point: str) -> list[str]:
        """Use LLM + web search to suggest graph nodes."""
        try:
            import json as _json
            web_results = self.web_search.search(knowledge_point, max_results=3)
            web_text = " | ".join(web_results[:3]) if web_results else ""
            from langchain_core.messages import HumanMessage
            llm = self.llm_factory.build_chat_model(temperature=0.2)
            prompt = _GRAPH_LLM_PROMPT.replace("{kp}", knowledge_point).replace("{web}", web_text[:2000])
            raw = llm.invoke([HumanMessage(content=prompt)]).content
            if not isinstance(raw, str): return []
            cleaned = raw.strip()
            payload = _json.loads(cleaned)
            topics = list(payload.get("prereqs", [])) + list(payload.get("recs", []))
            return [str(t) for t in topics]
        except Exception as exc:
            logger.warning("LLM graph nodes failed for %s: %s", knowledge_point, exc)
            return []

    def _fallback_prerequisites(self, title: str) -> list[str]:
        return []

    # ------------------------------------------------------------------
    # Courseware -> graph synchronization
    # ------------------------------------------------------------------

    def sync_courseware_to_graph(self, knowledge_point: str) -> dict[str, Any]:
        prerequisites = self._derive_prerequisites(knowledge_point, None)
        recommendations = self._derive_recommendations(knowledge_point, None)
        result = {"knowledge_point": knowledge_point, "prerequisites_extracted": prerequisites, "recommendations_extracted": recommendations, "sql_knowledge_points_created": 0, "sql_relations_created": 0, "neo4j_relations_created": 0}
        if not prerequisites and not recommendations: return result
        with SessionLocal() as db:
            current_kp = self._get_or_create_sql_knowledge_point(db, knowledge_point)
            for pn in prerequisites:
                pk = self._get_or_create_sql_knowledge_point(db, pn)
                if self._create_sql_relation_if_absent(db, pk.id, current_kp.id, "DEPENDS_ON"): result["sql_relations_created"] += 1
            for rn in recommendations:
                rk = self._get_or_create_sql_knowledge_point(db, rn)
                if self._create_sql_relation_if_absent(db, current_kp.id, rk.id, "RECOMMENDS"): result["sql_relations_created"] += 1
            db.commit()
        nc = self._sync_relations_to_neo4j(knowledge_point, prerequisites, "DEPENDS_ON") + self._sync_relations_to_neo4j(knowledge_point, recommendations, "RECOMMENDS")
        result["neo4j_relations_created"] = nc
        logger.info("sync_courseware_to_graph: kp=%s prereq=%d rec=%d sql=%d neo4j=%d", knowledge_point, len(prerequisites), len(recommendations), result["sql_relations_created"], nc)
        return result

    def _get_or_create_sql_knowledge_point(self, db, name):
        existing = db.query(KnowledgePoint).filter(KnowledgePoint.name == name).first()
        if existing is not None: return existing
        kp = KnowledgePoint(name=name, description="", difficulty=2, importance=2)
        db.add(kp); db.flush(); return kp

    def _create_sql_relation_if_absent(self, db, from_id, to_id, relation_type):
        existing = db.query(KnowledgeRelation).filter(KnowledgeRelation.from_id == from_id, KnowledgeRelation.to_id == to_id, KnowledgeRelation.relation_type == relation_type).first()
        if existing is not None: return False
        db.add(KnowledgeRelation(from_id=from_id, to_id=to_id, relation_type=relation_type))
        return True

    def _sync_relations_to_neo4j(self, kp, targets, rtype):
        if self._driver is None: return 0
        count = 0
        try:
            with self._require_driver().session() as s:
                for t in targets:
                    q = """MERGE (kp:KnowledgePoint {name:$kp}) MERGE (target:KnowledgePoint {name:$t}) MERGE (kp)-[r:RELATION {type:$rtype}]->(target) SET r.label=$rtype"""
                    s.run(q, kp=kp, t=t, rtype=rtype); count += 1
        except Exception as exc:
            logger.warning("Neo4j sync failed for %s (%s): %s", kp, rtype, exc)
        return count
