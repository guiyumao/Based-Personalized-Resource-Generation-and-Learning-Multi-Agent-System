# 基于大模型的个性化资源生成与学习多智能体系统 — 系统功能文档

## 1. 文档说明

本文档面向产品、开发与验收人员，从头到尾完整描述「基于大模型的个性化资源生成与学习多智能体系统」的功能全貌，内容包括：系统定位、角色体系、总体架构、各微服务功能明细、核心业务流程、数据模型、接口清单、运行部署方式以及当前已知边界。文档内容以仓库源码与 2026-10-21 版功能基线为准。

## 2. 系统概述

### 2.1 定位

本系统是一个面向**学生、教师、管理员**三类角色的多智能体个性化学习平台。系统以大语言模型（LLM）为核心驱动力，围绕「学习规划 → 资源学习 → 练习评价 → 问题诊断 → 补强调整」组织连续的学习闭环。

### 2.2 「千人千面」的四个维度

系统通过多智能体协作实现个性化，体现在四个维度：

1. **学什么**：由路径规划智能体依据学习者画像与知识图谱生成个性化学习路径。
2. **怎么学**：由资源生成智能体生成个性化课件（图文、导图、代码案例、讲稿等）。
3. **练什么**：由习题生成智能体针对薄弱知识点生成练习。
4. **下一步做什么**：由评价反馈智能体根据作答表现给出诊断报告与补强建议，并反哺路径调整。

### 2.3 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Element Plus + Vite（开发端口 5175） |
| 主后端 | Python FastAPI 多服务（端口 8001–8007） |
| 迁移预研 | Java 17 + Spring Boot 3 骨架（`java-services/`，非主链路） |
| 关系库 | 本地 SQLite（`learning_system.db`）/ 生产 PostgreSQL |
| 向量库 | Chroma（集合 `education_resources`，约 1296 个语义分块） |
| 图数据库 | Neo4j（知识图谱） |
| 其他中间件 | Redis、RabbitMQ、MinIO、Elasticsearch（docker-compose 编排） |
| 智能体编排 | LangChain / LangGraph |

## 3. 角色体系

### 3.1 学生

学生是学习闭环的核心使用者，可使用：学习路径生成与调整、课件学习、课后自测、错题本与重练题、收藏本、学习报告（章节/阶段/月度/综合）、学习洞察、知识图谱与思维导图、智能答疑、聊天助手（大小模型协作）、小智学习助手（附件、流式对话、持久任务、个人记忆）、笔记与闪卡、成绩单导入与分析、讨论区等。

### 3.2 教师

教师侧能力由 teacher-service 提供：班级管理、学生入班、教学范围（TeachingScope）设定、作业布置与提交批改、讨论区与通知。配合 evaluation-service 的成绩单分析能力，教师可导入 XLSX/CSV/DOCX/PDF/图片（OCR）格式的成绩单并获得学情分析。

### 3.3 管理员

管理员负责平台的治理与运营，共 12 个管理页面、7 个功能分组：数据看板、用户与角色管理、学科规划与公共知识建设、知识文档与候选审核发布、自动维护计划、资源管理与内容改写、提示词与图文配置、操作日志与系统配置等。本地默认管理员账号为 `admin`，密码由 `.env` 的 `DEFAULT_ADMIN_PASSWORD` 配置。

## 4. 总体架构

### 4.1 微服务划分

| 服务 | 端口 | 职责 |
|---|---|---|
| user_service | 8001 | 认证、学习者画像、学习画像（learning_portrait）、笔记/闪卡（study_tools） |
| agent_service | 8002 | 核心服务：多智能体协调、资源/习题生成、路径、答疑、聊天、小智助手、知识治理、运营看板 |
| resource_service | 8003 | 资源目录、推荐、导入、下载、DOCX 导出 |
| evaluation_service | 8004 | 作答评分、错题本、学习报告、成绩单分析、学习洞察 |
| teacher_service | 8005 | 班级、教学范围、作业、讨论、通知 |
| system_service | 8006 | 用户管理、角色、学科、系统配置、日志 |
| agent-service-qa-compat | 8007 | 答疑兼容部署入口 |
| assistant-worker | 无端口 | 持久任务 Worker（心跳、租约、执行尝试恢复） |

### 4.2 多智能体协调器

协调器位于 `services/agent_service/app/agents/coordinator.py`，基于 LangGraph StateGraph 编排，执行链为 **意图分析（analyze_intent）→ 任务分发（dispatch_tasks）→ 冲突消解（resolve_conflicts）**。对外入口为 `POST /agents/coordinate`。

受支持的 8 个智能体：

| 智能体 | 职责 |
|---|---|
| learner_profiling_agent | 学习者画像构建（对话式 + 手工修补） |
| knowledge_graph_agent | 知识图谱构建与查询 |
| knowledge_base_agent | 公共知识库检索与治理 |
| path_planning_agent | 个性化学习路径规划与调整 |
| resource_generation_agent | 个性化课件/资源生成 |
| exercise_generation_agent | 个性化习题生成 |
| qa_agent | 智能答疑（优先 DeepSeek） |
| evaluation_feedback_agent | 作答评价与反馈建议 |

各智能体的本体实现分布于 `services/agent_service/app/services/` 下的 50+ 个服务模块，其中代表性模块包括：`personalization.py`（画像快照）、`learning_path.py`（路径生成/调整）、`resource_generation.py`（课件生成，含显式生成规划）、`exercise_generation.py`、`qa_service.py`、`rag.py`（ChromaRetriever：查询改写/重排/TTL 缓存）、`llm_factory.py`（LLM 工厂，支持按任务构建模型与预热）。

### 4.3 共享层与基础设施

`common/` 目录提供共享能力：SQLAlchemy 模型（`models/`）、Pydantic 模式（`schemas/`）、数据库会话与迁移引导（`db/`）、统一配置（`config.py`）、安全（`security/`）、消息队列封装（`messaging/rabbitmq.py`）、模型调用台账（`model_usage.py`）、学习上下文与证据（`learning_context.py` / `learning_evidence.py`）、画像评分（`profile_scoring.py`）等。

## 5. 功能模块详述

### 5.1 用户认证

| 接口 | 说明 |
|---|---|
| `POST /users/register` | 注册 |
| `POST /users/login` | 登录 |
| `GET /users/me` | 获取当前用户 |

### 5.2 学习者画像

- 对话式画像构建：`POST /users/{user_id}/profile/chat`（来自 agent-core 集成）。
- 手工维度修补：`PUT /users/{user_id}/profile`。
- 画像读模型包含持久化的 `profile_dimensions`，底层为四维画像：掌握度（mastery_json）、学习风格（learning_style）、认知能力（cognitive_abilities）、学习习惯（habits）。

### 5.3 学习路径

| 接口 | 说明 |
|---|---|
| `POST /paths/generate` | 生成学习路径（持久化生命周期） |
| `GET /paths/{user_id}` | 查询我的路径 |
| `POST /paths/adjust` | 调整路径 |
| `POST /paths/preflight` | 知识覆盖预检 |
| `POST /paths/adaptation/preview` / `confirm` | 调整提案需本人确认后生效 |

路径生成与调整结合知识图谱、画像掌握度与学习缺口（LearningKnowledgeGap），调整采用「先预览提案、本人确认」的安全模式。

### 5.4 个性化资源生成

入口：`POST /resources/generate`。完整链路：

1. 身份与学习上下文核验；
2. 材料获取（协调器共享检索，RAG 召回）；
3. **生成规划**：先产出显式 `generation_plan`，包含主题规范化、大纲、难度、目标字数与个性化提示；
4. 本人候选复用判断（30 天内，按用户/目标/学情/模板/篇幅指纹去重，避免重复生成）；
5. 正式生成（默认返回 1 份正式模型课件，保证稳定性；可通过 `RESOURCE_COURSEWARE_VARIANT_COUNT` 开启多候选版本）；
6. 保存资源与版本记录；
7. 导出与产物制作。

配套能力：

- **分章修订**：`POST /resources/{resource_id}/chapters/{chapter_key}/regenerate`，支持对单个章节重新生成。
- **资源编辑器**：管理员对资源进行改写与配图（改写操作受 `RUN_LIVE_LLM=1` + `DEEPSEEK_LIVE_PAID_ACK=1` 双闸门保护）。
- **本地产物**：可制作 PPTX、SVG 动画、WAV 语音、无声 WebM 视频等课件产物，存放于 `storage/` 并以 `/storage` 静态路径对外提供。
- **资源交互沉淀**：`POST /resources/{resource_id}/interactions` 记录查看、下载、来源打开等隐式反馈，供推荐系统使用。

### 5.5 资源推荐

`GET /resources/recommendations` 采用混合推荐策略，融合 User-CF、Item-CF、学习画像、知识点薄弱度与资源热度五路信号。资源目录、导入、下载与 DOCX 导出由 resource_service（8003）承担。

### 5.6 习题生成与作答评价

- 习题生成：`POST /exercises/generate`，按知识点与画像定向出题。
- 作答提交：`POST /evaluation/practice/submit` 与 `/batch_submit`。
- 错题本：`GET /evaluation/mistakes/{user_id}/detail`，支持补救练习（remedial）生成重练题。
- 收藏本：`practice/favorites`。
- 评价反馈：评价反馈智能体汇总作答表现，输出诊断结论并反哺学习建议、知识漏洞与错题本。

### 5.7 学习报告与洞察

- 报告：章节报告、阶段报告、月度报告、综合报告。
- 确定性分析建议：`GET /reports/suggestions/{user_id}`（源自 agent-core 分析层的确定性建议）。
- 学习洞察与活动心跳：记录学习活动流，支撑时长、节奏与坚持度分析。

### 5.8 笔记与闪卡

- 学习笔记：`/study/notes`，带编辑历史（CAS 乐观锁保护，防止并发覆盖）。
- 复习闪卡：`/study/cards`，支持到期复习调度、回执去重，卡片可与知识点绑定（CardKnowledgeBinding）。

### 5.9 知识图谱与思维导图

- 知识图谱基于 Neo4j，提供图谱查询与可视化数据。
- 私人思维导图保存时校验版本冲突、单根节点与无环约束。

### 5.10 智能答疑

`POST /qa/analyze`：

- 优先调用 DeepSeek 生成具体教师式讲解正文；
- 作答前进行轻量关键词接地检索，返回 `context_snippets` 与 `confidence`；
- 同时返回结构化分析，供系统更新学习建议、知识漏洞与错题本；
- 8007 端口提供答疑兼容部署入口。

### 5.11 聊天系统（大小模型协作）

| 接口 | 说明 |
|---|---|
| `POST /chat/sessions/new` | 新建会话 |
| `GET /chat/sessions` | 会话列表 |
| `GET /chat/sessions/{id}` | 会话详情 |
| `POST /chat/chat` | 发送消息 |
| `DELETE /chat/sessions/{id}` | 删除会话 |

决策规则：知识库无相关内容、含复杂关键词、或问题长度超过 100 字符时路由到大模型；否则由小模型作答，并由小模型对质量做二次分析。会话上下文保留最近 10 条消息。

### 5.12 小智学习助手（Assistant）

- 对话：`POST /assistant/chat`，流式 `POST /assistant/chat/stream`。
- 附件：`/assistant` 附件上传与引用。
- 持久任务：`/assistant/tasks`、取消请求、重试、路径确认（confirm-path）；服务启动时自动恢复中断任务（fail_interrupted_tasks），可由独立 Worker（`ASSISTANT_TASK_EXECUTION_MODE=worker`）执行，带心跳与租约机制。
- 能力与记忆：`/assistant/capabilities`、个人记忆 `/assistant/memory`。

### 5.13 教师端功能

- 班级管理：创建班级、学生入班（ClassEnrollment）。
- 教学范围：TeachingScope 界定教学边界，约束生成内容范围。
- 作业：布置（Assignment）与提交（Submission）。
- 讨论与通知：DiscussionThread/Reply、Notification。

### 5.14 成绩单分析

成绩单接口支持 parse / analyze / history / chat / share / export 全流程：上传 XLSX/CSV/DOCX/PDF/图片（OCR，单文件 20MB 上限）→ 结构化解析（TranscriptImport/Score）→ 学情分析（TranscriptAnalysis）→ 可分享与导出。

### 5.15 公共知识库建设与治理

这是平台内容供给的中枢，分「自动建设」与「人工治理」两条线。

**自动建设链路（学生触发、无需等待管理员）：**

1. 公共版本预检：检查公共知识库是否已有所需学科/知识点/已发布内容；
2. 模型建设：缺口内容由模型生成草稿；
3. 独立模型全文审核：仅接受严格 PASS，正文哈希绑定，被拒绝最多修订一次；
4. 自动入库：直接创建 SystemSubject/KnowledgePoint、发布 KnowledgeVersion 并写入向量索引，标记 `license_name=AI_GENERATED`，语料头注明「AI 自动构建，管理员可修订/下架」，状态为 `AUTO_APPROVED`（与人工 `APPROVED` 严格区分）；
5. 发布/索引验证与重新检索；
6. 失败补偿：因 SQL/语料文件/Chroma 无法原子提交，采用「写锁 → 复用检查 → 发布 → 版本级校验 → 失败补偿（DB→文件→索引→reconcile）」，补偿失败写 AuditLog ERROR 并排队对账任务；任何失败返回 `{"ok": false, "reason": ...}` 而非伪成功。被管理员下架（WITHDRAWN）或驳回（REJECTED）的知识不会被自动补建。

**管理员工具链：**

- 建设任务：学科/知识点规划、计划确认、知识点构建、采集（Search/Fetch）；
- 候选审核：提交、审核、发布、撤回、版本 diff；
- 版本管理：compare / impact / rollback；
- 知识文档：上传、归类、分块、归档、转候选；
- 知识融合决策：A 新建 / B 补充 / C 修订 / D 重复 / E 冲突；
- 自动维护：维护计划、启停与报告；
- 预算控制：KnowledgeBudgetCounter 限制建设开销。

### 5.16 知识检索（RAG）

| 接口 | 说明 |
|---|---|
| `GET /knowledge-base/search` | 检索，模式 hybrid / lexical / vector，支持 subject、university、license 等过滤 |
| `GET /knowledge-base/status` | 索引状态 |
| `GET /knowledge-base/sources` | 来源列表 |
| `POST /knowledge-base/reindex` | 重建索引（仅管理员） |
| `POST /knowledge-base/sources/crawl` | 来源采集 |

检索器 ChromaRetriever 具备查询改写、结果重排与 TTL 缓存。口径约定：SQL 中的发布状态/版本/可见性是内容准入依据，Chroma 仅作为检索索引。知识库语料约 119 份 Markdown，覆盖 23 个学科目录（Python、C、Java、C++、算法、数据库等），索引约 1296 个语义分块。

### 5.17 管理端功能

1. **数据看板**（`/admin`）：`GET /admin/dashboard`、运营任务 `/admin/operations/tasks`、模型用量 `/admin/usage`（UTC 自然日口径）与导出、Worker 实例 `/admin/workers`、模型预算 `GET/PUT /admin/model-budget`。
2. **用户与角色**：搜索、分页、启停、角色分配。
3. **学科规划与知识建设 / 知识文档 / 审核发布 / 自动维护**：见 5.15。
4. **资源管理与内容改写**：管理员改写受双闸门保护。
5. **提示词与图文配置**：提示词模板带版本历史与恢复；图片 Provider 四态管理（blocked / invalid / disabled / configured）。
6. **操作日志与系统配置**：`/system/configs`、`/system/logs`、AuditLog。

## 6. 数据模型概览

关系模型集中于 `common/models/learning.py`（约 50 个实体类），按域划分：

| 域 | 主要实体 |
|---|---|
| 用户与画像 | User、UserProfile、ProfileConversation |
| 知识体系 | KnowledgePoint、KnowledgeRelation、SystemSubject |
| 资源 | Resource、ResourceInteraction |
| 学习过程 | StudySession、StudyActivity、LearningPath、LearningTask、LearningKnowledgeGap、LearningContext、ContextExercise |
| 练习评价 | Exercise、ExerciseFavorite、AnswerRecord、LearningReport |
| 笔记闪卡 | StudyNote、ReviewCard、CardReviewEvent、NoteRevision、CardKnowledgeBinding、CardReviewReceipt |
| 成绩单 | TranscriptImport、TranscriptScore、TranscriptAnalysis |
| 教学 | Course、Classroom、ClassEnrollment、Assignment、Submission、TeachingScope |
| 社区 | DiscussionThread、DiscussionReply、Notification |
| 聊天与助手 | ChatSession、ChatMessage、AssistantTask、AssistantAgentExecution、AssistantMemory、AssistantAttachment |
| 知识治理 | KnowledgeBuildTask、KnowledgeMaintenancePlan、KnowledgeBudgetCounter、KnowledgeCandidate、KnowledgeVersion、KnowledgeDocument |
| 运营 | ModelCall、WorkerInstance、TaskAttempt、SystemConfig、AuditLog |
| 媒体产物 | ResourceArtifact、ResourceRevision、ResourceIllustration |

数据库迁移由 Alembic 管理，共 33 个版本（0001 初始 schema → 0033 note_card_evidence），演进路径覆盖作答元数据、资源生命周期、学习社区、成绩单、助手任务、知识建设、学习上下文、运营台账、证据链等。

## 7. 提示词体系

`prompts/` 目录内置 13 份提示词模板，与智能体一一对应：协调器（coordinator）、画像（learner_profile）、知识图谱（knowledge_graph）、路径规划（path_planning）、资源生成（resource_gen）、习题生成（exercise_gen）、答疑（qa）、评价反馈（evaluation_feedback）、思维导图（mind_map_gen）、代码案例（code_case_gen）、视频脚本（video_script_gen）、公共知识建设（public_knowledge_build）、公共知识审核（public_knowledge_review）。提示词支持在管理端进行版本化管理与恢复。

## 8. 运行与部署

### 8.1 本地一键启动

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local_services.ps1
```

脚本拉起 8001–8007 全部服务与前端（5175）。启动后访问：

- 前端：`http://127.0.0.1:5175`
- 健康检查：`http://127.0.0.1:8001/health`（用户）/ `8002`（智能体）/ `8003`（资源）

### 8.2 手动启动

```bash
python -m uvicorn services.user_service.app.main:app --host 127.0.0.1 --port 8001
python -m uvicorn services.agent_service.app.main:app --host 127.0.0.1 --port 8002
python -m uvicorn services.evaluation_service.app.main:app --host 127.0.0.1 --port 8004
python -m uvicorn services.teacher_service.app.main:app --host 127.0.0.1 --port 8005
python -m uvicorn services.system_service.app.main:app --host 127.0.0.1 --port 8006
```

前端：`cd web-app && npm install && npm run dev`。

### 8.3 Docker 部署

`docker-compose.yml` 编排 postgres:16、redis:7.2、rabbitmq:3.13、neo4j:5、minio、elasticsearch:8.15、chroma:0.5.5 及 6 个应用服务与 nginx；Worker 通过 `deployment/assistant-worker.compose.yml` 以 overlay 方式部署。另提供 sakurafrp 内网穿透部署脚本与 nginx 反向代理配置。

### 8.4 环境要求

- Python 3.12+，Node.js 20+，可选 JDK 17 + Maven 3.9+（Java 骨架）。
- 核心依赖：FastAPI ≥ 0.115、SQLAlchemy ≥ 2.0、LangChain/LangGraph、chromadb（≥0.5.5,<1.0）、psycopg、neo4j、pika、redis、minio、elasticsearch<9、python-docx/pptx、reportlab、pytesseract/opencv（成绩单 OCR）。
- 测试标记：`live_llm`（需 `RUN_LIVE_LLM=1`）、`external_service`。

## 9. 测试与质量保障

- 测试分层：`tests/unit/`、`tests/integration/`、`tests/e2e/`、`tests/global/` 及聊天专项测试。
- RAG 回归：`benchmarks/rag_queries.json` 固定 50 条查询集，配合 `scripts/benchmark_rag.py` 做检索质量回归。
- 验收脚本：`scripts/verify_*.py` 提供大量端到端验收入口。
- 无费用运行护栏：`scripts/no_cost_runtime/`。
- 功能状态分级：IMPLEMENTED / TESTED_ISOLATED / LIVE_VERIFIED，引用管理功能融合矩阵（ADMIN_FUNCTION_FUSION_MATRIX.md）时需区分状态等级。

## 10. 已知边界与限制

依据当前功能基线，以下事项**尚不能统一宣称完成**：

1. 全站端到端（E2E）联调覆盖仍不完整；
2. 外部图片生成、TTS、视频生成等外部能力未默认启用；
3. 个性化推荐的长期效果缺少量化评估；
4. 未做正式压测与公网发布准备；
5. 管理功能融合矩阵中多数项为 PARTIAL/MISSING 状态（Token 分析为 MISSING）；
6. 新课件/习题禁止使用 Mermaid flowchart 图形；
7. 本地实际运行库为 `artifacts/local-start-20261019/runtime.sqlite`（而非根目录 `learning_system.db`）；
8. 答疑默认优先 DeepSeek，受密钥与预算配置约束。

## 11. 附录：目录结构

| 目录 | 职责 |
|---|---|
| `services/` | 6 个 Python FastAPI 微服务 |
| `common/` | 共享模型、模式、配置、安全、消息、台账 |
| `alembic/` | 数据库迁移（33 个版本） |
| `knowledge_base/` | 独立 RAG 知识库：语料 + Chroma 索引 |
| `prompts/` | 13 份智能体提示词模板 |
| `web-app/` | Vue 3 前端（学生端 16 页、管理端 12 页） |
| `scripts/` | 启动、采集、索引、基准、验收等运维脚本 |
| `deployment/` | Worker overlay 与内网穿透部署 |
| `java-services/` | Java 迁移骨架（非主链路） |
| `benchmarks/` | RAG 基准查询集与结果 |
| `tests/` | 单元/集成/E2E/全局测试 |
| `docs/` | 40+ 份设计与验收文档 |
