# 系统功能与实现逻辑说明

> 最近更新时间：`2026-07-17`

本文档用于说明本仓库当前已经实现的核心功能、页面入口、后端服务职责、数据流转方式、主要业务逻辑和关键闭环。文档面向项目答辩、交付验收、二次开发和后续维护。

---

## 1. 项目定位

本项目是一个面向学生、教师和管理员的个性化学习多智能体系统。系统以大语言模型为生成与分析能力核心，以学习画像、知识库、知识图谱、答题记录和教师教学范围为约束条件，通过多个智能体协同完成学习路径规划、课件生成、习题生成、智能答疑、错题复盘、学习报告和资源管理。

系统不是单纯的 AI 聊天应用，也不是只生成静态课件的工具。它的核心目标是把“学生画像 -> 学习资源 -> 在线练习 -> 评价反馈 -> 错题本 -> 报告建议 -> 再次个性化生成”串成完整学习闭环。

当前主运行链路：

- 前端：`Vue 3 + TypeScript + Element Plus + Pinia + Vue Router`
- 后端：`FastAPI` 多服务
- 数据层：SQLAlchemy 模型，开发环境可使用 SQLite，生产环境面向 PostgreSQL
- 智能体层：`agent-service` 统一承接多智能体编排、生成、检索、问答和图谱查询
- 评价层：`evaluation-service` 统一承接答题评估、错题本、报告和画像快照

仓库中保留 Java 版骨架和历史迁移资料，但当前可直接联调、可展示、可验收的主线是 Python 服务与 `web-app/` 前端。

---

## 2. 角色与功能边界

### 2.1 学生端

学生端是系统主链路的主要使用入口，负责承接多智能体输出并形成连续学习体验。

核心能力：

- 构建与查看个人学习画像
- 查看学习仪表盘和近期学习状态
- 按教师范围或自主输入生成学习路径
- 阅读个性化课件
- 完成练习和变式重练
- 查看即时反馈、标准答案与解析
- 按科目查看实时错题本
- 查看阶段报告、综合报告和学习建议
- 使用智能问答进行多轮答疑
- 从大学知识库导入官方课件并统一管理学习资源
- 查看知识图谱及知识点依赖关系

### 2.2 教师端

教师端的定位是教学控制与学情观察，不直接替代学生学习流程。

核心能力：

- 管理班级与学生
- 设定教学范围、学习方向、教学目标和课件内容
- 查看班级进度、薄弱知识点和学生洞察
- 查看学生详情、报告和错题本
- 管理教师侧课件和资源审核

### 2.3 管理员端

管理员端用于系统基础配置和运行管理。

核心能力：

- 用户角色分配
- 学科管理
- 系统配置管理
- 审计日志查看

---

## 3. 总体架构

### 3.1 前端结构

前端位于 `web-app/`，主要结构如下：

| 目录/文件 | 作用 |
| --- | --- |
| `src/router.ts` | 路由配置、角色访问控制 |
| `src/stores/auth.ts` | 登录态、用户信息、token 持久化 |
| `src/api/` | 多服务 Axios 客户端和类型定义 |
| `src/components/AppSidebar.vue` | 多角色侧边导航 |
| `src/components/AppTopbar.vue` | 顶部栏与当前页面标题 |
| `src/views/student/` | 学生端核心页面 |
| `src/views/TeacherView.vue` | 教师端工作台 |
| `src/views/AdminView.vue` | 管理端工作台 |

学生端主要页面：

| 页面 | 路由 | 核心功能 |
| --- | --- | --- |
| 学习概览 | `/student/dashboard` | 学习状态、画像摘要、近期记录、入口聚合 |
| 学习路径 | `/student/learning-path` | 生成路径、复用教师范围、路径任务操作 |
| 课件中心 | `/student/courseware` | 阅读个性化课件、目录跳转、导出保存 |
| 练习测评 | `/student/exercise` | 生成练习、答题、提交、即时反馈 |
| 错题本 | `/student/mistakes` | 按科目分类错题、错题详情、变式重练 |
| 知识图谱 | `/student/knowledge-graph` | 知识点依赖图、相关资源、节点详情 |
| 学习报告 | `/student/report` | 阶段报告、综合报告、建议 |
| 智能问答 | `/student/qa` | 多轮对话、学习分析、问答错题同步 |
| 学习资源 | `/student/resources` | 大学知识库、官方课件导入、资源管理 |
| 画像分析 | `/student/profile-analysis` | 画像维度、分析摘要、建议 |

### 3.2 后端服务

| 服务 | 端口 | 核心职责 |
| --- | --- | --- |
| `user-service` | 8001 | 用户注册/登录、JWT、画像维度、画像对话、画像分析 |
| `agent-service` | 8002 | 多智能体协调、课件生成、习题生成、路径规划、问答、知识库、知识图谱 |
| `resource-service` | 8003 | 学习资源导入、查询、导出、下载、状态管理、批量删除 |
| `evaluation-service` | 8004 | 作答评估、错题本、重练题、报告、建议、画像快照 |
| `teacher-service` | 8005 | 班级、学生洞察、教学范围、作业和教师视角数据 |
| `system-service` | 8006 | 角色、学科、配置、日志 |

### 3.3 共享层

`common/` 提供跨服务共享能力：

- SQLAlchemy 数据模型
- 数据库连接与初始化
- 通用 Schema
- 认证与安全工具
- 配置读取

---

## 4. 核心业务闭环

### 4.1 主闭环

```text
学生登录
  -> 完成画像构建
  -> 输入知识点或接收教师教学范围
  -> 多智能体生成学习路径、课件、练习
  -> 学生阅读课件并完成练习
  -> evaluation-service 判分与记录答题
  -> 错题进入对应科目错题本
  -> 报告与建议更新
  -> 学生基于错题生成变式重练
  -> 新答题结果再次回流画像与报告
```

### 4.2 个性化来源

系统个性化不是单次模型输出，而是多源信息共同决定：

- 学习者画像：学习风格、掌握度、能力维度、偏好
- 历史答题记录：正确率、耗时、题型分布
- 错题本：错题知识点、错因、题型、所属科目
- 教师教学范围：知识点范围、学习方向、教学目标、课件内容
- 知识库检索：概念解释、常见误区、应用场景、自测问题
- 知识图谱：前置知识、依赖路径、相关资源
- 智能问答上下文：学生近期提问、模型分析和同步错题

### 4.3 多智能体协作逻辑

`agent-service` 的协调逻辑根据用户意图选择不同智能体：

- 画像智能体：整理用户画像、掌握度和偏好
- 知识库智能体：检索大学知识库与课程资料
- 知识图谱智能体：查询知识点依赖、相关节点和资源
- 路径规划智能体：生成阶段化学习计划
- 资源生成智能体：生成课件、讲义、示例和复习材料
- 习题生成智能体：生成结构化练习题
- QA 智能体：进行答疑、学习诊断和追问建议
- 评价反馈智能体：综合上游结果生成学习反馈

同步执行时，后续智能体会消费前序智能体输出。例如资源生成可以使用画像、知识库检索结果和知识图谱路径；习题生成可以使用课件内容；反馈智能体可以汇总画像、路径、资源、练习和问答结果。

---

## 5. 功能逻辑详解

### 5.1 登录注册与角色分流

功能：

- 注册学生、教师、管理员账号
- 登录后签发 JWT
- 前端保存 token 和用户信息
- 根据角色进入对应工作台
- 路由守卫阻止越权访问

实现逻辑：

1. 用户在登录/注册页提交账号密码。
2. `user-service` 校验账号并返回 token、用户 ID 和角色。
3. 前端 `auth store` 将 token 和用户信息写入 `localStorage`。
4. Axios 请求拦截器自动添加 `Authorization: Bearer <token>`。
5. Vue Router 根据角色重定向：
   - `student` -> 学生工作台
   - `teacher` -> 教师工作台
   - `admin` -> 管理后台

### 5.2 学习画像构建

功能：

- 多维画像采集
- 对话式画像补全
- 画像状态检查
- 画像维度更新和删除
- 画像分析结果展示

实现逻辑：

1. 学生首次进入系统后填写画像表单。
2. 前端将画像维度提交给 `user-service`。
3. 后端持久化到 `user_profiles`。
4. 画像分析服务根据维度生成摘要和建议。
5. 后续路径、课件、练习、问答都会读取画像作为个性化输入。

影响范围：

- 路径难度和每日任务量
- 课件讲解风格与内容深度
- 习题难度分布
- 问答时的解释方式
- 报告中的学习建议

### 5.3 教师教学范围下发

功能：

- 教师设定知识点范围
- 教师填写学习方向、教学目标和课件内容
- 学生端读取教师范围并生成路径或课件

实现逻辑：

1. 教师在教师端维护教学范围。
2. `teacher-service` 保存范围信息。
3. 学生学习路径页读取当前学生可用教学范围。
4. 学生选择范围后，系统将教师课件标题、课件内容和教学目标作为上下文传给路径/资源生成链路。
5. 生成结果既保留教师约束，又结合学生画像做个性化调整。

### 5.4 学习路径生成

功能：

- 根据知识点和画像生成学习路径
- 支持教师教学范围
- 支持任务完成、重置、跳过
- 串联课件、练习和图谱入口

实现逻辑：

1. 前端组装 `subject`、`knowledge_point`、`daily_minutes`、教师范围等参数。
2. 调用 `agent-service` 的路径生成接口。
3. 路径规划智能体结合画像、知识图谱依赖和教师范围生成分阶段路径。
4. 前端展示任务列表和进度。
5. 用户操作任务后调用调整接口更新状态。

路径通常分为：

- 概念建构：理解基础概念和前置知识
- 练习强化：完成例题、自测和错题训练
- 复盘提升：总结错因、补齐薄弱点、形成迁移应用

### 5.5 个性化课件生成与阅读

功能：

- 生成 Markdown 课件
- 支持多个变体
- 展示章节目录
- 支持导出保存
- 支持与学习路径、问答、资源库联动

实现逻辑：

1. 前端传入知识点、学科、画像、教师范围或问答上下文。
2. `agent-service` 生成资源计划，包括难度、目标字数、结构大纲和个性化提示。
3. 资源生成智能体调用 LLM 生成课件内容。
4. 结果写入前端会话状态或资源库。
5. `CoursewareView.vue` 负责解析 Markdown 结构、生成目录、支持阅读和导出。

课件生成约束：

- 不输出空泛提纲
- 尽量包含概念解释、例子、误区、练习和总结
- 与学生画像匹配
- 与教师教学范围保持一致

### 5.6 练习生成与在线测评

功能：

- 生成结构化练习题
- 支持选择题、填空题、判断题、简答题、编程题
- 支持本地草稿
- 提交后显示即时反馈
- 错题自动进入错题本

实现逻辑：

1. 学生选择知识点、难度和题量。
2. `agent-service` 生成练习题。
3. 前端渲染不同题型的答题控件。
4. 学生提交答案。
5. `evaluation-service` 执行判分：
   - 客观题可直接匹配答案
   - 主观题可结合参考答案和 LLM 评估
6. 服务写入 `answer_records`。
7. 如果错误，则生成错题条目并保留科目信息。

### 5.7 错题本与科目化复盘

功能：

- 实时聚合练习和问答产生的错题
- 按科目分类错题
- 左侧科目目录可直接跳转到对应错题列表
- 选中科目后只展示该科目错题，避免用户上下滚动查找
- 查看错题详情、用户答案、正确答案和 AI 解析
- 基于错题生成变式重练
- 支持清空错题本

实现逻辑：

1. 练习提交或问答同步错题时，前端/后端提交 `subject`、`knowledge_point`、题目、答案、解析等字段。
2. `evaluation-service` 将错误记录保存到答题记录或 QA 错题记录中。
3. 错题本页面读取 `/evaluation/mistakes/{user_id}/detail`。
4. 前端按 `subject` 分组；如果历史数据缺少显式科目，则根据知识点和题干关键词推断科目。
5. 页面构建：
   - 科目错题目录
   - 科目分析卡片
   - 当前科目错题列表
   - 错题详情弹窗
   - 变式重练区
6. 点击某个科目时：
   - 设置 `activeSubject`
   - 关闭已打开的错题弹窗
   - 只显示当前科目的分析和错题
   - 将错题列表置于当前视口可见位置

当前科目识别规则：

- 优先使用后端返回的 `subject` 或 `course`
- 如果没有显式科目，则根据知识点和题干关键词推断
- 仍无法判断时归入“未分类科目”

### 5.8 变式重练

功能：

- 从错题本生成补救练习
- 在错题页内直接答题
- 提交后显示标准答案、解析和反馈
- 新的错误继续回流错题本

实现逻辑：

1. 前端调用 `/evaluation/mistakes/{user_id}/remedial`。
2. 后端根据当前活跃错题生成或返回重练题。
3. 前端按题目序号渲染重练题。
4. 学生提交后调用 `/evaluation/practice/submit`。
5. 服务判分并写入新答题记录。
6. 如果仍然错误，错题本刷新并保留科目归类。

### 5.9 智能问答与错题同步

功能：

- 多轮会话
- 会话创建、切换、删除
- 学习型问答与通用问答兼容
- 返回结构化学习分析
- 可联动生成课件和习题
- 可将问答中的错误同步到对应科目错题本

实现逻辑：

1. 前端提交问题、会话 ID、当前知识点和上下文。
2. `agent-service` 保存用户消息。
3. QA 智能体结合知识库、画像、历史会话生成回答。
4. 系统返回：
   - `student_response`
   - `structured_analysis`
   - 知识漏洞
   - 思维误区
   - 路径调整建议
   - 错题本更新建议
   - 可选生成资源
5. 如果结构化分析中存在需要加入错题本的内容，前端可同步到 `evaluation-service`。
6. 同步时保留 `subject`，后续错题本会按该科目实时生成错题列表。

### 5.10 学习报告与建议

功能：

- 阶段报告
- 综合报告
- 学习建议
- 画像快照
- 教师端学生详情复用报告数据

实现逻辑：

1. `evaluation-service` 从 `answer_records` 汇总答题正确率、题型表现、知识点掌握度和错题分布。
2. 阶段报告强调某一阶段或章节表现。
3. 综合报告强调长期趋势、薄弱点、学习策略和下一步建议。
4. 前端报告页按报告类型展示。
5. 教师端查看学生详情时复用同一套报告和错题数据。

### 5.11 知识库与学习资源

功能：

- 查看大学知识库专题
- 搜索课程、概念和关键词
- 查看知识点说明和关联课件
- 导入官方课件到学习资源库
- 管理系统生成资源和官方导入资源
- 支持下载、导出、状态切换、单个删除和批量删除

实现逻辑：

1. `agent-service` 提供知识库列表、搜索和详情。
2. 学生在资源页选择知识库专题。
3. 如果专题有关联外部课件，可通过 `resource-service` 导入。
4. `resource-service` 保存资源元数据、来源、格式、本地文件路径和下载地址。
5. 前端资源页统一展示：
   - 知识库专题列表
   - 当前专题可下载课件
   - 当前知识点已下载课件
   - 全部已保存资源
6. 批量删除支持按来源过滤：
   - `generated`：系统生成资源
   - `external_import`：官方导入课件

### 5.12 知识图谱

功能：

- 查询知识点依赖
- 展示前置知识和后续知识
- 查询相关资源
- 可视化节点和边

实现逻辑：

1. 前端提交知识点。
2. `agent-service` 查询图谱后端。
3. 优先使用 Neo4j 或图谱服务能力。
4. 不可用时可降级到 SQL 表关系和已有资源。
5. 前端使用 `vis-network` 渲染交互式图谱。

### 5.13 教师工作台

功能：

- 班级管理
- 教学范围设定
- 学生洞察
- 学生详情
- 作业布置与批改
- 教师课件管理

实现逻辑：

1. 教师进入工作台后读取班级列表和统计。
2. 教师可维护教学范围和课件内容。
3. 学生端路径规划可读取这些范围作为输入。
4. 教师查看学生详情时，系统聚合：
   - 学习画像
   - 答题记录
   - 错题本
   - 阶段报告
   - 综合报告

### 5.14 管理后台

功能：

- 用户角色分配
- 学科管理
- 系统配置
- 审计日志

实现逻辑：

1. 管理员进入后台。
2. `system-service` 提供角色、学科、配置和日志接口。
3. 前端以表单和列表方式展示管理项。

---

## 6. 服务接口总览

### 6.1 `user-service`

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

### 6.2 `agent-service`

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

### 6.3 `evaluation-service`

- `POST /evaluation/submit`
- `POST /evaluation/batch_submit`
- `POST /evaluation/answers`
- `POST /evaluation/practice/submit`
- `POST /evaluation/mistakes/qa`
- `GET /evaluation/stage-report/{user_id}/{chapter_id}`
- `GET /evaluation/monthly-report/{user_id}`
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

### 6.4 `teacher-service`

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

### 6.5 `system-service`

- `POST /system/roles/assign`
- `GET /system/subjects`
- `POST /system/subjects`
- `GET /system/configs`
- `PUT /system/configs/{key}`
- `GET /system/logs`

### 6.6 `resource-service`

- `GET /resources`
- `POST /resources/import-external`
- `GET /resources/{resource_id}`
- `POST /resources/{resource_id}/export`
- `GET /resources/{resource_id}/download`
- `PATCH /resources/{resource_id}/status`
- `DELETE /resources/{resource_id}`
- `DELETE /resources`

---

## 7. 核心数据模型

`common/models/learning.py` 中最关键的模型：

| 模型 | 作用 | 关键字段 |
| --- | --- | --- |
| `User` | 用户账号与角色 | username, password_hash, role |
| `UserProfile` | 学习画像 | mastery_json, learning_style, cognitive_abilities, habits |
| `KnowledgePoint` | 知识点 | name, description, difficulty, importance, subject_id |
| `KnowledgeRelation` | 知识点关系 | from_id, to_id, relation_type |
| `Resource` | 学习资源 | title, type, content, source_type, local_path, download_url |
| `LearningPath` | 学习路径 | user_id, path_data_json, status |
| `LearningTask` | 路径任务 | path_id, task_type, resource_ids, completed |
| `Exercise` | 练习题 | knowledge_point_id, type, difficulty, content, answer |
| `AnswerRecord` | 答题记录 | user_id, exercise_id, user_answer, is_correct, evaluation_json |
| `LearningReport` | 学习报告 | user_id, report_type, content_json |
| `TeachingScope` | 教学范围 | class_id, student_user_id, knowledge_points, courseware_content |
| `ChatSession` | 问答会话 | user_id, title, subject, is_active |
| `ChatMessage` | 会话消息 | session_id, role, content, metadata_json |

关键字段说明：

- `AnswerRecord.evaluation_json`：保存判分详情、解析、建议、错因和科目信息。
- `Resource.content`：既可保存生成内容，也可保存导入资源的元信息。
- `Resource.source_type`：区分 `generated` 与 `external_import`。
- `Resource.local_path` / `download_url`：决定资源是否可下载。
- `UserProfile.mastery_json`：保存知识点掌握度。
- `ChatMessage.metadata_json`：保存模型、检索、结构化分析和生成资源信息。

---

## 8. 前端状态与本地持久化

### 8.1 登录态

- token 和用户信息写入 `localStorage`
- 页面刷新后由 auth store 恢复
- 退出登录时清除本地状态

### 8.2 学习过程状态

前端会根据场景使用 `sessionStorage` 或 `localStorage` 保存短期学习状态：

- 课件生成结果
- 错题本快照
- 重练题状态
- 学习路径中转数据
- 问答会话当前选择

这些本地缓存用于优化页面跳转体验，不替代后端真实数据。需要刷新最新数据时，页面会重新调用对应后端接口。

### 8.3 错题本快照

错题本页会优先展示最近一次快照，随后可手动刷新。快照的作用是：

- 避免页面跳转后立刻空白
- 在服务短暂不可用时保留最近内容
- 支持从练习页、问答页跳转后立即查看错题

---

## 9. 兜底与容错逻辑

系统为了保证开发演示和本地联调稳定，保留了必要容错，但不依赖硬编码内容冒充真实结果。

主要容错点：

- LLM provider 可配置，主模型不可用时切换备用 provider。
- 知识图谱后端不可用时，使用 SQL 关系或已有知识点信息降级展示。
- 错题本详情接口失败时，前端可展示最近快照并提示刷新。
- 资源删除失败时，前端提示错误，不伪造成功。
- 问答生成失败时返回明确错误，不写入错误会话结果。

---

## 10. 启动方式

推荐脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local_services.ps1
```

常用地址：

- 前端：`http://127.0.0.1:5175`
- 用户服务：`http://127.0.0.1:8001/health`
- 智能体服务：`http://127.0.0.1:8002/health`
- 资源服务：`http://127.0.0.1:8003/health`
- 评价服务：`http://127.0.0.1:8004/health`
- 教师服务：`http://127.0.0.1:8005/health`
- 系统服务：`http://127.0.0.1:8006/health`

---

## 11. 验证建议

修改系统功能后，建议至少验证以下链路：

1. 登录后角色路由是否正确。
2. 学生画像是否能读取并影响生成内容。
3. 学习路径是否能生成并进入课件/练习。
4. 练习提交后是否生成反馈。
5. 错题是否进入对应科目错题本。
6. 点击错题本科目目录是否直接显示对应科目列表。
7. 智能问答是否能保留会话并同步错题。
8. 学习资源页是否能搜索、导入、下载、删除资源。
9. 教师端是否能查看学生报告和错题。
10. 管理端基础配置是否能读取和保存。

常用命令：

```powershell
cd web-app
npm run build
```

```powershell
pytest tests/unit/test_evaluation_reports.py -q
```

---

## 12. 维护规则

- 新增页面时，同步补充页面入口、调用接口和数据流。
- 新增接口时，同步补充前端调用点、Schema 和测试。
- 改动错题、报告、问答、资源链路时，优先验证闭环数据是否能回流。
- 不要用硬编码演示数据替代真实服务结果；确需兜底时必须明确提示用户当前展示的是缓存或降级信息。
- 文档中涉及路由、接口、数据字段时，应与代码实际命名保持一致。

