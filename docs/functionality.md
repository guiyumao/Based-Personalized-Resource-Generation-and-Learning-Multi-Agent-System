# 功能说明文档

> 本文档由 `scripts/generate_function_docs.py` 自动生成。
> 最近生成时间：`2026-05-30 13:17:19`

## 1. 项目当前实现概览

当前仓库已经实现的核心能力如下：

- 后端已提供 `user-service`、`agent-service`、`evaluation-service`、`teacher-service` 四个可运行的 FastAPI 服务。
- 数据层已提供 SQLAlchemy 模型、Alembic 初始迁移和本地建表脚本。
- 学生端已经支持学习路径、课件阅读、在线答题、即时反馈、错题本、重练题和学习报告。
- 教师端已经支持班级管理、作业布置与批改、学生洞察以及学生详细诊断查看。
- 前端已提供 `Vue 3 + Element Plus` Web 工作台，可直接联调当前后端。

## 2. 已实现模块

### 2.1 用户服务 `user-service`

功能说明：

- 创建平台用户。
- 提供注册接口，并在注册后直接签发 JWT。
- 提供登录接口。
- 初始化空白学习者画像。
- 查询用户详情、用户画像和当前登录用户信息。

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
| `POST` | `/resources/generate` | `generate_resource` | Generate a personalized resource with RAG context. |

学习路径与练习接口：

| Method | Path | Handler | Description |
| --- | --- | --- | --- |
| `POST` | `/paths/generate` | `generate_learning_path` | Generate a lightweight personalized learning path. |
| `POST` | `/exercises/generate` | `generate_exercises` | Generate a structured exercise set for learner practice. |

### 2.3 效果评估服务 `evaluation-service`

功能说明：

- 支持在线答题即时判分与反馈。
- 支持错题本、错题重练题生成。
- 支持阶段报告与综合报告详情。

接口清单：

| Method | Path | Handler | Description |
| --- | --- | --- | --- |
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

### 2.5 Web 前端

核心页面：`LoginView.vue`、`RegisterView.vue`、`StudentView.vue`、`TeacherView.vue`、`AdminView.vue`

当前页面能力：

- 登录、注册、JWT 持久化、请求拦截器、路由守卫、角色分流已完成。
- 学生端已从测试面板升级为正式学习工作台，支持路径、课件、练习、反馈、错题本、报告、图谱可视化。
- 教师端已从摘要卡片升级为正式工作台，支持查看班级、学生洞察，并可点开学生详情抽屉查看错题本与报告。
- 管理员端已接入 `system-service` 基础能力。

默认访问地址：`http://127.0.0.1:5175`

## 3. 当前未完成但已预留的模块

- `resource-service` 仍待从骨架推进到真实资源库业务。
- `system-service` 已有基础接口，但管理端复杂业务仍待扩展。
- 移动端 `React Native` 尚未创建。
- 更深层的智能体真实化、真实数据库写入和 LangGraph 端到端闭环仍待继续推进。

## 4. 文档更新机制

### 4.1 手动更新

```bash
python scripts/generate_function_docs.py
```

### 4.2 实时监听更新

```bash
python scripts/watch_function_docs.py
```

## 5. 推荐维护规则

- 新增接口后，先更新代码，再运行文档生成脚本。
- 新增页面后，在文档中补充页面职责与交互入口。
- 提交代码前，建议先运行一次文档生成脚本，确保文档与实现一致。
