# Based-Personalized-Resource-Generation-and-Learning-Multi-Agent-System

# 基于大模型的个性化资源生成与学习多智能体系统

一个面向学生、教师和管理员的多智能体个性化学习平台。当前主联调链路以 Python 服务为准，仓库中同时保留了正在迁移中的 `Java 17 + Spring Boot 3` 骨架。

## 当前状态

- 前端：`Vue 3 + Element Plus`
- 当前主联调后端：`FastAPI`
- 预研迁移骨架：`java-services/common`、`java-services/user-service`、`java-services/agent-service`
- 学生端支持学习路径、课件学习、课件多版本切换、课后自测、错题本、重练题、学习报告、知识图谱与智能答疑
- 智能答疑优先调用 DeepSeek，返回具体教学讲解正文

## 核心能力

### 用户认证

- `POST /users/register`
- `POST /users/login`
- `GET /users/me`

本地默认管理员账号：

- 用户名：`admin`
- 密码：`admin123`

### 学习资源与路径

- `POST /resources/generate`
- `POST /paths/generate`
- `POST /exercises/generate`

课件生成能力说明：

- 一次请求可返回多份候选课件
- 当前会返回 `interactive`、`concise`、`case` 三类版本
- 前端可直接切换不同课件版本继续学习

### 智能答疑

- `POST /qa/analyze`

答疑能力说明：

- 优先调用 DeepSeek 生成具体教师讲解
- 同时返回结构化分析，供系统更新学习建议、知识漏洞和错题本

## 目录结构

```text
common/
docs/
java-services/
prompts/
scripts/
services/
tests/
web-app/
```

## 本地启动

推荐直接使用脚本：

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

启动后可访问：

- 前端：`http://127.0.0.1:5175`
- 用户服务健康检查：`http://127.0.0.1:8001/health`
- 智能体服务健康检查：`http://127.0.0.1:8002/health`

## 手动启动

### 前端

```bash
cd web-app
npm install
npm run dev
```

### Python 服务

```bash
python -m uvicorn services.user_service.app.main:app --host 127.0.0.1 --port 8001
python -m uvicorn services.agent_service.app.main:app --host 127.0.0.1 --port 8002
python -m uvicorn services.evaluation_service.app.main:app --host 127.0.0.1 --port 8004
python -m uvicorn services.teacher_service.app.main:app --host 127.0.0.1 --port 8005
python -m uvicorn services.system_service.app.main:app --host 127.0.0.1 --port 8006
```

## 环境要求

- Python 3.12+
- Node.js 20+
- 可选：JDK 17、Maven 3.9+

## 文档

- 功能说明：[docs/functionality.md](docs/functionality.md)
- OpenAPI 草案：[docs/openapi.yaml](docs/openapi.yaml)

## Recent Integration From `agent-core`

The current `main` branch now keeps the Python multi-service architecture as the primary runtime, and additionally absorbs the highest-value learner-agent capabilities from `agent-core`:

- Conversational learner profile building:
  `POST /users/{user_id}/profile/chat`
- Manual learner profile dimension patching:
  `PUT /users/{user_id}/profile`
- Enriched learner profile read model with stored `profile_dimensions`
- Persisted learning-path lifecycle support:
  `POST /paths/generate`
  `GET /paths/{user_id}`
  `POST /paths/adjust`

Implementation choice notes:

- Resource generation, QA analysis, and evaluation reporting remain on the `main` Python services because they already had stronger end-to-end integration coverage and passing tests.
- The profile conversation flow and learning-path adjustment flow were added from the `agent-core` feature set because they were missing on `main` and could be integrated cleanly without regressing the existing student workspace.

Second-round integration details:

- QA now borrows the `agent-core` tutoring idea of lightweight keyword-grounded retrieval before answering:
  `POST /qa/analyze` now also returns `context_snippets` and `confidence`.
- Evaluation now exposes deterministic learner analytics suggestions inspired by the `agent-core` analytics layer:
  `GET /reports/suggestions/{user_id}`

Third-round integration details:

- Resource generation now borrows the `agent-core` coordination idea of building an explicit generation plan before composing content:
  `POST /resources/generate` now returns `generation_plan` with inferred topic normalization, outline, difficulty, target word count, and personalization hints.
- We intentionally kept `main`'s synchronous Python generation execution instead of porting the original async queue/task-status flow from `agent-core`, because the existing `main` path is currently faster and already well covered by passing tests.

## 说明

- 当前仓库中存在一部分中文乱码历史内容，本轮已优先修正关键启动说明和功能文档。
- 如果后续继续扩展接口或页面，建议同步更新 `docs/functionality.md` 和 `README.md`。
