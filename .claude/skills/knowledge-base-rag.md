---
name: knowledge-base-rag
description: 知识库和 RAG 系统说明 — 了解爬虫来源、ChromaDB 存储、标签系统、RAG 检索注入方式
model: haiku
---

# 知识库与 RAG 系统

## 架构概览

```
爬虫 (scripts/crawl_resources.py)
  → 本地文件夹 (crawled_content/*.md)
  → 标签分析智能体 (tag_analysis.py)
  → 数据库 resources 表 (tags JSON 列)
  → ChromaDB 索引 (scripts/index_resources.py)
  → RAG 检索 (rag.py: ChromaRetriever)
  → LLM prompt 注入 (exercise/resource/QA generation)
```

## 爬取内容

### 存储位置
`crawled_content/`（项目根目录），按学科分文件夹：

```
crawled_content/
├── python/       # Python 基础 (13 files)
├── c_lang/       # C 语言基础 (10 files)
├── java/         # Java 语言基础 (11 files)
├── cpp/          # C++ 基础 (10 files)
├── algorithms/   # 算法与数据结构 (7 files)
├── databases/    # 数据库 MySQL (6 files)
├── math/         # 数学 (3 files)
└── software_eng/ # 软件工程 (0 files, 待补充)
```

### 数据来源

| 来源 | URL | 覆盖内容 |
|---|---|---|
| **菜鸟教程** | `runoob.com` | Python/C/Java/C++ 数据类型、循环、条件、OOP、函数、IO、异常；算法排序；MySQL 查询/JOIN/索引/事务 |
| **维基教科书** | `zh.wikibooks.org` | 高等数学（微积分）、线性代数、概率论 |

所有内容均为 **CC BY-SA** 或 **公开教学资源**，爬取时已标注来源 URL 和爬取时间。

### 数据量

- 60 个 Markdown 文件，~422KB
- ChromaDB 索引后：~400+ chunks
- 标签覆盖：~50 种标签（学科/主题/难度/类型）

### 如何扩展

编辑 `scripts/crawl_resources.py` 的 `TARGETS` 列表，添加新的 `CrawlTarget(url, subject, topic, difficulty, tags)` 条目，然后运行：

```bash
python scripts/crawl_resources.py          # 爬取
python scripts/index_resources.py          # 索引
```

**建议补充的源**：
- GitHub 上的 CS-Notes 仓库（Markdown 格式，数百 MB）
- 中国大学 MOOC 课件（需要登录，较复杂）
- 百度百科/维基百科 API（结构化数据，可批量）
- 廖雪峰官网（Python/Java 教程，质量极高）

## 标签系统

### 标签分析智能体

`services/agent_service/app/services/tag_analysis.py` — `TagAnalysisService`

每个爬取的文档会自动分析并打上 3-6 个标签，格式：

```json
["Python", "循环结构", "while", "for", "基础", "概念讲解"]
```

标签维度：
- **学科/语言**：Python, Java, C语言, C++, 数学, 数据库, 算法, 数据结构
- **具体主题**：循环结构, 条件判断, OOP, 排序, SQL, 微积分
- **难度级别**：基础, 进阶
- **内容类型**：概念讲解, 代码示例

### 标签存储

数据库 `resources` 表 `tags` 列（JSON 类型），支持 PostgreSQL JSON 查询：

```sql
SELECT * FROM resources WHERE tags ? 'Python';
SELECT * FROM resources WHERE tags @> '["基础","循环结构"]';
```

## ChromaDB 向量数据库

### 配置

- 路径：`.env` 中的 `CHROMA_PERSIST_DIRECTORY`（默认 `./.chroma`）
- Collection：`education_resources`
- 嵌入模型：ChromaDB 内置（默认 all-MiniLM-L6-v2）

### 检索 API

`services/agent_service/app/services/rag.py` — `ChromaRetriever`

```python
from services.agent_service.app.services.rag import ChromaRetriever

r = ChromaRetriever()

# 基本检索
results = r.retrieve("Python while循环", top_k=3)

# 带 metadata 检索
results = r.retrieve_with_metadata("快速排序 分治", top_k=5)

# 按 tag 过滤检索
results = r.retrieve_by_tags(["Python", "基础"], "循环条件判断", top_k=5)

# 直接获取注入 prompt 的文本
context = r.retrieve_context_text("微积分 导数", top_k=3)
# 返回: "【参考学习资料】\n--- 参考 1: 微积分入门 ---\n..."
```

### 索引重建

```bash
python scripts/index_resources.py              # 全量索引
python scripts/index_resources.py --subject python  # 只索引 python
python scripts/index_resources.py --dry-run    # 预览
```

## RAG 注入点

当前已集成 RAG 的模块：

| 模块 | 文件 | 注入方式 |
|---|---|---|
| **练习题生成** | `exercise_generation.py` L118-130 | `{context_text}` 注入 LLM prompt |
| **课件生成** | `resource_generation.py` L578-631 | `{context_text}` + Chroma `retrieve()` |
| **智能问答** | `qa_service.py` | 通过 `KnowledgeBaseService` 关键词检索（待升级为 Chroma） |

待集成的模块：
- 学习路径（`learning_path.py`）
- 知识图谱（`graph.py`）
- 学习报告（`report_service.py`）
- 用户画像追问（`profile_builder.py`）

## 数据库表

`resources` 表（`common/models/learning.py` L87-107）：

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | 自增主键 |
| `title` | String(200) | 资源标题 |
| `type` | String(30) | courseware/exercise/notes/exam |
| `content` | Text | Markdown 内容或 JSON metadata |
| `format` | String(20) | markdown/pdf/html |
| `source_url` | Text | 爬取来源 URL |
| `local_path` | Text | 本地文件路径（相对于 crawled_content/） |
| `tags` | JSON | 标签数组 ["Python","循环","基础"] |
| `crawl_status` | String(20) | pending/succeeded/failed |
| `language` | String(10) | zh/en |
| `summary` | Text | 内容摘要 |
| `knowledge_point_id` | FK | 关联知识点 |
