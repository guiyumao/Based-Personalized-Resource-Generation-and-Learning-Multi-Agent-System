# 功能说明文档

> 本文档基于当前代码实现人工更新。
> 最近更新时间：`2026-07-19`

## 1. 项目当前实现概览

当前系统是一个面向学生、教师和管理员的多智能体个性化学习平台。主联调链路采用 `Vue 3 + Element Plus` 前端和 `FastAPI` 微服务后端，围绕学习者画像、课件生成、习题生成、智能答疑、错题复盘、学习报告和资源管理形成完整学习闭环。

当前本地可运行服务：

| 服务 | 端口 | 主要职责 |
| --- | --- | --- |
| `user-service` | `8001` | 用户注册、登录、JWT、学习者画像与画像分析 |
| `agent-service` | `8002` | 多智能体协调、课件生成、习题生成、学习路径、知识库、知识图谱、智能问答 |
| `resource-service` | `8003` | 学习资源列表、外部课件导入、下载、导出、状态更新、单个/批量删除 |
| `evaluation-service` | `8004` | 答题评分、报告生成、错题本、QA 错题同步、补救练习、学习建议 |
| `teacher-service` | `8005` | 班级、学生洞察、教学范围、作业布置与批改 |
| `system-service` | `8006` | 学科管理、系统配置、角色分配、审计日志 |
| `agent-service-qa-compat` | `8007` | 智能答疑兼容入口 |

## 2. 已实现模块

### 2.1 用户服务 `user-service`

功能说明：

- 创建平台用户。
- 提供注册、登录接口，并签发 JWT。
- 查询当前登录用户和指定用户详情。
- 初始化、读取、更新学习者画像。
- 支持对话式学习者画像采集。
- 支持画像维度补丁更新、跳过画像采集、画像状态查询和画像深度分析。
- 服务启动时自动建表，并确保本地管理员账号可用。

本地默认管理员账号：

- 用户名：`admin`
- 密码：由 `.env` 中的 `DEFAULT_ADMIN_PASSWORD` 配置

主要接口：

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/users` | 创建用户并初始化画像 |
| `POST` | `/users/register` | 注册并返回 JWT |
| `POST` | `/users/login` | 登录并返回 JWT |
| `GET` | `/users/me` | 获取当前登录用户 |
| `GET` | `/users/{user_id}` | 查询用户详情 |
| `GET` | `/users/{user_id}/profile` | 查询学习者画像 |
| `PUT` | `/users/{user_id}/profile` | 更新画像维度 |
| `DELETE` | `/users/{user_id}/profile/dimensions/{dimension_key}` | 删除指定画像维度 |
| `GET` | `/users/{user_id}/profile/status` | 查询画像采集状态 |
| `POST` | `/users/{user_id}/profile/skip` | 跳过画像采集 |
| `POST` | `/users/{user_id}/profile/chat` | 对话式画像采集 |
| `GET` | `/users/{user_id}/profile/dashboard` | 学生端画像仪表盘数据 |
| `GET` | `/users/{user_id}/profile/analysis` | 查询画像深度分析 |
| `GET` | `/users/{user_id}/profile/analysis/status` | 查询画像分析状态 |
| `POST` | `/users/{user_id}/profile/analysis/refresh` | 刷新画像深度分析 |
| `POST` | `/users/{user_id}/token` | 为指定用户签发 Token |

### 2.2 智能体服务 `agent-service`

功能说明：

- 接收前端或上游服务的智能体任务请求。
- 使用协调器选择并调度学习者画像、知识图谱、知识库、路径规划、资源生成、习题生成、问答和评价反馈等智能体。
- 生成个性化课件，并返回 `generation_plan`、正式内容和候选变体。
- 支持学习路径生成、路径读取和路径任务状态调整。
- 支持大学知识库列表、搜索和文章详情。
- 支持知识图谱依赖链、关联资源和可视化数据。
- 智能答疑支持具体讲解、结构化分析、轻量知识库证据、置信度、联带课件/习题生成。
- 聊天服务支持会话创建、会话列表、会话详情、消息发送和会话删除。

主要接口：

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/agents/coordinate` | 执行多智能体协调工作流 |
| `POST` | `/resources/generate` | 生成个性化课件资源 |
| `POST` | `/paths/generate` | 生成个性化学习路径 |
| `GET` | `/paths/{user_id}` | 获取用户最新学习路径 |
| `POST` | `/paths/adjust` | 调整学习路径任务状态 |
| `GET` | `/knowledge-base` | 获取大学知识库文章列表 |
| `GET` | `/knowledge-base/search` | 搜索知识库文章 |
| `GET` | `/knowledge-base/{article_id}` | 获取知识库文章详情 |
| `POST` | `/exercises/generate` | 生成结构化习题 |
| `POST` | `/qa/analyze` | 智能答疑与结构化学习分析 |
| `POST` | `/graph/dependencies` | 查询知识点依赖链 |
| `GET` | `/graph/related-resources/{knowledge_point}` | 查询关联资源 |
| `POST` | `/graph/visualization` | 获取知识图谱可视化数据 |
| `POST` | `/sessions/new` | 创建聊天会话 |
| `GET` | `/sessions` | 查询聊天会话列表 |
| `GET` | `/sessions/{session_id}` | 查询聊天会话详情 |
| `POST` | `/chat` | 发送聊天消息 |
| `DELETE` | `/sessions/{session_id}` | 删除聊天会话 |

### 2.3 资源服务 `resource-service`

功能说明：

- 提供统一资源库管理能力。
- 支持系统生成资源和外部导入资源统一列表展示。
- 支持从大学知识库页面导入外部课件、讲义、教材或下载包。
- 支持本地资源下载、导出、状态更新、单个删除和批量删除。
- 支持按 `source_type` 批量删除，例如只删除系统生成资源或只删除外部导入课件。

主要接口：

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/resources` | 获取资源列表 |
| `GET` | `/resources/recommendations` | 基于 User-CF、Item-CF、学习画像和热度获取混合推荐 |
| `POST` | `/resources/{resource_id}/interactions` | 记录查看、下载、打开来源等隐式反馈 |
| `POST` | `/resources/import-external` | 导入外部课件资源 |
| `GET` | `/resources/{resource_id}` | 查询单个资源 |
| `POST` | `/resources/{resource_id}/export` | 导出资源 |
| `GET` | `/resources/{resource_id}/download` | 下载资源文件 |
| `PATCH` | `/resources/{resource_id}/status` | 更新资源状态 |
| `DELETE` | `/resources/{resource_id}` | 删除单个资源 |
| `DELETE` | `/resources` | 批量删除资源，可按来源筛选 |

### 2.4 效果评估服务 `evaluation-service`

功能说明：

- 支持在线答题即时判分与反馈。
- 支持批量答题提交。
- 支持阶段报告、月度报告和综合报告。
- 支持错题本、教师视角错题详情、错题清空和补救练习生成。
- 支持 QA 问答中暴露出的错误同步进入错题本。
- 练习错题和 QA 错题会保留 `subject` 字段，便于错题本按科目实时分组。
- 支持学习者画像快照和个性化学习建议生成。

主要接口：

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/evaluation/submit` | 提交单题答题记录并评分 |
| `POST` | `/evaluation/batch_submit` | 批量提交答题记录 |
| `GET` | `/evaluation/stage-report/{user_id}/{chapter_id}` | 生成章节阶段报告 |
| `GET` | `/evaluation/monthly-report/{user_id}` | 生成月度报告 |
| `POST` | `/evaluation/answers` | 提交答题记录 |
| `POST` | `/evaluation/practice/submit` | 提交练习答案并返回即时反馈 |
| `POST` | `/evaluation/mistakes/qa` | 从 QA 分析结果导入错题 |
| `GET` | `/evaluation/reports/stage/{user_id}` | 获取阶段报告摘要 |
| `GET` | `/evaluation/reports/stage/{user_id}/detail` | 获取阶段报告详情 |
| `GET` | `/evaluation/reports/comprehensive/{user_id}` | 获取综合报告摘要 |
| `GET` | `/evaluation/reports/comprehensive/{user_id}/detail` | 获取综合报告详情 |
| `GET` | `/evaluation/mistakes/{user_id}` | 获取错题统计 |
| `GET` | `/evaluation/mistakes/{user_id}/detail` | 获取学生错题本详情 |
| `GET` | `/evaluation/mistakes/{user_id}/teacher-detail` | 获取教师视角错题详情 |
| `DELETE` | `/evaluation/mistakes/{user_id}` | 清空错题本可见记录 |
| `GET` | `/evaluation/mistakes/{user_id}/remedial` | 根据错题生成补救练习 |
| `GET` | `/evaluation/profiles/{user_id}/snapshot` | 获取画像快照 |
| `GET` | `/evaluation/reports/suggestions/{user_id}` | 获取个性化学习建议 |

### 2.5 教师服务 `teacher-service`

功能说明：

- 支持班级列表、班级创建、班级进度概览和学生洞察。
- 支持教师查看单个学生学习详情、错题本和学习报告。
- 支持教学范围设置、学生教学范围查询和班级教学分析。
- 支持作业布置与批改结果提交。

主要接口：

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/teacher/classes` | 获取班级列表 |
| `POST` | `/teacher/classes` | 创建班级 |
| `GET` | `/teacher/classes/{class_id}/progress` | 获取班级进度 |
| `GET` | `/teacher/classes/{class_id}/insights` | 获取班级学生洞察 |
| `GET` | `/teacher/classes/{class_id}/students/{user_id}` | 获取学生学习详情 |
| `GET` | `/teacher/classes/{class_id}/teaching-scopes` | 查询班级教学范围 |
| `POST` | `/teacher/teaching-scopes` | 创建教学范围 |
| `GET` | `/teacher/students/me/teaching-scopes` | 查询当前学生教学范围 |
| `GET` | `/teacher/students/{user_id}/teaching-scopes` | 查询指定学生教学范围 |
| `GET` | `/teacher/classes/{class_id}/teaching-analytics` | 查询班级教学分析 |
| `POST` | `/teacher/homework/assign` | 布置作业 |
| `POST` | `/teacher/homework/{submission_id}/review` | 批改作业 |

### 2.6 系统服务 `system-service`

功能说明：

- 支持角色分配。
- 支持学科列表和学科创建。
- 支持系统配置读取与更新。
- 支持审计日志查询。

主要接口：

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/system/roles/assign` | 分配用户角色 |
| `GET` | `/system/subjects` | 获取学科列表 |
| `POST` | `/system/subjects` | 创建学科 |
| `GET` | `/system/configs` | 获取系统配置 |
| `PUT` | `/system/configs/{key}` | 更新系统配置 |
| `GET` | `/system/logs` | 查询审计日志 |

### 2.7 Web 前端

核心能力：

- 登录、注册、JWT 持久化、请求拦截器、路由守卫和角色分流。
- 学生端支持仪表盘、学习路径、课件学习、课后练习、学习资源、知识库、知识图谱、智能问答、错题本、学习报告、画像分析和个人设置。
- 错题本页面支持按科目分组、科目目录点击直达、错题详情弹窗、错题清空和变式重练。
- 智能问答页面支持将问答暴露出的错误同步到错题本，并携带 `subject` 进入科目分组。
- 学习资源页面整合大学知识库、外部学习入口、官方课件导入和已保存资源管理。
- 教师端支持班级、学生洞察、学生详情、教学范围、教学分析和作业管理。
- 管理员端支持学科、配置、角色和审计日志管理。
- 前端不可连接后端时会明确提示服务不可达，不再统一误报为用户名或密码错误。

默认访问地址：`http://127.0.0.1:5175`

## 3. 近期功能更新

### 3.1 科目化实时错题本

错题本已经从按时间堆叠升级为按科目分组。练习提交、重练提交和 QA 错题同步都会尽量携带 `subject`，历史错题缺少科目时由前端根据知识点和题干关键词兜底推断。

页面交互重点：

- 点击科目目录后直接显示该科目的错题列表。
- 选中科目时错题列表置顶，分析卡片后置。
- 错题详情弹窗展示原题、用户答案、正确答案、AI 解析和建议。
- 变式重练区可基于错题生成补救练习并提交。

### 3.2 QA 错题同步

智能问答返回的结构化分析中包含 `mistake_book_update`。当前端判断 `should_add=true` 时，会调用：

```text
POST /evaluation/mistakes/qa
```

同步字段包括 `subject`、`knowledge_point`、`question_summary`、`wrong_reason`、`correct_approach` 和 `suggested_action`。题干摘要使用 `question_summary`，避免读取不存在字段导致同步失败。

### 3.3 学习资源页与大学知识库合并

学生端 `ResourceView` 将知识库专题、外部学习入口、官方课件导入和本地资源库管理合并到同一页面。学生可按知识点选择专题，查看知识库文章、打开 MOOC/B 站/菜鸟教程等外部入口，导入官方课件，并在统一资源库中打开、导出、删除系统生成资源和外部导入资源。

### 3.4 资源服务落地

`resource-service` 已从骨架推进到可联调资源库业务，支持外部资源导入、下载、导出、状态更新和删除。相关单元测试覆盖外部资源导入、下载地址生成和按来源批量删除。

## 4. 本地启动与联调

推荐使用脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local_services.ps1
```

该脚本会尝试启动：

- `user-service`：`8001`
- `agent-service`：`8002`
- `resource-service`：`8003`
- `evaluation-service`：`8004`
- `teacher-service`：`8005`
- `system-service`：`8006`
- `agent-service-qa-compat`：`8007`
- `web-app`：`5175`

常用本地地址：

- 前端：`http://127.0.0.1:5175`
- 用户服务健康检查：`http://127.0.0.1:8001/health`
- 智能体服务健康检查：`http://127.0.0.1:8002/health`
- 资源服务健康检查：`http://127.0.0.1:8003/health`
- 评价服务健康检查：`http://127.0.0.1:8004/health`

## 5. 当前预留模块

- Java 版后端骨架已经存在，但当前主联调链路仍以 Python 服务为准。
- 移动端 `React Native` 尚未创建。
- 管理员端复杂业务可以继续扩展，但基础系统配置、学科、角色和审计日志已经可联调。

## 6. 文档维护规则

- 新增接口后，先更新代码，再同步 `docs/functionality.md` 和 `README.md`。
- 新增页面后，在文档中补充页面职责、路由入口和主要交互。
- 提交材料中的“作品安装/可执行文件”只保留启动脚本、配置模板和安装说明，不放完整源码、依赖目录、日志、数据库和运行缓存。
