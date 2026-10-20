"""Curated knowledge snippets used to ground courseware and exercise generation."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import ClassVar
from urllib.parse import quote_plus

from common.config import get_settings


@dataclass(frozen=True)
class ExternalResource:
    """One external learning entry for a knowledge article."""

    title: str
    provider: str
    url: str
    kind: str
    license: str
    notes: str


@dataclass(frozen=True)
class KnowledgeArticle:
    """One curated knowledge article for a learning topic."""

    title: str
    subject: str
    level: str
    summary: str
    concepts: list[str]
    syntax: list[str]
    examples: list[str]
    mistakes: list[str]
    applications: list[str]
    checks: list[str]
    aliases: tuple[str, ...] = ()
    external_resources: list[ExternalResource] = field(default_factory=list)


def _learning_links(topic: str) -> list[ExternalResource]:
    encoded = quote_plus(topic)
    return [
        ExternalResource(
            title=f"{topic} - 中国大学 MOOC 课程搜索",
            provider="中国大学 MOOC",
            url=f"https://www.icourse163.org/search.htm?search={encoded}",
            kind="mooc_course",
            license="external",
            notes="进入中国大学 MOOC，查找高校课程、章节视频和课程资料。",
        ),
        ExternalResource(
            title=f"{topic} - 哔哩哔哩教学视频",
            provider="哔哩哔哩",
            url=f"https://search.bilibili.com/all?keyword={encoded}",
            kind="video",
            license="external",
            notes="进入 B 站搜索讲解视频，适合快速补概念、看例题演示。",
        ),
        ExternalResource(
            title=f"{topic} - 菜鸟教程检索",
            provider="菜鸟教程",
            url=f"https://www.runoob.com/?s={encoded}",
            kind="interactive",
            license="external",
            notes="进入菜鸟教程搜索基础说明、代码示例和语法参考。",
        ),
    ]


class KnowledgeBaseService:
    """Provide curated topic knowledge and external learning entries."""

    _article_cache: ClassVar[dict[str, list[tuple[tuple[str, ...], KnowledgeArticle]]]] = {}
    _cache_lock: ClassVar[threading.Lock] = threading.Lock()
    _curated_subject_titles: ClassVar[dict[str, frozenset[str]]] = {
        "computer_networks": frozenset({"计算机网络"}),
        "data_structures": frozenset({"数据结构与算法"}),
        "algorithms": frozenset({"数据结构与算法"}),
        "computer_architecture": frozenset({"计算机组成原理"}),
        # 操作系统当前只有独立索引资料，不能把“计算机基础”专题混入。
        "operating_systems": frozenset(),
    }

    def __init__(self) -> None:
        version = get_settings().knowledge_base_version
        with self._cache_lock:
            articles = self._article_cache.get(version)
            if articles is None:
                articles = self._build_articles()
                self._article_cache[version] = articles
        self._articles = articles

    def get_article(self, knowledge_point: str) -> KnowledgeArticle | None:
        """Return a curated article for a knowledge point if one exists."""

        query_tokens = set(self._extract_keywords(knowledge_point))
        if not query_tokens:
            return None

        for keywords, article in self._articles:
            if query_tokens.intersection(keywords):
                return article
        return None

    def list_articles(self, subject: str | None = None) -> list[KnowledgeArticle]:
        """Return curated articles, optionally filtered by subject."""

        articles = [article for _, article in self._articles]
        if subject:
            return [article for article in articles if self._matches_subject(article, subject)]
        return articles

    @classmethod
    def _matches_subject(cls, article: KnowledgeArticle, subject: str) -> bool:
        normalized = subject.strip().lower().replace("-", "_").replace(" ", "_")
        mapped_titles = cls._curated_subject_titles.get(normalized)
        if mapped_titles is not None:
            return article.title in mapped_titles
        return article.subject.casefold() == subject.strip().casefold()

    def article_to_dict(self, article: KnowledgeArticle) -> dict[str, object]:
        """Convert a KnowledgeArticle to a dictionary consumed by the frontend."""

        return {
            "id": self._slugify(article.title),
            "title": article.title,
            "subject": article.subject,
            "level": article.level,
            "summary": article.summary,
            "concepts": article.concepts,
            "syntax": article.syntax,
            "examples": article.examples,
            "mistakes": article.mistakes,
            "applications": article.applications,
            "checks": article.checks,
            "external_resources": [resource.__dict__ for resource in article.external_resources],
        }

    def search(self, question: str, subject: str | None = None, top_k: int = 3) -> list[KnowledgeArticle]:
        """Search for articles relevant to a question."""

        query_tokens = set(self._extract_keywords(question))
        articles = self.list_articles(subject)
        if not query_tokens:
            return articles[:top_k]

        scored: list[tuple[int, KnowledgeArticle]] = []
        normalized_question = question.lower()
        for article in articles:
            haystack = " ".join(
                [
                    article.title,
                    article.subject,
                    article.summary,
                    *article.concepts,
                    *article.syntax,
                    *article.aliases,
                ]
            ).lower()
            score = sum(1 for token in query_tokens if token in haystack)
            # Chinese questions often have no spaces. Match curated topic names
            # inside a full sentence instead of treating the sentence as one token.
            score += sum(
                1 for term in (*article.aliases, *article.concepts, article.title)
                if len(term.strip()) >= 2 and term.lower() in normalized_question
            )
            if score:
                scored.append((score, article))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [article for _, article in scored[:top_k]]

    def search_by_keywords(
        self,
        question: str,
        top_k: int = 3,
        subject: str | None = None,
    ) -> list[KnowledgeArticle]:
        """Search articles with keyword matching."""

        return self.search(question, subject=subject, top_k=top_k)

    def search_indexed(
        self,
        question: str,
        top_k: int = 3,
        *,
        filters: dict[str, object] | None = None,
        retrieval_mode: str = "hybrid",
    ) -> list[dict[str, object]]:
        """Search the crawled Chroma corpus and adapt chunks for the existing UI."""

        from services.agent_service.app.services.rag import ChromaRetriever

        retriever = ChromaRetriever()
        if not retriever.is_available or not question.strip():
            return []
        rows = retriever.retrieve_with_metadata(
            question,
            top_k=max(top_k, min(40, top_k * 4)),
            filters=filters,
            retrieval_mode=retrieval_mode,
        )
        subject_labels = {
            "python": "Python",
            "algorithms": "算法与数据结构",
            "data_structures": "数据结构",
            "databases": "数据库",
            "software_eng": "软件工程",
            "math": "数学基础",
            "java": "Java",
            "cpp": "C++",
            "c_lang": "C语言",
            "computer_networks": "计算机网络",
            "computer_architecture": "计算机组成原理",
            "operating_systems": "操作系统",
        }
        items: list[dict[str, object]] = []
        seen_sources: set[str] = set()
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            source_id = str(metadata.get("source_id") or row.get("id") or "")
            if not source_id or source_id in seen_sources:
                continue
            seen_sources.add(source_id)
            content = str(row.get("content") or "")
            title = str(metadata.get("title") or metadata.get("chapter") or "知识库资料")
            compact = re.sub(r"^\s*(?:#|>|---).*?$", " ", content, flags=re.MULTILINE)
            compact = re.sub(r"\s+", " ", compact).strip()
            tags_raw = metadata.get("tags", "[]")
            try:
                tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
            except (json.JSONDecodeError, TypeError):
                tags = []
            tags = [str(tag) for tag in tags] if isinstance(tags, list) else []
            source_url = str(metadata.get("source_url") or "")
            source_match = re.search(r"^>\s*来源:\s*(https?://\S+)", content, flags=re.MULTILINE)
            if not source_url and source_match:
                source_url = source_match.group(1)
            external_resources: list[dict[str, str]] = []
            if source_url:
                external_resources.append({
                    "title": f"{title} - 原始资料",
                    "provider": str(metadata.get("source") or "知识库来源"),
                    "url": source_url,
                    "kind": "reference",
                    "license": "external",
                    "notes": "查看该知识分块对应的原始公开资料。",
                })
            items.append({
                "id": f"indexed-{source_id}",
                "title": title,
                "subject": subject_labels.get(str(metadata.get("subject") or ""), str(metadata.get("subject") or "其他")),
                "level": "进阶" if "进阶" in tags else "基础",
                "summary": compact[:360] or title,
                "concepts": tags[:10],
                "syntax": [],
                "examples": [],
                "mistakes": [],
                "applications": [],
                "checks": [],
                "external_resources": external_resources,
                "retrieval_strategy": row.get("retrieval_strategy", "vector"),
                "source": metadata.get("source", ""),
                "source_url": source_url,
                "university": metadata.get("university", ""),
                "course": metadata.get("course", ""),
                "difficulty": metadata.get("difficulty", ""),
                "license": metadata.get("license", ""),
            })
            if len(items) >= top_k:
                break
        return items

    def get_indexed_article(self, article_id: str) -> dict[str, object] | None:
        """Return one indexed source assembled from its ordered chunks."""

        from services.agent_service.app.services.rag import ChromaRetriever

        source_id = article_id.removeprefix("indexed-")
        retriever = ChromaRetriever()
        if retriever.collection is None or not source_id:
            return None
        payload = retriever.collection.get(
            where={"source_id": {"$eq": source_id}},
            include=["documents", "metadatas"],
        )
        documents = payload.get("documents", []) or []
        metadatas = payload.get("metadatas", []) or []
        if not documents:
            return None
        ordered = sorted(
            zip(documents, metadatas, strict=False),
            key=lambda item: int((item[1] or {}).get("chunk_index", 0)),
        )
        from services.agent_service.app.services.knowledge_publication import visible_chunks
        visible = visible_chunks([{"content": content, "metadata": metadata} for content, metadata in ordered])
        if not visible:
            return None
        ordered = [(row["content"], row["metadata"]) for row in visible]
        metadata = ordered[0][1] if isinstance(ordered[0][1], dict) else {}
        content = "\n\n".join(str(item[0]) for item in ordered)
        tags_raw = metadata.get("tags", "[]")
        try:
            tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
        except (json.JSONDecodeError, TypeError):
            tags = []
        tags = [str(tag) for tag in tags] if isinstance(tags, list) else []
        title = str(metadata.get("title") or "知识库资料")
        source_url = str(metadata.get("source_url") or "")
        return {
            "id": f"indexed-{source_id}",
            "title": title,
            "subject": str(metadata.get("subject") or "其他"),
            "level": str(metadata.get("difficulty") or ("进阶" if "进阶" in tags else "基础")),
            "summary": re.sub(r"\s+", " ", content).strip()[:500],
            "content": content,
            "concepts": tags[:12],
            "syntax": [],
            "examples": [],
            "mistakes": [],
            "applications": [],
            "checks": [],
            "external_resources": ([{
                "title": f"{title} - 原始资料",
                "provider": str(metadata.get("source_site") or metadata.get("source") or "知识库来源"),
                "url": source_url,
                "kind": "reference",
                "license": str(metadata.get("license") or "source-terms"),
                "notes": "查看原始公开资料及其授权条款。",
            }] if source_url else []),
            "source": metadata.get("source", ""),
            "source_url": source_url,
            "university": metadata.get("university", ""),
            "course": metadata.get("course", ""),
            "license": metadata.get("license", ""),
        }

    def list_subjects(self) -> list[str]:
        """Return available knowledge subjects."""

        return sorted({article.subject for _, article in self._articles})

    def _build_articles(self) -> list[tuple[tuple[str, ...], KnowledgeArticle]]:
        articles = [
            KnowledgeArticle(
                title="计算机组成原理",
                subject="计算机基础",
                level="大学基础",
                summary="围绕 CPU、存储器、指令系统、总线和输入输出系统理解计算机如何执行程序，是学习操作系统、体系结构和嵌入式开发的基础。",
                concepts=["冯诺依曼结构", "CPU", "寄存器", "指令周期", "存储层次", "总线", "I/O 系统"],
                syntax=["取指 -> 译码 -> 执行 -> 写回", "地址总线 / 数据总线 / 控制总线", "Cache 命中率与访存时间"],
                examples=["分析一条加法指令从内存取出到执行完成的全过程", "比较寄存器、Cache、内存和磁盘的速度与容量差异"],
                mistakes=["把 CPU 等同于整台主机", "混淆内存地址和指令内容", "只记部件名称但说不清数据流向"],
                applications=["性能优化", "嵌入式系统", "操作系统内存管理", "计算机体系结构课程"],
                checks=["说明指令周期四个阶段", "解释 Cache 为什么能提升性能", "画出 CPU、内存、总线之间的数据流"],
                aliases=("CPU", "寄存器", "总线", "存储器", "指令", "cache"),
                external_resources=_learning_links("计算机组成原理"),
            ),
            KnowledgeArticle(
                title="计算机网络",
                subject="计算机基础",
                level="大学基础",
                summary="从分层模型、IP 地址、TCP/UDP、HTTP 和路由转发理解网络通信过程，适合支撑 Web 开发、后端接口和网络安全学习。",
                concepts=["OSI 七层模型", "TCP/IP", "IP 地址", "子网掩码", "TCP 三次握手", "HTTP", "DNS"],
                syntax=["HTTP 请求行 + 请求头 + 请求体", "TCP SYN / SYN-ACK / ACK", "IP + Port 定位网络进程"],
                examples=["浏览器访问网页时 DNS、TCP、HTTP 的完整链路", "比较 TCP 和 UDP 的可靠性与实时性"],
                mistakes=["把 HTTP 和 TCP 混为一谈", "忽视端口号作用", "不理解 DNS 与 IP 的关系"],
                applications=["Web 后端开发", "接口调试", "网络故障排查", "网络安全入门"],
                checks=["解释三次握手为什么需要三步", "说明输入网址后发生了什么", "区分 TCP 和 UDP 的适用场景"],
                aliases=("TCP", "UDP", "HTTP", "DNS", "IP", "网络协议"),
                external_resources=_learning_links("计算机网络"),
            ),
            KnowledgeArticle(
                title="数据结构与算法",
                subject="程序设计",
                level="大学核心",
                summary="系统学习线性表、栈、队列、树、图、排序、查找和复杂度分析，提升程序设计能力和问题抽象能力。",
                concepts=["时间复杂度", "数组", "链表", "栈", "队列", "二叉树", "图", "排序算法"],
                syntax=["O(1)、O(log n)、O(n)、O(n log n)", "递归终止条件 + 递推关系", "DFS / BFS"],
                examples=["用栈判断括号匹配", "用 BFS 求无权图最短路径", "比较快排和归并排序"],
                mistakes=["只会背复杂度不会分析循环", "递归没有终止条件", "混淆树和图的遍历方式"],
                applications=["算法竞赛", "后端性能优化", "数据库索引理解", "面试题训练"],
                checks=["分析两层循环复杂度", "写出二叉树前序遍历", "说明快排最坏情况"],
                aliases=("算法", "链表", "二叉树", "排序", "递归", "动态规划"),
                external_resources=_learning_links("数据结构与算法"),
            ),
            KnowledgeArticle(
                title="Python 程序设计",
                subject="程序设计",
                level="入门到进阶",
                summary="覆盖 Python 基础语法、函数、模块、文件、异常和面向对象，适合快速完成数据处理、脚本开发和 AI 应用原型。",
                concepts=["变量", "列表", "字典", "函数", "模块", "文件操作", "异常处理", "类与对象"],
                syntax=["def function(args):", "for item in iterable:", "with open(path) as f:", "class Student:"],
                examples=["读取文本文件并统计词频", "用字典保存学生成绩", "封装一个简单的用户类"],
                mistakes=["缩进错误", "可变默认参数误用", "混淆列表和元组", "异常捕获过宽"],
                applications=["自动化脚本", "数据分析", "Web API", "机器学习实验"],
                checks=["解释列表和字典的区别", "写一个带返回值的函数", "说明 with open 的好处"],
                aliases=("Python", "函数", "列表", "字典", "面向对象", "文件操作"),
                external_resources=_learning_links("Python 程序设计"),
            ),
            KnowledgeArticle(
                title="Java 面向对象程序设计",
                subject="程序设计",
                level="大学核心",
                summary="围绕类、对象、封装、继承、多态、接口和异常机制，建立大型软件开发所需的面向对象思维。",
                concepts=["类", "对象", "封装", "继承", "多态", "接口", "抽象类", "异常"],
                syntax=["class User { }", "extends", "implements", "try-catch-finally", "public / private"],
                examples=["设计用户、教师、学生类", "用接口抽象不同支付方式", "使用异常处理文件读取失败"],
                mistakes=["把类和对象混为一谈", "滥用继承", "接口只会写不会解释作用", "忽视访问控制"],
                applications=["企业后端", "Android 开发", "大型系统建模", "Spring Boot 学习"],
                checks=["解释重载和重写区别", "说明接口和抽象类差异", "设计一个简单继承结构"],
                aliases=("Java", "面向对象", "继承", "多态", "接口", "异常"),
                external_resources=_learning_links("Java 面向对象程序设计"),
            ),
            KnowledgeArticle(
                title="数据库系统与 SQL",
                subject="数据库",
                level="大学核心",
                summary="学习关系模型、SQL 查询、连接、索引、事务和并发控制，是后端开发和数据管理的基础能力。",
                concepts=["关系模型", "主键", "外键", "SELECT", "JOIN", "索引", "事务", "ACID"],
                syntax=["SELECT ... FROM ... WHERE ...", "INNER JOIN / LEFT JOIN", "GROUP BY", "BEGIN / COMMIT / ROLLBACK"],
                examples=["查询每个班级的平均成绩", "用 JOIN 查询用户和订单", "给高频查询字段建立索引"],
                mistakes=["WHERE 和 HAVING 混用", "JOIN 条件缺失导致笛卡尔积", "认为索引越多越好", "忽略事务一致性"],
                applications=["后端业务系统", "报表分析", "数据建模", "性能优化"],
                checks=["写出三表连接查询", "解释索引为什么能加速", "说明事务 ACID 含义"],
                aliases=("SQL", "数据库", "事务", "索引", "JOIN", "MySQL"),
                external_resources=_learning_links("数据库系统 SQL"),
            ),
            KnowledgeArticle(
                title="高等数学微积分",
                subject="数学基础",
                level="大学基础",
                summary="以极限、导数、积分和级数为主线，支撑机器学习、物理建模、优化算法和工程计算。",
                concepts=["极限", "连续", "导数", "微分", "不定积分", "定积分", "级数"],
                syntax=["lim f(x)", "f'(x)", "∫ f(x) dx", "牛顿-莱布尼茨公式"],
                examples=["用导数判断函数单调性", "用定积分计算面积", "用极限理解瞬时变化率"],
                mistakes=["把导数只理解成公式运算", "忽略积分上下限含义", "极限计算不检查条件"],
                applications=["机器学习优化", "物理建模", "工程计算", "概率统计基础"],
                checks=["解释导数的几何意义", "计算简单定积分", "说明连续和可导的关系"],
                aliases=("微积分", "高数", "导数", "积分", "极限", "定积分"),
                external_resources=_learning_links("高等数学 微积分"),
            ),
            KnowledgeArticle(
                title="线性代数",
                subject="数学基础",
                level="大学基础",
                summary="围绕矩阵、向量空间、线性方程组、特征值和特征向量建立多维数据表达能力，是人工智能和图形学的重要基础。",
                concepts=["矩阵", "向量", "行列式", "秩", "线性方程组", "特征值", "特征向量"],
                syntax=["Ax=b", "det(A)", "rank(A)", "Av=λv"],
                examples=["用矩阵表示线性变换", "求解线性方程组", "用特征值理解主成分方向"],
                mistakes=["矩阵乘法顺序写反", "混淆秩和维数", "只会计算不会解释线性变换"],
                applications=["机器学习", "图像处理", "推荐系统", "计算机图形学"],
                checks=["说明矩阵乘法条件", "解释特征向量含义", "判断方程组是否有唯一解"],
                aliases=("矩阵", "向量", "线代", "特征值", "特征向量", "行列式"),
                external_resources=_learning_links("线性代数"),
            ),
        ]
        return [(self._article_keywords(article), article) for article in articles]

    def _article_keywords(self, article: KnowledgeArticle) -> tuple[str, ...]:
        tokens = [
            article.title,
            article.subject,
            *article.concepts,
            *article.syntax,
            *article.aliases,
        ]
        keywords: set[str] = set()
        for token in tokens:
            keywords.update(self._extract_keywords(token))
        return tuple(sorted(keywords))

    def _slugify(self, text: str) -> str:
        return re.sub(r"[\s：、，,]+", "-", text.strip().lower()).strip("-")

    def _extract_keywords(self, question: str) -> list[str]:
        tokens = [
            token.strip().lower()
            for token in re.split(r"[\s，。！？,!.?；;：:、（）()\-/]+", question)
            if token.strip()
        ]
        return [token for token in tokens if len(token) >= 2]
