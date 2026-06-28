# 基于大模型的个性化资源生成与学习多智能体系统 — 功能与架构文档

> **技术栈**: Python 3.11 + FastAPI + Vue 3 + PostgreSQL + Neo4j + ChromaDB + RabbitMQ + Redis + MinIO + Docker

---

## 目录

1. [系统概览](#1-系统概览)
2. [基础设施架构](#2-基础设施架构)
3. [微服务架构](#3-微服务架构)
4. [数据库模型设计](#4-数据库模型设计)
5. [多智能体协作系统](#5-多智能体协作系统)
6. [个性化学习画像系统](#6-个性化学习画像系统)
7. [知识图谱系统](#7-知识图谱系统)
8. [知识库与 RAG 系统](#8-知识库与-rag-系统)
9. [课件生成系统](#9-课件生成系统)
10. [习题生成系统](#10-习题生成系统)
11. [智能问答系统](#11-智能问答系统)
12. [学习路径规划](#12-学习路径规划)
13. [聊天对话系统](#13-聊天对话系统)
14. [反馈联合智能体](#14-反馈联合智能体)
15. [教师工作台](#15-教师工作台)
16. [前端页面架构](#16-前端页面架构)
17. [API 路由总览](#17-api-路由总览)
18. [数据流转图](#18-数据流转图)
19. [环境配置说明](#19-环境配置说明)
20. [设计说明文档](#20-设计说明文档)

## 1. 系统概览

### 1.1 项目目标

构建一个**基于大语言模型的多智能体协作式个性化学习系统**，能够根据学习者画像自动生成个性化的学习资源（课件、习题、学习路径），并通过知识图谱、向量检索和智能问答提供全方位学习支持。

### 1.2 核心能力

- 🎯 **多智能体协作**：8 个专业智能体通过 LangGraph 编排协同工作
- 👤 **四维学习画像**：知识掌握度 + 学习风格 + 认知能力 + 学习习惯
- 📚 **个性化课件生成**：基于画像生成 concise/case/interactive 三种风格课件
- 📝 **智能习题生成**：5 种题型，3 种难度，支持真实错题驱动的变式训练
- 🔗 **知识图谱可视化**：Neo4j + PostgreSQL 双存储，自动从课件提取节点和关系
- 🔍 **RAG 向量检索**：ChromaDB 存储 400+ chunks，标签系统 50+ 标签
- 💬 **智能问答**：大/小模型协作，支持学习分析和追问
- 📊 **反馈联合智能体**：LLM 跨智能体综合分析 + 评估数据融合
- 🏫 **教师工作台**：教学范围划定、课件发布、学情监控
- 🗄️ **多库协同**：PostgreSQL(业务数据) + Neo4j(知识图谱) + ChromaDB(向量) + Redis(缓存) + RabbitMQ(消息) + MinIO(文件)

---

## 2. 基础设施架构

### 2.1 Docker Compose 服务栈

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `postgres` | postgres:16 | 5432 | 主业务数据库（用户、资源、习题等） |
| `redis` | redis:7.2 | 6379 | 缓存与会话 |
| `rabbitmq` | rabbitmq:3.13-management | 5672/15672 | 消息队列（智能体任务分发） |
| `neo4j` | neo4j:5 | 7474/7687 | 图数据库（知识图谱） |
| `minio` | minio/minio:latest | 9000/9001 | 对象存储（课件文件） |
| `elasticsearch` | elasticsearch:8.15.0 | 9200 | 全文搜索 |
| `chroma` | chromadb/chroma:0.5.5 | 8010 | 向量数据库（RAG） |
| `user-service` | python:3.11-slim | 8001 | 用户认证与画像 |
| `agent-service` | python:3.11-slim | 8002 | 多智能体编排 |
| `resource-service` | python:3.11-slim | 8003 | 资源管理 |
| `evaluation-service` | python:3.11-slim | 8004 | 评估与报告 |
| `teacher-service` | python:3.11-slim | 8005 | 教师功能 |
| `system-service` | python:3.11-slim | 8006 | 系统管理 |
| `nginx` | nginx:1.27-alpine | 80 | 反向代理 |

### 2.2 LLM 配置

支持三种 LLM 后端（优先级递减）：

1. **DeepSeek** — `DEEPSEEK_API_BASE` + `DEEPSEEK_API_KEY`
2. **Qwen（通义千问）** — `QWEN_API_BASE` + `QWEN_API_KEY`
3. **OpenAI** — `OPENAI_API_KEY` + `OPENAI_BASE_URL`

通过 `LLMFactory.build_chat_model()` 自动选择可用后端，使用 LangChain 的 `ChatOpenAI` 统一调用。

---

## 3. 微服务架构

### 3.1 服务划分

```
┌─────────────────────────────────────────────────────────────┐
│                     Nginx (Port 80)                          │
│              反向代理 + API 路由分发                           │
├──────┬──────┬──────┬──────┬──────┬──────┬──────────────────┤
│User  │Agent │Res   │Eval  │Teach │Sys   │  Frontend         │
│8001  │8002  │8003  │8004  │8005  │8006  │  Vite :5175       │
└──────┴──────┴──────┴──────┴──────┴──────┴──────────────────┘
         │       │       │       │       │
         └───────┴───────┴───────┴───────┘
                      │
         ┌────────────┼────────────┐
         │            │            │
    PostgreSQL    Neo4j      ChromaDB
    (业务数据)   (知识图谱)  (向量检索)
```

### 3.2 Agent Service（核心服务）

**端口**: 8002  
**核心入口**: `CoordinatorWorkflow` — 基于 LangGraph 的智能体编排引擎

**8 个专业智能体**：

| 智能体 | 英文标识 | 功能说明 |
|--------|----------|----------|
| 画像分析智能体 | `learner_profiling_agent` | 从数据库加载真实作答记录，计算掌握度、正确率、薄弱题型 |
| 知识图谱智能体 | `knowledge_graph_agent` | Neo4j 图查询 + 课件同步 + 可视化数据生成 |
| 知识库智能体 | `knowledge_base_agent` | 知识库文章列表、搜索、详情查询 |
| 路径规划智能体 | `path_planning_agent` | 生成 3-4 天的分阶段学习路径 |
| 资源生成智能体 | `resource_generation_agent` | 基于 RAG + 画像 + 知识库生成个性化课件 |
| 习题生成智能体 | `exercise_generation_agent` | 生成 5-10 道结构化练习题 |
| 答疑智能体 | `qa_agent` | 学习分析 + 知识缺口识别 + 推荐下一步 |
| 评估反馈智能体 | `evaluation_feedback_agent` | LLM 跨智能体综合分析 + 评估数据融合 |

**协作模式**：
- **强制智能体列表**：前端指定 `force_agents` 参数，精确控制参与协作的智能体
- **意图匹配**：根据中文/英文关键词自动选择智能体组合
- **全系统协作**：关键词触发全部 8 个智能体协同

---

## 4. 数据库模型设计

### 4.1 PostgreSQL 核心表（`common/models/learning.py`）

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `users` | 用户账户 | id, username, password_hash, role(student/teacher/admin), email |
| `user_profiles` | 四维学习画像 | user_id(FK), mastery_json, learning_style, cognitive_abilities, habits, profile_analysis |
| `knowledge_points` | 知识点元数据 | id, name, description, difficulty(1-3), importance(1-3) |
| `knowledge_relations` | 知识点有向关系 | from_id(FK), to_id(FK), relation_type(DEPENDS_ON/RECOMMENDS) |
| `resources` | 学习资源 | id, title, type, content(Markdown/JSON), format, knowledge_point_id(FK), tags(JSON), crawl_status |
| `exercises` | 习题 | id, knowledge_point_id(FK), type, difficulty, content(JSON), answer, analysis |
| `answer_records` | 作答记录 | user_id(FK), exercise_id(FK), user_answer, is_correct, time_spent |
| `learning_paths` | 学习路径 | user_id(FK), path_data_json, status(active/archived) |
| `learning_tasks` | 路径内任务 | path_id(FK), task_type, resource_ids(JSON), completed |
| `learning_reports` | 学习报告 | user_id(FK), report_type, content_json |
| `teaching_scopes` | 教师划定范围 | class_id, student_user_id(FK), knowledge_points(JSON), courseware_content |
| `profile_conversations` | 画像构建对话 | user_id(FK), role, content |
| `chat_sessions` | 聊天会话 | user_id(FK), title, subject, is_active, last_message_at |
| `chat_messages` | 聊天消息 | session_id(FK), role, content, model_used(small_model/large_model) |

### 4.2 Neo4j 图模型

```
(KnowledgePoint {name, description, difficulty, importance})
  -[:DEPENDS_ON]-> (KnowledgePoint)   // 前置知识依赖
  -[:RECOMMENDS]-> (KnowledgePoint)   // 后续学习推荐
  -[:ASSOCIATED_WITH]-> (Resource)    // 关联资源
```

### 4.3 ChromaDB 向量库

- Collection: `education_resources`
- 嵌入模型: `all-MiniLM-L6-v2`（默认）
- 数据来源: 60 个爬取 Markdown 文件，~400+ chunks

---

## 5. 多智能体协作系统

### 5.1 编排流程（CoordinatorWorkflow）

```
用户请求 → analyze_intent → dispatch_tasks → resolve_conflicts → 执行智能体
```

**状态机节点**（LangGraph StateGraph）：

1. **`analyze_intent`** — 根据 `intent` 和 `force_agents` 选择智能体列表
2. **`dispatch_tasks`** — 向 RabbitMQ 发布异步任务消息
3. **`resolve_conflicts`** — 解决智能体间排序冲突
4. **同步执行阶段**（`payload.execute = True`）：
   - 画像分析 → 知识图谱 → 知识库 → 学习路径 → 课件生成 → 习题生成 → 答疑 → 评估反馈

### 5.2 Agent 间上下文共享

通过 `agent_handoff` 机制在各智能体间传递上下文：

```json
{
  "learner_profiling_agent": ["画像摘要"],
  "resource_generation_agent": ["个性化提示"],
  "exercise_generation_agent": ["薄弱题型"],
  "qa_agent": ["回答问题建议"]
}
```

---

## 6. 个性化学习画像系统

### 6.1 画像构建（ProfileBuilder）

**服务**: `user_service/app/services/profile_builder.py`  
**路由**: `POST /users/{user_id}/profile/build`

**构建流程**：
1. LLM 根据学生回答生成追问问题
2. 多轮对话收集：已知背景 → 兴趣方向 → 学习目标 → 薄弱点 → 学习速度
3. 结构化提取为 `profile_dimensions` 六维画像
4. 存入 `user_profiles.habits` JSON 字段

**六维画像维度**：

| 维度 | 英文键 | 说明 |
|------|--------|------|
| 知识基础 | knowledgeBase | 已有知识储备 |
| 认知风格 | cognitiveStyle | 抽象/具体思维偏好 |
| 错误偏好 | errorPreference | 常犯错误模式 |
| 学习速度 | learningPace | 快/中/慢 |
| 兴趣方向 | interestDirection | 偏好的学习主题 |
| 目标导向 | goalOrientation | 考试/项目/兴趣驱动 |

### 6.2 画像快照（PersonalizationService）

**服务**: `agent_service/app/services/personalization.py`

从 `user_profiles` + `answer_records` + `exercises` 构建实时画像快照：

```
LearnerPersonalizationSnapshot:
  - mastery_score: int          # 掌握度 0-100
  - correct_rate: int           # 近期正确率 %
  - answered_count: int         # 作答次数
  - weak_question_types: list   # 薄弱题型排行
  - recent_mistakes: list       # 最近 5 道错题详情
  - learner_profile: dict       # 完整四维画像
```

**掌握度计算逻辑**：
1. 优先使用 `user_profiles.mastery_json` 中的显式掌握度
2. 若无显式数据，根据作答正确率、答题耗时、题目难度综合估算
3. 零作答记录返回 0

---

## 7. 知识图谱系统

### 7.1 图谱仓储（KnowledgeGraphRepository）

**路由**（`agent_service`）：
- `POST /graph/dependencies` — 依赖路径查询
- `GET /graph/related-resources/{kp}` — 关联资源
- `POST /graph/visualization` — 可视化图谱数据

### 7.2 课件→图谱同步

`sync_courseware_to_graph(knowledge_point)` 从课件 Markdown 内容中提取：

- **前置依赖**：从"前置知识/前置基础/预备知识"段落提取 ➜ `DEPENDS_ON`
- **后续推荐**：从"拓展延伸/进阶内容/延伸学习"段落提取 ➜ `RECOMMENDS`
- **关联资源**：从数据库 `resources` 表匹配

提取流程：
1. 知识库文章概念提取
2. 课件 Markdown section 解析（正则匹配 `## section_name`）
3. SQL 相似知识点匹配（token overlap 算法）
4. LLM + WebSearch 兜底（对未知主题用大模型建议节点）

同步目标：
- **PostgreSQL**: `knowledge_points` + `knowledge_relations` 表
- **Neo4j**: `KnowledgePoint` 节点 + `DEPENDS_ON`/`RECOMMENDS` 关系

---

## 8. 知识库与 RAG 系统

### 8.1 爬取内容

**脚本**: `scripts/crawl_resources.py`, `scripts/index_resources.py`

| 学科文件夹 | 文件数 | 来源 |
|-----------|--------|------|
| `python/` | 13 | 菜鸟教程 |
| `c_lang/` | 10 | 菜鸟教程 |
| `java/` | 11 | 菜鸟教程 |
| `cpp/` | 10 | 菜鸟教程 |
| `algorithms/` | 7 | 菜鸟教程 |
| `databases/` | 6 | 菜鸟教程 |
| `math/` | 3 | 维基教科书 |

共计 60 个 Markdown 文件，~422KB。

### 8.2 标签系统

`TagAnalysisService` 自动为每个文档打 3-6 个标签：

```
["Python", "循环结构", "while", "for", "基础", "概念讲解"]
```

标签维度：
- 学科/语言：Python, Java, C, C++, 数学, 数据库, 算法
- 具体主题：循环结构, 条件判断, OOP, 排序, SQL, 微积分
- 难度级别：基础, 进阶
- 内容类型：概念讲解, 代码示例

存储于 `resources.tags`（JSON 列），支持 PostgreSQL JSON 查询。

### 8.3 ChromaDB 检索（ChromaRetriever）

**Collection**: `education_resources`  
**默认嵌入模型**: all-MiniLM-L6-v2

```python
retriever.retrieve("Python while循环", top_k=3)
retriever.retrieve_with_metadata("快速排序 分治", top_k=5)
retriever.retrieve_by_tags(["Python", "基础"], "循环条件判断", top_k=5)
retriever.retrieve_context_text("微积分 导数", top_k=3)  # 返回格式化文本
```

### 8.4 RAG 注入点

| 模块 | 注入位置 | 方式 |
|------|----------|------|
| 课件生成 | `resource_generation.py` L565-569 | ChromaRetriever.retrieve() → `context_text` 注入 LLM prompt |
| 习题生成 | `exercise_generation.py` L132-137 | ChromaRetriever.retrieve_context_text() → `context_text` 注入 prompt |

---

## 9. 课件生成系统

### 9.1 入口

**API**: `POST /resources/generate` （agent-service）  
**服务**: `ResourceGenerationService` — `generate_courseware_with_plan()`

### 9.2 生成流程

```
请求解析 → 画像快照 → RAG检索 → 知识库底稿 → 生成计划 → LLM 多风格变体 → 审核→落库
```

#### 阶段 1：生成计划（GenerationPlan）

从请求 + 画像推导：
- `knowledge_point` — 知识点名称
- `resource_type` — courseware/exercise/notes/exam（智能推断）
- `resource_style` — concise/case/interactive
- `difficulty` — foundation/intermediate/advanced（基于掌握度）
- `target_word_count` — 300–6000（默认根据类型和难度）
- `suggested_outline` — 6 段大纲
- `personalization_hints` — 最多 4 条个性化提示

#### 阶段 2：RAG + 知识库增强

1. **ChromaDB 检索** — 取 top-k（默认2）相似文档片段
2. **知识库底稿** — 获取知识点文章的核心概念、语法、示例、易错点
3. **画像整合** — 掌握度、正确率、薄弱题型、近期错题

#### 阶段 3：LLM 生成多风格变体

为每个 `resource_style` 变体构建独立 prompt，注入个性化和审核驳回原因：

```
style 变体数量 = max(1, RESOURCE_COURSEWARE_VARIANT_COUNT)  # 默认1
```

每个变体都调用 LLM（温度 0.2），输出符合 9 段结构（课程导入/学习目标/你的当前学习情况/知识讲解/重点难点突破/示例讲解/课堂小结/学完后自测/拓展延伸）的 Markdown 内容。

#### 阶段 4：内容审核

`AuditService.audit_courseware()` 审核生成内容是否跑题。

如果驳回，以更高温度（0.5, 0.8）重试最多 2 次。

#### 阶段 5：持久化

`_persist_generated_resource()` 存入 `resources` 表，同步知识点到图谱。

---

## 10. 习题生成系统

### 10.1 入口

**API**: `POST /exercises/generate` （agent-service）  
**服务**: `ExerciseGenerationService`

### 10.2 生成流程

```
请求解析 → 画像快照 → LLM计划 → JSON生成 → 题型分配 → 去重 → 审核 → 落库
```

#### 智能体计划（AgentPlan）

先分析学习者状态生成出题策略：

```json
{
  "agent": "exercise_generation_agent",
  "mastery_score": 65,
  "difficulty_mix": {"foundation": 0.5, "intermediate": 0.4, "advanced": 0.1},
  "focus_points": ["循环条件判断", "边界检查", "嵌套循环应用"],
  "weak_question_types": ["programming", "choice"],
  "strategy": [
    "先覆盖学习范围内的核心概念和应用场景",
    "再针对错题或薄弱题型生成变式",
    "同一组内题干、题型和考查角度不得重复"
  ]
}
```

#### 题目生成

- **LLM 生成**：使用 `exercise_gen.md` prompt 模板，温度 0.15
- **JSON 解析**：三层策略（直接解析 / 平衡括号提取 / 截断提取）
- **题型分配**：`choice` → `blank` → `judge` → `short_answer` → `programming`
- **难度配比**（基于掌握度）：
  - 掌握度 < 40：70% 基础 + 30% 中等
  - 掌握度 < 70：50% 基础 + 40% 中等 + 10% 高级
  - 掌握度 ≥ 70：30% 基础 + 50% 中等 + 20% 高级

#### 去重机制

1. **签名去重** — 每题生成 `question_type::normalized_prompt` 签名
2. **历史去重** — 查询已有 80 道习题签名，避免重复
3. **强制补全** — 去重后数量不足时，动态生成变式补齐

#### 高数专区

对高数/微积分主题，使用 4 个硬编码知识片段（函数连续三条件、导数符号判断单调、定积分区间和符号、极限逼近方式），按题型模板生成题目，确保数学场景精准。

#### 审核重试

`AuditService.audit_exercises()` 审核，驳回后以更高温度（0.4, 0.65）重试。

---

## 11. 智能问答系统

### 11.1 入口

**API**: `POST /qa/analyze` （agent-service）  
**服务**: `QAService`

### 11.2 处理流程

1. **意图识别**：
   - `general` 模式：纯文本问题（如"什么是微积分"）
   - `learning_analysis` 模式：带学习上下文的深度分析
2. **智能体编排**：
   - general → 仅 `qa_agent`
   - learning_analysis → `learner_profiling_agent` + `knowledge_graph_agent` + `qa_agent`
3. **LLM 分析输出**：
   - `student_response` — 学生友好回答
   - `structured_analysis` — 结构化学习分析：
     - 知识缺口识别 (`identified_knowledge_gaps`)
     - 误解点 (`misconceptions`)
     - 难度评级 (`difficulty_level`)
     - 推荐下一步知识点 (`recommended_next_knowledge_points`)
     - 错题本更新 (`mistake_book_update`)
     - 资源推荐 (`resource_recommendations`)
4. **可选联动**：根据分析结果，可自动触发课件/习题生成

---

## 12. 学习路径规划

### 12.1 入口

**API**：
- `POST /paths/generate` — 生成学习路径
- `GET /paths/{user_id}` — 获取最新路径
- `POST /paths/adjust` — 调整任务状态

### 12.2 路径结构

```
阶段一：概念建构（2个任务）
  ├─ 学习核心概念课件 (courseware)
  └─ 查看前置知识依赖 (graph)

阶段二：练习强化（1个任务）
  └─ 完成基础与进阶习题 (exercise)

阶段三：复盘提升（1个任务）
  └─ 错题复盘与再次练习 (review)
```

**参数**：
- `daily_minutes`（15-180）→ 推算预计天数
- 画像中的学习风格决定资源推荐偏好
- 教师划定范围可覆盖默认路径结构

---

## 13. 聊天对话系统

### 13.1 入口

**API**（`/chat`）：
- `POST /chat/sessions/new` — 创建会话
- `GET /chat/sessions?user_id=` — 列表
- `GET /chat/sessions/{id}?user_id=` — 详情
- `POST /chat/chat` — 发送消息
- `DELETE /chat/sessions/{id}?user_id=` — 删除会话

### 13.2 大-小模型协作

```
用户消息 → 小模型搜索知识库
          ├─ 知识库有匹配 → 小模型直接回答（快，高置信度）
          └─ 知识库无匹配/复杂问题 → 大模型深度回答
                                      └─ 小模型分析大模型回答质量
```

**大模型触发条件**（任一满足）：
1. 知识库无相关内容
2. 含复杂关键词（为什么/如何/分析/对比/推导）
3. 问题长度 > 100 字符

---

## 14. 反馈联合智能体

### 14.1 入口

**触发**: `force_agents` 包含 `"evaluation_feedback_agent"` 或意图匹配"评估/测评/报告"

### 14.2 双阶段流程

**阶段 1**：`ReportService` 收集数据
- 学习建议 (`generate_learning_suggestions`)
- 画像快照 (`generate_profile_snapshot`)
- 错题统计 (`get_mistake_statistics`)
- 可选：阶段报告 (`generate_stage_report_detail`)
- 可选：综合报告 (`generate_comprehensive_report_detail`)

**阶段 2**：`FeedbackSynthesisService` LLM 综合

将 7 个上游智能体的输出 + 4 种评估数据拼接为不超过 5000 字符的上下文，输入 LLM（温度 0.4），输出结构化反馈：

```json
{
  "overall_assessment": "整体评估",
  "core_strengths": ["优势1", "优势2"],
  "improvement_areas": [
    {"area": "...", "severity": "high", "evidence_from": "习题生成智能体", "suggestion": "..."}
  ],
  "personalized_feedback": "面对学生的个性化反馈",
  "next_step_plan": {
    "immediate_actions": ["立即行动"],
    "this_week_focus": ["本周重点"],
    "recommended_resources": [{"type": "exercise", "title": "...", "reason": "..."}]
  },
  "agent_synthesis_summary": "智能体协同总结",
  "learning_insight": "核心洞察"
}
```

**降级兜底**：LLM 失败时，使用纯数据驱动的 `build_fallback()` 输出。

---

## 15. 教师工作台

### 15.1 入口

**服务**: `teacher_service`（端口 8005）  
**路由**: `POST /classes/scopes/assign`

### 15.2 教学范围划定

教师发布课件时指定：
- `class_id` — 班级 ID
- `student_user_id` — 可选指定学生（全班/个人）
- `knowledge_points` — 知识点列表
- `learning_direction` — 学习方向说明
- `courseware_title` + `courseware_content` — 课件内容
- `teaching_goal` — 教学目标

**生效机制**：`teaching_scopes` 表存储，在学习路径生成时注入 `teacher_scope` 参数，覆盖默认路径结构。

---

## 16. 前端页面架构

### 16.1 路由结构

| 路径 | 组件 | 权限 | 说明 |
|------|------|------|------|
| `/` | LandingView | 公开 | 首页/落地页 |
| `/login` | LoginView | 公开 | 登录 |
| `/register` | RegisterView | 公开 | 注册 |
| `/profile-setup` | ProfileSetupView | 登录 | 初始画像构建 |
| `/student/dashboard` | DashboardView | student | 学生仪表盘 |
| `/student/learning-path` | LearningPathView | student | 学习路径 |
| `/student/courseware` | CoursewareView | student | 课件生成 |
| `/student/exercise` | ExerciseView | student | 习题练习 |
| `/student/mistakes` | MistakeNotebookView | student | 错题本 |
| `/student/knowledge-graph` | KnowledgeGraphView | student | 知识图谱可视化 |
| `/student/report` | ReportView | student | 学习报告 |
| `/student/qa` | QaView | student | 智能问答 |
| `/student/resources` | ResourceView | student | 大学知识库+资源管理 |
| `/student/profile-analysis` | ProfileAnalysisView | student | 深度画像分析 |
| `/teacher/overview` | TeacherView | teacher | 教师总览 |
| `/teacher/classes` | TeacherView | teacher | 班级管理 |
| `/teacher/scopes` | TeacherView | teacher | 教学范围 |
| `/admin` | AdminView | admin | 管理控制台 |

### 16.2 API 客户端层

```typescript
// web-app/src/api/http.ts
serviceEndpoints = {
  user:    VITE_USER_API_BASE_URL,        // 127.0.0.1:8001
  agent:   VITE_AGENT_API_BASE_URL,       // 127.0.0.1:8002
  resource: VITE_RESOURCE_API_BASE_URL,   // 127.0.0.1:8003
  evaluation: VITE_EVALUATION_API_BASE_URL, // 127.0.0.1:8004
  teacher: VITE_TEACHER_API_BASE_URL,     // 127.0.0.1:8005
  system:  VITE_SYSTEM_API_BASE_URL,      // 127.0.0.1:8006
}
```

每个 API 客户端通过 Axios 创建，自动注入 JWT Bearer Token（localStorage → `learning-system-auth`）。

### 16.3 主要前端页面功能

| 页面 | 核心功能 |
|------|----------|
| **LandingView** | 产品介绍、功能亮点、注册/登录入口 |
| **ProfileSetupView** | 多轮对话式画像构建，6 个维度收集 |
| **DashboardView** | 学习概览：掌握度热力图、学习日历、待办任务、最近活动 |
| **CoursewareView** | 课件生成：知识点输入 → 风格选择 → 多变体预览 → 切换 → 导出 |
| **ExerciseView** | 习题：按知识点生成组题 → 作答 → 即时反馈 → 错题记录 |
| **LearningPathView** | 路径：阶段展开 → 任务完成 → 进度追踪 → 教师范围展示 |
| **KnowledgeGraphView** | 图谱：节点-边可视化 → 点击展开依赖 → 关联资源 |
| **QaView** | 问答：会话列表 → 提问 → 流式回答 → 追问 → 分析报告 |
| **ReportView** | 报告：综合评估 → 能力雷达 → 错题统计 → 改进建议 |
| **ResourceView** | 知识库：学科筛选 → 搜索 → 课件下载 → 资源管理（增删） |
| **ProfileAnalysisView** | 深度画像：六维雷达图 → 学习建议 → 画像摘要 |
| **TeacherView** | 教师：班级管理 → 范围划定 → 课件发布 → 学生学情 |
| **AdminView** | 管理：用户管理、系统监控 |

---

## 17. API 路由总览

### 17.1 User Service (8001)

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/users/register` | 用户注册 |
| POST | `/users/login` | 用户登录（返回 JWT） |
| GET | `/users/{id}` | 获取用户信息 |
| GET | `/users/{id}/profile` | 获取学习画像 |
| PUT | `/users/{id}/profile` | 更新学习画像 |
| POST | `/users/{id}/profile/build` | 构建画像（LLM 对话） |

### 17.2 Agent Service (8002)

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/agents/coordinate` | 多智能体编排（通用入口） |
| POST | `/resources/generate` | 课件生成 |
| POST | `/exercises/generate` | 习题生成 |
| POST | `/qa/analyze` | 智能问答 |
| POST | `/paths/generate` | 生成学习路径 |
| GET | `/paths/{user_id}` | 获取学习路径 |
| POST | `/paths/adjust` | 调整路径任务 |
| GET | `/knowledge-base` | 知识库列表 |
| GET | `/knowledge-base/search?q=&top_k=` | 知识库搜索 |
| GET | `/knowledge-base/{id}` | 知识库文章详情 |
| POST | `/graph/dependencies` | 图谱依赖查询 |
| GET | `/graph/related-resources/{kp}` | 图谱关联资源 |
| POST | `/graph/visualization` | 图谱可视化 |
| POST | `/chat/sessions/new` | 创建聊天会话 |
| GET | `/chat/sessions?user_id=` | 聊天会话列表 |
| GET | `/chat/sessions/{id}?user_id=` | 聊天会话详情 |
| POST | `/chat/chat` | 发送聊天消息 |
| DELETE | `/chat/sessions/{id}?user_id=` | 删除聊天会话 |

### 17.3 Resource Service (8003)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/resources` | 列出所有资源 |
| GET | `/resources/{id}` | 获取单个资源 |
| POST | `/resources/import-external` | 导入外部课件 |
| POST | `/resources/{id}/export` | 导出 PDF/Word |
| GET | `/resources/{id}/download` | 下载资源文件 |
| PATCH | `/resources/{id}/status` | 更新资源状态(draft/ready/archived) |
| DELETE | `/resources/{id}` | **删除单个资源** |
| DELETE | `/resources` | 删除所有资源 |

### 17.4 Teacher Service (8005)

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/classes/scopes/assign` | 分配教学范围 |

---

## 18. 数据流转图

### 18.1 课件生成全链路

```
前端 CoursewareView
  │  POST /resources/generate {user_id, knowledge_point, resource_style}
  ▼
CoordinatorWorkflow.run()
  │  force_agents: [learner_profiling_agent, resource_generation_agent]
  ▼
[1] PersonalizationService.build_snapshot()
      ├─ user_profiles (画像)
      ├─ answer_records (作答)
      └─ exercises (习题)
      → LearnerPersonalizationSnapshot
  ▼
[2] ResourceGenerationService.generate_courseware_with_plan()
      ├─ ChromaRetriever.retrieve()  → context_text
      ├─ KnowledgeBaseService.get_article() → grounding_text
      ├─ _build_generation_plan() → generation_plan
      ├─ _invoke_llm() → content (每人1-3个变体)
      ├─ AuditService.audit_courseware() → pass/reject
      └─ _persist_generated_resource() → resources 表
  ▼
[3] KnowledgeGraphRepository.sync_courseware_to_graph()
      ├─ _derive_prerequisites() → knowledge_points + knowledge_relations
      └─ Neo4j MERGE 节点和关系
  ▼
返回 → 前端渲染 Markdown 课件 + 变体切换
```

### 18.2 习题→作答→画像更新环路

```
习题生成 → exercises 表
  ↓
学生作答 → answer_records 表
  ↓
PersonalizationService 读取最新记录
  ↓
更新画像快照（掌握度、正确率、薄弱题型、错题）
  ↓
下次课件/习题生成时使用最新画像
```

---

## 19. 环境配置说明

### 19.1 必需配置

```env
# 数据库
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/learning_system

# JWT
JWT_SECRET_KEY=your-strong-secret

# LLM（至少配一个）
DEEPSEEK_API_KEY=sk-xxx           # 优先
QWEN_API_KEY=sk-xxx               # 次选
OPENAI_API_KEY=sk-xxx             # 兜底

# 前端
VITE_USER_API_BASE_URL=http://127.0.0.1:8001
VITE_AGENT_API_BASE_URL=http://127.0.0.1:8002
VITE_RESOURCE_API_BASE_URL=http://127.0.0.1:8003
```

### 19.2 启动命令

```bash
# 启动全部基础设施
docker-compose up -d

# 爬取+索引知识库
python scripts/crawl_resources.py
python scripts/index_resources.py

# 启动前端开发服务器
cd web-app && npm run dev
```

---

## 20. 设计说明文档

本系统围绕“基于大模型的个性化资源生成与学习多智能体系统”展开设计，目标是在真实学习数据、知识库内容和教师教学范围的共同约束下，为学生生成更贴合其当前能力水平的课件、习题、学习路径和反馈报告。整体设计强调可扩展的微服务架构、可追溯的 RAG 知识增强、多智能体协同决策，以及面向学生个体差异的动态画像更新。

### 20.1 AI 工具使用过程

#### 20.1.1 开发与设计阶段

在项目开发过程中，AI 工具主要用于辅助需求拆解、架构梳理、代码实现、文档整理和测试检查，形成“人工设计 + AI 辅助生成 + 人工验证修正”的协作流程：

1. **需求分析与功能拆解**：使用 AI 工具将“个性化学习资源生成、多智能体协作、知识图谱、RAG 检索、学习评价”等高层需求拆分为用户服务、智能体服务、资源服务、评价服务、教师服务和系统服务等模块。
2. **技术架构设计辅助**：通过 AI 辅助比较微服务、单体服务、异步任务队列、多数据库协同等方案，最终形成 FastAPI 微服务 + Vue 前端 + PostgreSQL/Neo4j/ChromaDB 多库协作的架构。
3. **Prompt 与智能体流程设计**：使用 AI 工具辅助编写课件生成、习题生成、答疑分析、反馈综合等 Prompt 模板，并根据输出效果反复调整结构化字段、约束条件和审核规则。
4. **代码生成与重构辅助**：在人工确定接口、数据模型和业务边界后，使用 AI 工具辅助生成部分服务代码、Schema、API 调用封装和文档草稿，再由开发者检查逻辑、修复兼容性问题并补充测试。
5. **测试与文档完善**：使用 AI 工具辅助整理接口说明、系统架构文档、运行说明和异常场景，结合本地测试结果对文档进行校正，确保说明与实际代码保持一致。

#### 20.1.2 系统运行阶段

系统运行时也集成了大模型能力，AI 不只是开发辅助工具，而是平台核心业务能力的一部分：

1. **学习画像构建**：通过学生初始对话、历史作答记录、正确率、耗时、薄弱题型和错题数据，生成并持续更新个性化学习画像。
2. **RAG 知识增强**：先从 ChromaDB 向量库和知识库文章中检索相关内容，再将检索片段注入大模型 Prompt，减少凭空生成，提高课件、习题和问答内容的可依据性。
3. **多智能体协作**：由 LangGraph 编排画像分析、知识图谱、知识库检索、路径规划、课件生成、习题生成、答疑和反馈评价等智能体，使不同任务能够共享上下文并协同完成复杂学习流程。
4. **内容生成与审核**：课件和习题生成后进入审核逻辑，检查内容是否偏题、格式是否符合要求、题目是否重复，必要时自动重试生成。
5. **反馈闭环优化**：学生作答后，评价服务更新掌握度、薄弱点和错题模式，后续课件、习题和学习路径会基于最新画像动态调整。

### 20.2 技术架构

系统采用前后端分离和微服务架构，整体分为表示层、业务服务层、智能体编排层、数据存储层和基础设施层。

#### 20.2.1 表示层

- **前端框架**：Vue 3 + Element Plus。
- **主要页面**：学生仪表盘、学习路径、课件生成、习题练习、错题本、知识图谱、智能问答、学习报告、教师工作台和后台管理。
- **交互方式**：前端通过 Axios 调用各微服务 API，并携带 JWT Token 完成身份认证和权限控制。

#### 20.2.2 业务服务层

- **User Service**：负责用户注册、登录、角色权限、学习画像读取与更新。
- **Agent Service**：负责多智能体编排、课件生成、习题生成、智能问答、学习路径规划、知识库检索和知识图谱查询。
- **Resource Service**：负责学习资源导入、导出、下载、状态管理和删除。
- **Evaluation Service**：负责作答提交、客观题判分、主观题/编程题 LLM 评分、错题分析和学习报告生成。
- **Teacher Service**：负责教师划定教学范围、发布课件、管理班级学习目标。
- **System Service**：负责系统管理、运行状态和基础配置。

#### 20.2.3 智能体编排层

核心编排入口为 `CoordinatorWorkflow`，基于 LangGraph 将用户请求拆分并路由到不同智能体。智能体之间通过共享上下文传递画像摘要、知识点依赖、检索结果、生成计划和评价反馈，从而支持跨模块协作。

主要智能体包括：

- 学习画像智能体：分析学生掌握度、薄弱点和学习风格。
- 知识图谱智能体：维护知识点依赖关系和资源关联关系。
- 知识库智能体：负责知识库文章检索与内容 grounding。
- 路径规划智能体：生成阶段化学习任务。
- 资源生成智能体：生成个性化课件和学习材料。
- 习题生成智能体：生成结构化练习题并控制难度分布。
- 答疑智能体：提供学习问答、误区识别和下一步建议。
- 评价反馈智能体：综合多源数据生成学习反馈和改进计划。

#### 20.2.4 数据存储层

- **PostgreSQL**：存储用户、画像、资源、习题、作答记录、学习路径、报告和教师教学范围等业务数据。
- **Neo4j**：存储知识点节点、前置依赖、后续推荐和资源关联关系，用于知识图谱可视化和路径推理。
- **ChromaDB**：存储知识库文档向量，用于 RAG 相似度检索。
- **Redis**：用于缓存、会话和高频临时数据。
- **RabbitMQ**：用于智能体任务分发和异步事件传递。
- **MinIO**：用于课件、导出文件等对象存储。

#### 20.2.5 部署与运行架构

系统通过 Docker Compose 管理数据库、消息队列、向量库、对象存储、后端服务和 Nginx 反向代理。开发环境可分别启动 Python 微服务和 Vue 前端，生产环境可通过 Nginx 统一转发前端页面和后端 API。

### 20.3 创新点

1. **多智能体协同的个性化学习资源生成**：系统不是单次调用大模型生成内容，而是将画像分析、知识检索、路径规划、资源生成、习题生成和反馈评价拆分为多个专业智能体，通过编排流程完成协作。
2. **学习画像驱动的动态生成机制**：课件、习题和学习路径会根据学生掌握度、近期正确率、薄弱题型、错题记录和学习偏好动态变化，实现“同一知识点、不同学生不同资源”。
3. **RAG + 知识图谱双重知识增强**：ChromaDB 负责语义相似内容检索，Neo4j 负责知识点依赖与关系推理，两者共同约束大模型输出，使生成内容既有语义依据，也符合知识结构。
4. **课件、习题、作答、反馈的闭环系统**：系统从生成学习资源开始，到学生练习、评价服务判分、画像更新、再次生成资源，形成完整的数据反馈闭环。
5. **教师教学范围与 AI 个性化推荐融合**：教师可以划定班级或学生个人的教学范围，系统在生成学习路径和资源时结合教师目标与学生画像，兼顾教学计划和个体差异。
6. **大模型与小模型协同的智能问答模式**：简单问题优先由小模型或知识库检索处理，复杂问题再调用大模型深度分析，在回答质量、响应速度和调用成本之间取得平衡。
7. **生成内容审核与重试机制**：课件和习题生成后经过审核服务检查，未通过时自动调整参数重新生成，提升生成内容的稳定性和可用性。
8. **面向教学场景的多库协同架构**：PostgreSQL、Neo4j、ChromaDB、Redis、RabbitMQ 和 MinIO 分别承担结构化业务数据、图关系、向量检索、缓存、消息和文件存储职责，满足复杂学习系统对不同数据形态的处理需求。

---
