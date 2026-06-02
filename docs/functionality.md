# 功能说明文档

> 本文档基于当前代码实现人工更新。
> 最近更新时间：`2026-05-30`

## 1. 项目当前实现概览

当前仓库已经实现的核心能力如下：

- 后端已提供 `user-service`、`agent-service`、`evaluation-service`、`teacher-service`、`system-service` 五个本地可运行服务。
- 数据层已提供 SQLAlchemy 模型、Alembic 初始迁移、本地建表能力与默认账号初始化。
- 学生端已经支持学习路径、课件阅读、在线答题、即时反馈、错题本、重练题、学习报告和智能答疑。
- 智能答疑已支持优先调用 DeepSeek 生成具体教师讲解，同时返回结构化学习分析结果。
- 教师端已经支持班级管理、作业布置与批改、学生洞察以及学生详细诊断查看。
- 管理员端已接入基础系统配置、角色分配、审计日志等能力。

## 2. 已实现模块

### 2.1 用户服务 `user-service`

功能说明：

- 创建平台用户。
- 提供注册接口，并在注册后直接签发 JWT。
- 提供登录接口。
- 初始化空白学习者画像。
- 查询用户详情、用户画像和当前登录用户信息。
- 服务启动时自动建表，并自动确保本地管理员账号可用。

本地默认账号：

- 用户名：`admin`
- 密码：`admin123`

接口清单：

| Method | Path | Handler | Description |
| --- | --- | --- | --- |
| `POST` | `/users` | `create_user` | Create a platform user and initialize an empty learner profile. |
| `POST` | `/users/register` | `register` | Register a new user and immediately return a JWT token. |
| `POST` | `/users/login` | `login` | Authenticate a user and return a JWT token. |
| `GET` | `/users/me` | `get_me` | Return the currently authenticated user. |
| `GET` | `/users/{user_id}` | `get_user` | Retrieve a user by ID. |
| `GET` | `/users/{user_id}/profile` | `get_profile` | Retrieve a learner profile by user ID. |
| `GET` | `/users/{user_id}/profile/dashboard` | `get_profile_dashboard` | Return learner dashboard data for the student workspace. |
| `POST` | `/users/{user_id}/token` | `create_user_token` | Issue a JWT token for a known user. |

### 2.2 智能体服务 `agent-service`

功能说明：

- 接收前端或上游服务的智能体任务请求。
- 提供协调调度、资源生成、知识图谱查询、学习路径生成、结构化练习生成。
- 提供知识图谱可视化节点和边数据。
- 课件生成当前默认返回 1 份正式模型课件，优先保证稳定生成与响应成功率。
- 答疑服务支持具体讲解回答与结构化分析双输出。

协调调度接口：

| Method | Path | Handler | Description |
| --- | --- | --- | --- |
| `POST` | `/agents/coordinate` | `coordinate` | Execute the coordinator LangGraph workflow. |

知识图谱接口：

| Method | Path | Handler | Description |
| --- | --- | --- | --- |
| `POST` | `/graph/dependencies` | `get_dependency_path` | Return dependency chains for a knowledge point. |
| `GET` | `/graph/related-resources/{knowledge_point}` | `get_related_resources` | Return resources associated with a knowledge point. |
| `POST` | `/graph/visualization` | `get_visualization_graph` | Return visualization-ready node and edge data. |

资源生成接口：

| Method | Path | Handler | Description |
| --- | --- | --- | --- |
| `POST` | `/resources/generate` | `generate_resource` | Generate personalized courseware and return one recommended content plus multiple selectable variants. |

学习路径与练习接口：

| Method | Path | Handler | Description |
| --- | --- | --- | --- |
| `POST` | `/paths/generate` | `generate_learning_path` | Generate a lightweight personalized learning path. |
| `POST` | `/exercises/generate` | `generate_exercises` | Generate a structured exercise set for learner practice. |

智能答疑接口：

| Method | Path | Handler | Description |
| --- | --- | --- | --- |
| `POST` | `/qa/analyze` | `analyze_question` | Return a concrete tutoring answer and structured learning analysis. |

### 2.3 效果评估服务 `evaluation-service`

功能说明：

- 支持在线答题即时判分与反馈。
- 支持错题本、错题重练题生成。
- 支持阶段报告与综合报告详情。
- 支持生成学生画像快照，供学生端课件和报告模块直接使用。

接口清单：

| Method | Path | Handler | Description |
| --- | --- | --- | --- |
| `POST` | `/evaluation/submit` | `submit_answer` | Evaluate one answer submission and persist real feedback, mastery updates, and events. |
| `POST` | `/evaluation/batch_submit` | `batch_submit` | Evaluate a batch of answer submissions and return aggregate accuracy. |
| `GET` | `/evaluation/stage-report/{user_id}/{chapter_id}` | `get_stage_report` | Generate a chapter-level stage report from real answer history. |
| `GET` | `/evaluation/monthly-report/{user_id}` | `get_monthly_report` | Generate a rolling 30-day monthly report. |
| `POST` | `/evaluation/answers` | `submit_answer_record` | Submit one answer record for evaluation. |
| `POST` | `/evaluation/practice/submit` | `submit_practice_answer` | Evaluate one practice answer and return immediate feedback. |
| `GET` | `/evaluation/reports/stage/{user_id}` | `get_stage_report` | Generate a stage report. |
| `GET` | `/evaluation/reports/stage/{user_id}/detail` | `get_stage_report_detail` | Generate a detailed stage report for the student workspace. |
| `GET` | `/evaluation/reports/comprehensive/{user_id}` | `get_comprehensive_report` | Generate a comprehensive report. |
| `GET` | `/evaluation/reports/comprehensive/{user_id}/detail` | `get_comprehensive_report_detail` | Generate a detailed comprehensive report for the student workspace. |
| `GET` | `/evaluation/mistakes/{user_id}` | `get_mistake_statistics` | Return mistake statistics. |
| `GET` | `/evaluation/mistakes/{user_id}/detail` | `get_mistake_notebook` | Return the learner mistake notebook. |
| `GET` | `/evaluation/mistakes/{user_id}/remedial` | `get_remedial_exercises` | Generate remedial exercises from the learner's mistake notebook. |
| `GET` | `/evaluation/profiles/{user_id}/snapshot` | `get_profile_snapshot` | Return a learner profile dashboard snapshot derived from recent practice. |
| `GET` | `/evaluation/reports/suggestions/{user_id}` | `get_learning_suggestions` | Return personalized suggestions distilled from persisted answer history. |

### 2.4 教师服务 `teacher-service`

功能说明：

- 支持班级列表与班级创建。
- 支持班级进度概览与学生洞察卡片。
- 支持教师查看单个学生的错题本、阶段报告、综合报告详情。
- 支持作业布置与批改结果提交。

接口清单：

| Method | Path | Handler | Description |
| --- | --- | --- | --- |
| `GET` | `/teacher/classes` | `list_classes` | List all classes. |
| `POST` | `/teacher/classes` | `create_class` | Create a new class. |
| `GET` | `/teacher/classes/{class_id}/progress` | `get_class_progress` | Get class progress overview. |
| `GET` | `/teacher/classes/{class_id}/insights` | `get_class_insights` | Get student insights for one class. |
| `GET` | `/teacher/classes/{class_id}/students/{user_id}` | `get_student_learning_detail` | Get one student's detailed mistake notebook and learning reports. |
| `POST` | `/teacher/homework/assign` | `assign_homework` | Assign homework to a class. |
| `POST` | `/teacher/homework/{submission_id}/review` | `review_homework` | Review one homework submission. |

### 2.5 系统服务 `system-service`

功能说明：

- 提供学科管理、系统配置、角色分配、审计日志基础能力。
- 供管理员端页面直接联调和演示。

### 2.6 Web 前端

核心页面：`LoginView.vue`、`RegisterView.vue`、`StudentView.vue`、`TeacherView.vue`、`AdminView.vue`

当前页面能力：

- 登录、注册、JWT 持久化、请求拦截器、路由守卫、角色分流已完成。
- 学生端已从测试面板升级为正式学习工作台，支持路径、课件、练习、反馈、错题本、报告、图谱可视化。
- 课件区当前默认展示本次生成的正式模型课件；如需更多候选版本，可通过服务配置扩展返回数量。
- 课件生成失败时会明确提示模型生成失败，不再自动切换为本地快速课件。
- 智能答疑按钮已改为“开始智能讲解”，优先调用 DeepSeek 输出具体讲解正文。
- 后端不可达时，前端会明确提示“无法连接到后端服务”，不再统一误报为用户名密码错误。
- 教师端已从摘要卡片升级为正式工作台，支持查看班级、学生洞察，并可点开学生详情抽屉查看错题本与报告。
- 管理员端已接入 `system-service` 基础能力。

默认访问地址：`http://127.0.0.1:5175`

## 3. 当前未完成但已预留的模块

- `resource-service` 仍待从骨架推进到真实资源库业务。
- 更完整的管理员复杂业务仍待扩展。
- 移动端 `React Native` 尚未创建。
- Java 版后端骨架已经存在，但当前主联调链路仍以 Python 服务为准。

## 4. 本地启动与联调

推荐使用脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local_services.ps1
```

该脚本会尝试启动：

- `user-service`：`8001`
- `agent-service`：`8002`
- `evaluation-service`：`8004`
- `teacher-service`：`8005`
- `system-service`：`8006`
- `agent-service-qa-compat`：`8007`
- `web-app`：`5175`

常用本地地址：

- 前端：`http://127.0.0.1:5175`
- 用户服务健康检查：`http://127.0.0.1:8001/health`
- 智能体服务健康检查：`http://127.0.0.1:8002/health`

## 5. 文档更新机制

### 5.1 手动更新

```bash
python scripts/generate_function_docs.py
```

### 5.2 实时监听更新

```bash
python scripts/watch_function_docs.py
```

## 6. 推荐维护规则

- 新增接口后，先更新代码，再同步文档。
- 新增页面后，在文档中补充页面职责与交互入口。
- 提交代码前，建议检查启动方式、默认账号和主要页面说明是否仍与实现一致。

## 7. Recent Integration Notes

The `main` branch has absorbed selected capabilities from the standalone `agent-core` branch while keeping the Python multi-service runtime as the primary execution path.

Added endpoints:

- `POST /users/{user_id}/profile/chat`
  Conversational learner-profile building with structured extracted dimensions and estimated remaining rounds.
- `PUT /users/{user_id}/profile`
  Manual learner-profile dimension patching.
- `GET /paths/{user_id}`
  Fetch the latest persisted active learning path.
- `POST /paths/adjust`
  Mark one generated path task as `complete`, `reset`, or `skip`.

Selection rationale:

- Kept `main` implementations for resource generation, QA analysis, and evaluation/reporting because they already had better integration coverage and passing automated tests.
- Added the learner-profile conversation flow and persisted learning-path adjustment because those capabilities existed in `agent-core` but were still missing on `main`.

Second-round integration:

- `POST /qa/analyze`
  Now returns `context_snippets` and `confidence` so the tutoring result can expose lightweight knowledge-grounded evidence similar to the standalone `agent-core` tutor flow.
- `GET /reports/suggestions/{user_id}`
  Returns concise personalized learner suggestions and focus areas distilled from persisted practice evidence.

Third-round integration:

- `POST /resources/generate`
  Now follows a deterministic coordination plan inspired by `agent-core` `ResourceCoordinationServiceImpl`.
  The response includes `generation_plan` with inferred `knowledge_point`, `resource_type`, `difficulty`, `target_word_count`, `suggested_outline`, and `personalization_hints`.
- Selection rationale:
  We did not copy the original async queue/task-status design into `main` because the Python synchronous flow is currently more stable and faster in local tests.
  We kept the working `main` generation path, but migrated the high-value pre-generation analysis layer so the produced content is now guided by an explicit plan rather than only raw request fields.
