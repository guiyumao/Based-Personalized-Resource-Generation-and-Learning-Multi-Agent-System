# 系统功能与实现逻辑说明

> 最近更新时间：`2026-06-26`

本文档用于说明本仓库当前已经实现的核心功能、页面入口、后端服务职责、数据流转方式，以及主要实现逻辑。

## 1. 系统概览

本项目是一个面向学生、教师和管理员的个性化学习多智能体系统，当前主运行链路以 `Vue 3 + FastAPI` 为核心，支持：

- 登录注册与角色分流
- 学生学习画像构建
- 学习路径生成与调整
- 课件与练习生成
- 错题本与重练题
- 学习报告与阶段总结
- 智能问答与多轮会话
- 知识库检索与官方课件下载
- 教师班级与教学范围管理
- 管理员基础系统配置

仓库中同时保留了 Java 版骨架，但当前可直接联调的主线仍是 Python 服务。

## 2. 总体架构

### 2.1 前端

前端位于 `web-app/`，主要页面：

- `LoginView.vue` 登录
- `RegisterView.vue` 注册
- `ProfileSetupView.vue` 画像构建
- `student/DashboardView.vue` 学生首页
- `student/LearningPathView.vue` 学习路径
- `student/CoursewareView.vue` 课件学习
- `student/ExerciseView.vue` 练习与自测
- `student/MistakeNotebookView.vue` 错题本
- `student/KnowledgeGraphView.vue` 知识图谱
- `student/ReportView.vue` 学习报告
- `student/QaView.vue` 智能问答
- `student/ResourceView.vue` 资源库与知识库
- `TeacherView.vue` 教师工作台
- `AdminView.vue` 管理后台

### 2.2 后端服务

当前 Python 服务拆分如下：

- `user-service`：用户、画像、登录态
- `agent-service`：协调调度、资源生成、学习路径、练习、问答、知识库
- `evaluation-service`：答题评估、错题本、报告、建议
- `teacher-service`：班级、教学范围、作业、学生洞察
- `system-service`：角色、学科、配置、日志
- `resource-service`：资源库管理、下载、导入、删除、导出

### 2.3 共享层

`common/` 里保存：

- SQLAlchemy 模型
- 通用 API Schema
- 数据库连接与初始化
- 认证与安全工具
- 配置读取

## 3. 关键功能说明

### 3.1 用户认证与角色分流

功能：

- 用户注册
- 用户登录
- JWT 持久化
- 登录态恢复
- 角色路由守卫

实现逻辑：

- 前端把 token 和用户信息存入 `localStorage`
- `web-app/src/stores/auth.ts` 负责恢复、清理和首页路由计算
- `web-app/src/router.ts` 根据 `student`、`teacher`、`admin` 做页面跳转限制
- 后端 `user-service` 负责签发 token、返回用户与画像信息

### 3.2 学生画像构建

功能：

- 多维画像表单填写
- 对话式画像补全
- 画像维度增删改查
- 画像分析状态查看

实现逻辑：

- 画像数据由 `user-service` 持久化
- `ProfileSetupView.vue` 提供交互式采集
- 画像结果影响后续学习路径、课件生成、练习生成、智能问答

### 3.3 学习路径生成

功能：

- 根据知识点和用户画像生成学习路径
- 支持路径调整
- 保留教师下发教学范围的上下文

实现逻辑：

- 前端从教师教学范围或学生输入中组装请求
- `agent-service` 的 `/paths/generate` 生成分阶段路径
- `/paths/adjust` 允许将任务标记为 `complete`、`reset`、`skip`
- 学习路径页会把课件、练习、图谱和教师范围串成一个工作流

### 3.4 课件生成与阅读

功能：

- 生成个性化课件
- 支持多个候选变体
- 展示生成依据、引用片段和个性化提示
- 课件内容可导出和复用

实现逻辑：

- `agent-service` 的 `/resources/generate` 先构造 `generation_plan`
- 生成计划会归一化知识点、推导难度、目标字数、建议大纲和个性化提示
- 返回的正式内容优先展示在前端
- `CoursewareView.vue` 负责阅读、目录跳转、下载保存和本地持久化

### 3.5 练习生成与自测

功能：

- 生成结构化练习题
- 支持多题型组合
- 支持错题重练
- 支持即时反馈

实现逻辑：

- 练习生成依赖课件内容、画像和错题记录
- `agent-service` 负责题目生成
- `evaluation-service` 负责提交判分、记录错题、更新薄弱点
- `ExerciseView.vue` 负责答题流程与本地草稿

### 3.6 错题本与重练题

功能：

- 聚合错题
- 清空错题本
- 从错题生成重练题

实现逻辑：

- 错题记录由 `evaluation-service` 写入
- 前端错题页读取 `/evaluation/mistakes/{user_id}` 和 `/evaluation/mistakes/{user_id}/remedial`
- 清空操作会删除当前用户可见的错题记录

### 3.7 学习报告与建议

功能：

- 阶段报告
- 综合报告
- 学习建议
- 学习画像快照

实现逻辑：

- `evaluation-service` 从真实答题记录汇总统计
- 报告结果同时给学生端和教师端使用
- 学生首页会把报告、建议、错题和资源推荐拼成最近学习活动

### 3.8 智能问答与连续会话

功能：

- 支持多轮对话
- 支持会话创建、列表、详情、删除
- 支持答疑时生成分析、习题和课件

实现逻辑：

- `agent-service` 维护 `chat_sessions` 与 `chat_messages`
- 问答接口 `/qa/analyze` 会返回学生回答、结构化分析、上下文片段、置信度、以及可选的资源和习题
- 前端 `QaView.vue` 根据会话上下文渲染问答记录和系统生成卡片

### 3.9 知识库与资源库

功能：

- 查询知识库专题
- 搜索知识点
- 下载官方课件
- 保存后统一管理
- 资源导出、状态切换、删除

实现逻辑：

- 知识库数据由 `agent-service` 提供
- 官方课件导入后交给 `resource-service`
- `resource-service` 用 `Resource` 表管理资源元数据，并在内容里记录导入来源和本地文件路径
- 删除资源时会同时删除数据库记录和已下载文件
- 当前资源页支持按 `generated` 和 `external_import` 分别批量删除

### 3.10 教师工作台

功能：

- 班级管理
- 教学范围管理
- 学生洞察
- 学生详细报告
- 作业布置与批改

实现逻辑：

- `teacher-service` 提供班级和教学范围接口
- 教师可把课件标题与内容作为教学范围下发
- 学生端学习路径可直接复用教师课件内容
- 教师查看学生详情时会聚合错题、阶段报告和综合报告

### 3.11 管理员后台

功能：

- 角色分配
- 学科管理
- 系统配置
- 日志查询

实现逻辑：

- `system-service` 提供基础管理接口
- 前端 `AdminView.vue` 负责展示和编辑这些系统配置

## 4. 服务接口总览

### 4.1 `user-service`

- `POST /users/register`
- `POST /users/login`
- `GET /users/me`
- `GET /users/{user_id}`
- `GET /users/{user_id}/profile`
- `PUT /users/{user_id}/profile`
- `DELETE /users/{user_id}/profile/dimensions/{dimension_key}`
- `GET /users/{user_id}/profile/status`
- `POST /users/{user_id}/profile/chat`
- `GET /users/{user_id}/profile/dashboard`

### 4.2 `agent-service`

- `POST /agents/coordinate`
- `POST /resources/generate`
- `POST /paths/generate`
- `GET /paths/{user_id}`
- `POST /paths/adjust`
- `POST /exercises/generate`
- `POST /qa/analyze`
- `POST /graph/dependencies`
- `GET /graph/related-resources/{knowledge_point}`
- `POST /graph/visualization`
- `GET /knowledge-base`
- `GET /knowledge-base/search`
- `GET /knowledge-base/{article_id}`

### 4.3 `evaluation-service`

- `POST /evaluation/submit`
- `POST /evaluation/batch_submit`
- `GET /evaluation/stage-report/{user_id}/{chapter_id}`
- `GET /evaluation/monthly-report/{user_id}`
- `POST /evaluation/answers`
- `POST /evaluation/practice/submit`
- `POST /evaluation/mistakes/qa`
- `GET /evaluation/reports/stage/{user_id}`
- `GET /evaluation/reports/stage/{user_id}/detail`
- `GET /evaluation/reports/comprehensive/{user_id}`
- `GET /evaluation/reports/comprehensive/{user_id}/detail`
- `GET /evaluation/mistakes/{user_id}`
- `GET /evaluation/mistakes/{user_id}/detail`
- `GET /evaluation/mistakes/{user_id}/teacher-detail`
- `DELETE /evaluation/mistakes/{user_id}`
- `GET /evaluation/mistakes/{user_id}/remedial`
- `GET /evaluation/profiles/{user_id}/snapshot`
- `GET /evaluation/reports/suggestions/{user_id}`

### 4.4 `teacher-service`

- `GET /teacher/classes`
- `POST /teacher/classes`
- `GET /teacher/classes/{class_id}/progress`
- `GET /teacher/classes/{class_id}/insights`
- `GET /teacher/classes/{class_id}/students/{user_id}`
- `GET /teacher/classes/{class_id}/teaching-scopes`
- `POST /teacher/teaching-scopes`
- `GET /teacher/students/me/teaching-scopes`
- `GET /teacher/students/{user_id}/teaching-scopes`
- `GET /teacher/classes/{class_id}/teaching-analytics`
- `POST /teacher/homework/assign`
- `POST /teacher/homework/{submission_id}/review`

### 4.5 `system-service`

- `POST /system/roles/assign`
- `GET /system/subjects`
- `POST /system/subjects`
- `GET /system/configs`
- `PUT /system/configs/{key}`
- `GET /system/logs`

### 4.6 `resource-service`

- `GET /resources`
- `POST /resources/import-external`
- `GET /resources/{resource_id}`
- `POST /resources/{resource_id}/export`
- `GET /resources/{resource_id}/download`
- `PATCH /resources/{resource_id}/status`
- `DELETE /resources/{resource_id}`
- `DELETE /resources`

## 5. 核心数据模型

`common/models/learning.py` 中最关键的表：

- `User`：用户账号
- `UserProfile`：学习者画像
- `KnowledgePoint`：知识点
- `Resource`：学习资源
- `LearningPath`：学习路径
- `LearningTask`：路径任务
- `Exercise`：练习题
- `AnswerRecord`：答题记录
- `LearningReport`：学习报告
- `TeachingScope`：教师教学范围
- `ChatSession`：智能问答会话
- `ChatMessage`：会话消息

字段理解：

- `Resource.content` 同时承载生成内容和导入资源元数据
- `Resource.local_path` / `download_url` 决定是否可下载
- `UserProfile.mastery_json` 保存知识点掌握情况
- `ChatMessage.metadata_json` 保存模型、检索和附加信息

## 6. 主要实现逻辑

### 6.1 请求流

1. 前端根据角色进入不同工作台。
2. 用户输入知识点、题目或问题。
3. `agent-service` 根据场景做协调、生成、检索或答疑。
4. `evaluation-service` 处理作答结果和学习反馈。
5. `resource-service` 统一管理资源下载与删除。
6. `teacher-service` 和 `system-service` 提供管理端能力。

### 6.2 个性化的来源

个性化不是单点决策，而是多源合成：

- 学习者画像
- 历史答题记录
- 错题本
- 教师教学范围
- 知识库检索结果
- 近期学习路径状态

### 6.3 资源删除逻辑

资源删除分两类：

- 单个删除：按 `resource_id` 删除数据库记录，并删除本地下载文件
- 批量删除：按 `source_type` 过滤后一次性删除

这能保证：

- 系统生成资源和官方导入资源可以分别清理
- 已下载文件不会残留
- 前端不再用循环删除伪装批量删除

### 6.4 答疑逻辑

答疑页会：

- 记录多轮对话
- 优先返回可读的讲解文本
- 同时返回结构化分析
- 可选生成习题和课件卡片

### 6.5 学习路径与课件联动

学习路径页不是孤立页面，它会：

- 读取教师教学范围
- 调用路径生成接口
- 触发课件生成
- 再把练习入口和知识图谱入口串起来

## 7. 启动方式

推荐脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local_services.ps1
```

常用地址：

- 前端：`http://127.0.0.1:5175`
- 用户服务：`http://127.0.0.1:8001/health`
- 智能体服务：`http://127.0.0.1:8002/health`

## 8. 维护建议

- 新增页面时，同步补充对应服务接口和数据流。
- 新增接口时，优先补充前端调用点和测试。
- 资源、问答、报告这三条链路是系统最重要的闭环，改动时应优先验证。

