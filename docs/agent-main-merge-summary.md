# 智能体功能合并说明

> 文档目的：说明本次将 `agent-core` 分支智能体能力合并到 `main` 主分支时，实际做了哪些修改、保留了哪些实现、为什么这样选。
> 更新时间：`2026-06-01`
> 当前主分支：`main`

## 1. 合并目标

本次不是简单复制 `agent-core` 分支代码到 `main`，而是按以下原则进行能力迁移：

- 功能相同的场景，优先保留 `main` 中测试更稳定、响应更快、前后端集成更完整的实现。
- `agent-core` 中 `main` 还没有的能力，补进 `main`。
- `agent-core` 中思路更好、但技术栈不同的能力，迁移其“业务逻辑和交互设计”，而不是照搬 Java/Spring 代码。
- 所有修改以 `main` 的 Python/FastAPI 多服务架构为主线落地。

## 2. 本次涉及的提交

- `223556c` `Integrate profile chat and learning path flows into main`
- `a21c186` `Stabilize profile chat extraction fallback`
- `7c7f19f` `Integrate agent-core tutoring and resource planning into main`

## 3. 智能体能力修改总览

本次合并后，`main` 主分支新增或增强了以下智能体能力：

1. 学习者画像对话式采集
2. 学习者画像手动修正
3. 学习路径生成结果持久化读取
4. 学习路径任务状态调整
5. 智能答疑结果增加知识依据与置信度
6. 评估服务增加学习建议输出
7. 资源生成增加“生成前分析/规划”能力
8. 前端接入画像对话入口与资源规划请求参数

## 4. 各智能体模块具体修改

### 4.1 学习者画像智能体

来源能力：

- `agent-core` 中的 `ProfileAgentServiceImpl`

合并到 `main` 后新增：

- `POST /users/{user_id}/profile/chat`
  支持通过多轮对话逐步采集学习者画像。
- `PUT /users/{user_id}/profile`
  支持手动修正画像维度。

实际效果：

- 学生不再只能依赖静态表单录入画像。
- 系统可以从自然语言中抽取画像维度。
- 前端可直接从学生工作台进入画像对话流程。

补充优化：

- 增强了画像抽取失败时的 fallback 逻辑，避免对话结果为空时直接失效。

### 4.2 学习路径规划智能体

来源能力：

- `agent-core` 中的 `LearningPathServiceImpl`

合并到 `main` 后新增：

- `GET /paths/{user_id}`
  获取最近一次有效学习路径。
- `POST /paths/adjust`
  支持将学习任务标记为 `complete`、`reset`、`skip`。

实际效果：

- 学习路径不再只是一次性生成。
- 学生完成任务后可以持续推进路径状态。
- 前端能够读取并恢复已生成路径，而不是每次重新生成。

### 4.3 智能答疑智能体

来源能力：

- `agent-core` 中的 `TutorServiceImpl`

合并到 `main` 后增强：

- `POST /qa/analyze`
  在原有“学生可读回答 + 结构化分析”的基础上，新增：
  - `context_snippets`
  - `confidence`

后端具体变化：

- 新增轻量关键词检索逻辑。
- 优先从本地知识库中找最相关主题，再辅助答疑生成。
- fallback 回答也会带上知识依据与置信度。

实际效果：

- 答疑不再是纯生成式黑盒输出。
- 可以看到本次回答参考了哪些知识片段。
- 为后续前端展示“回答依据”提供了结构化数据。

### 4.4 学习评估/分析智能体

来源能力：

- `agent-core` 中的 `AnalyticsServiceImpl`

合并到 `main` 后新增：

- `GET /evaluation/reports/suggestions/{user_id}`

新增输出内容：

- `suggestions`
- `focus_areas`
- `recommended_action`

生成依据：

- 题目正确率
- 最薄弱知识点
- 最薄弱题型
- 平均耗时
- 用户画像中的学习习惯

实际效果：

- 评估服务不再只给阶段报告和综合报告。
- 系统可以直接给出“下一步学什么、先练什么”的建议。

### 4.5 资源生成协调智能体

来源能力：

- `agent-core` 中的 `ResourceCoordinationServiceImpl`

这是本次第三轮合并的重点。

#### 原始问题

`main` 原有资源生成已经可用，但更偏“直接生成”：

- 输入知识点
- 检索上下文
- 结合画像生成课件

缺少 `agent-core` 中“先分析需求，再形成生成计划”的协调层。

#### 合并后新增能力

`POST /resources/generate` 现在增加了显式的：

- `generation_plan`

其中包括：

- `request_summary`
- `knowledge_point`
- `resource_type`
- `resource_style`
- `title_suggestion`
- `suggested_outline`
- `target_word_count`
- `difficulty`
- `personalization_hints`
- `analysis_source`

#### 后端新增的规划逻辑

在 `services/agent_service/app/services/resource_generation.py` 中新增了：

- 请求文本构建
- 知识点归一化
- 资源类型推断
- 难度推断
- 目标字数推断
- 章节大纲生成
- 标题建议生成
- 个性化提示生成
- 规划文本构建

#### 具体提升

- 可以从更自然的请求文本中识别真实需求。
- 同一个知识点会先归一化，再进入生成链路。
- 课件生成不再只依赖固定 prompt，而是先形成显式计划。
- 生成结果可以解释“为什么会按这个结构、难度和字数生成”。

#### 为什么没有照搬异步任务队列

`agent-core` 的资源协调还包含：

- 任务排队
- 状态轮询
- 生成记录表
- 异步执行

本次没有直接迁入 `main`，原因是：

- `main` 当前同步生成链路已稳定可运行。
- 本地测试中当前 `main` 路径更直接，响应链路更短。
- 先迁移“高价值的需求分析能力”，可以在不破坏现有系统稳定性的前提下得到更好效果。

换句话说，本次保留了 `main` 的执行方式，但迁移了 `agent-core` 的协调思路。

## 5. 前端配套修改

本次前端也做了接线，确保新能力可以直接使用。

### 已接入的内容

- 学生端画像对话入口
- 资源生成请求新增 `request_text`
- 资源生成返回类型新增 `generation_plan`

涉及文件：

- `web-app/src/views/StudentView.vue`
- `web-app/src/api/types.ts`

实际效果：

- 前端生成课件时会把“学习目标/自然语言需求”一起传给资源生成智能体。
- 前后端类型已同步，后续可以直接在界面展示生成计划。

## 6. 本次新增/增强的接口清单

### 用户与画像

- `POST /users/{user_id}/profile/chat`
- `PUT /users/{user_id}/profile`

### 学习路径

- `GET /paths/{user_id}`
- `POST /paths/adjust`

### 智能答疑

- `POST /qa/analyze`
  新增返回：`context_snippets`、`confidence`

### 资源生成

- `POST /resources/generate`
  新增返回：`generation_plan`

### 学习评估建议

- `GET /evaluation/reports/suggestions/{user_id}`

## 7. 主要改动文件

### 后端

- `common/schemas/agent.py`
- `services/agent_service/app/services/resource_generation.py`
- `services/agent_service/app/services/qa_service.py`
- `services/agent_service/app/services/knowledge_base.py`
- `services/agent_service/app/api/routes/resources.py`
- `services/evaluation_service/app/services/report_service.py`
- `services/evaluation_service/app/api/routes/reports.py`
- `services/evaluation_service/app/schemas/report.py`

### 前端

- `web-app/src/api/types.ts`
- `web-app/src/views/StudentView.vue`

### 测试

- `tests/unit/test_resource_generation.py`
- `tests/unit/test_qa_service.py`
- `tests/unit/test_evaluation_reports.py`

### 文档

- `README.md`
- `docs/functionality.md`

## 8. 验证结果

本次合并完成后已验证：

- `pytest -q`
  结果：`28 passed`
- `npm run build`
  结果：通过
- 本地服务健康检查通过：
  - `8001`
  - `8002`
  - `8004`
  - `8005`
  - `8006`
  - `5175`
- 实际调用 `POST /resources/generate` 时，已确认响应中存在 `generation_plan`

## 9. 最终结论

这次 `agent-core -> main` 的智能体合并，核心不是“把另一套代码搬过来”，而是：

- 保留 `main` 已经更稳定、更快、更容易联调的主链路；
- 把 `agent-core` 中更有价值的智能体能力迁移过来；
- 尤其补齐了画像对话、学习路径调整、知识依据答疑、学习建议、资源生成规划这些主干能力。

因此，当前 `main` 分支已经具备更完整的多智能体学习支持能力，同时仍保持了原有 Python 多服务架构的可运行性和测试稳定性。
## 10. 评估智能体数据库设计与业务流程补充

本节补充说明“学习效果评估与个性化反馈智能体”在当前 `main` 分支中的数据库结构、核心操作流程以及 E-R 关系，便于后续继续扩展章节报告、月度报告、画像更新与路径调整逻辑。

### 10.1 核心数据表

当前与评估智能体直接相关的数据库表如下：

| 表名 | 作用 | 主键 | 核心字段 / 外键 |
| --- | --- | --- | --- |
| `users` | 平台用户基础信息 | `id` | `username`, `role`, `email`, `created_at` |
| `user_profiles` | 用户画像与知识掌握度 | `user_id` | `user_id -> users.id`, `mastery_json`, `cognitive_abilities`, `habits`, `updated_at` |
| `knowledge_points` | 知识点定义表 | `id` | `name`, `description`, `difficulty`, `importance` |
| `knowledge_relations` | 知识点先后依赖关系 | `id` | `from_id -> knowledge_points.id`, `to_id -> knowledge_points.id`, `relation_type` |
| `resources` | 学习资源表 | `id` | `knowledge_point_id -> knowledge_points.id`, `generated_for_user_id -> users.id` |
| `learning_paths` | 个性化学习路径 | `id` | `user_id -> users.id`, `path_data_json`, `status`, `created_at` |
| `learning_tasks` | 学习路径任务明细 | `id` | `path_id -> learning_paths.id`, `task_type`, `resource_ids`, `deadline`, `completed` |
| `exercises` | 题目主表 | `id` | `knowledge_point_id -> knowledge_points.id`, `type`, `difficulty`, `content`, `answer`, `analysis` |
| `answer_records` | 用户答题记录主表 | `id` | `user_id -> users.id`, `exercise_id -> exercises.id`, `user_answer`, `is_correct`, `time_spent`, `evaluation_json`, `created_at` |
| `learning_reports` | 学习报告表 | `id` | `user_id -> users.id`, `report_type`, `content_json`, `created_at` |
| `profile_conversations` | 画像对话历史 | `id` | `user_id -> users.id`, `role`, `content`, `created_at` |

### 10.2 评估智能体最关键的表

从业务角度看，评估智能体最核心的是以下 4 张表：

1. `exercises`
   存储题目内容、标准答案、参考答案、解析、题型、难度、章节信息等。

2. `answer_records`
   存储每次真实答题记录，是后续阶段报告、月度报告、错题本和掌握度计算的直接数据来源。

3. `user_profiles`
   存储评估智能体计算后的知识点掌握度、历史轨迹、弱点标记、错误模式标签、学习习惯统计等。

4. `learning_reports`
   存储阶段报告与月度综合报告，避免每次前端查看时都完全重新生成。

### 10.3 `answer_records` 表在评估链路中的作用

`answer_records` 是整个评估智能体的数据中心。每次用户答题提交后，系统都会写入一条记录，其中：

- `user_id` 标识是哪位用户提交
- `exercise_id` 标识作答的是哪道题
- `user_answer` 保存用户原始答案
- `is_correct` 保存最终判定结果
- `time_spent` 保存答题耗时
- `created_at` 保存提交时间
- `evaluation_json` 保存本次评估的扩展信息

`evaluation_json` 中会继续保存：

- 题目外部编号
- 关联知识点列表
- 题型与难度
- 本次得分、满分、得分比例
- 评语与建议
- 鼓励语
- 错误模式标签
- 标准答案 / 参考答案
- 题目内容与解析
- 章节编号与章节名称
- 是否使用 LLM 评分

因此，`answer_records` 不只是“做题日志”，而是后续分析的基础事实表。

### 10.4 `user_profiles` 表在评估链路中的作用

`user_profiles` 表中的 `mastery_json` 用于维护“用户 - 知识点”维度的动态掌握度，当前主要包含：

- `score`
  当前掌握度分数，范围 `0-100`
- `recent_accuracy`
  最近题目正确率
- `consecutive_incorrect`
  连续错误次数
- `weak`
  是否被标记为薄弱知识点
- `history`
  掌握度变化历史，用于成长曲线和趋势分析
- `attempt_count`
  该知识点累计作答次数
- `correct_count`
  该知识点累计答对次数
- `last_error_pattern`
  最近一次错误类型
- `error_tags`
  错误模式聚合结果

此外：

- `habits` 记录累计答题数、平均答题时长、最近一次作答时间等
- `cognitive_abilities` 记录最新错误模式、薄弱知识点集合、最近一次反馈摘要等

### 10.5 评估智能体的核心操作流程

#### 1. 单题提交流程

1. 前端调用 `POST /evaluation/submit`
2. 服务接收 `AnswerRecordSubmission`
3. 根据 `exercise_id` 查询 `exercises`
4. 如果题目不存在，则自动创建或补全题目元数据
5. 根据题型进入不同判分流程：
   - 客观题：直接比对 `user_answer` 与 `standard_answer`
   - 主观题 / 编程题：调用 LLM，根据 `reference_answer` 和 `max_score` 评分
6. 生成结构化评估结果：
   - 对错判定
   - 得分与得分比例
   - 简短评语
   - 修改建议
   - 鼓励语
   - 错误模式标签
7. 写入 `answer_records`
8. 更新 `user_profiles.mastery_json`
9. 若识别出薄弱知识点，则发送：
   - `ProfileUpdateEvent`
   - `PathAdjustmentRequest`
10. 返回即时反馈给前端

#### 2. 批量提交流程

1. 前端调用 `POST /evaluation/batch_submit`
2. 后端逐条执行单题评估逻辑
3. 聚合返回：
   - 每道题的评估结果
   - 总提交数
   - 正确题数
   - 整体正确率

#### 3. 阶段报告生成流程

1. 前端调用 `GET /evaluation/stage-report/{user_id}/{chapter_id}`
2. 系统查询该用户在该章节下的全部 `answer_records`
3. 联合 `user_profiles` 聚合知识点掌握情况
4. 统计：
   - 章节答题总数
   - 正确率
   - 用时
   - Top 3 薄弱知识点
   - 各知识点掌握度与错误模式
5. 调用 LLM 生成阶段性学习报告文本
6. 将结果写入 `learning_reports`
7. 返回阶段报告给前端

#### 4. 月度报告生成流程

1. 前端调用 `GET /evaluation/monthly-report/{user_id}`
2. 系统检索最近 30 天的 `answer_records`
3. 统计：
   - 月度涉及章节数
   - 总体正确率
   - 平均每日学习时长
   - 进步最大的知识点
   - 仍需加强的知识点
4. 调用 LLM 生成月度综合评语
5. 将报告写入 `learning_reports`
6. 返回月报给前端

### 10.6 评估智能体 E-R 关系说明

从实体关系上看，评估智能体主要围绕“用户、题目、答题记录、画像、报告、知识点、学习路径”展开。

#### 主要关系

- `users` 与 `user_profiles`
  一对一关系。一个用户对应一份画像。

- `users` 与 `answer_records`
  一对多关系。一个用户可以有多次答题记录。

- `exercises` 与 `answer_records`
  一对多关系。一道题可以被多个用户多次作答。

- `knowledge_points` 与 `exercises`
  一对多关系。一个知识点可以关联多道题。

- `users` 与 `learning_reports`
  一对多关系。一个用户可以生成多份阶段报告或月度报告。

- `users` 与 `learning_paths`
  一对多关系。一个用户可以拥有多条学习路径。

- `learning_paths` 与 `learning_tasks`
  一对多关系。一条路径包含多个任务。

- `knowledge_points` 与 `knowledge_relations`
  自关联关系。知识点之间通过依赖关系形成知识图谱。

### 10.7 E-R 结构图

```text
users
 ├── 1:1 ── user_profiles
 ├── 1:N ── answer_records ── N:1 ── exercises ── N:1 ── knowledge_points
 ├── 1:N ── learning_reports
 ├── 1:N ── learning_paths ── 1:N ── learning_tasks
 └── 1:N ── profile_conversations

knowledge_points
 ├── 1:N ── resources
 └── N:N ── knowledge_relations ── N:N ── knowledge_points
```

### 10.8 面向评估智能体的数据流总结

如果只看评估智能体本身，可以把它理解成下面这条主数据流：

`题目元数据 exercises`
-> `用户真实作答 answer_records`
-> `掌握度与弱点更新 user_profiles`
-> `阶段 / 月度报告 learning_reports`
-> `消息事件推送到画像智能体与路径规划智能体`

换句话说：

- `exercises` 提供题目标准
- `answer_records` 提供真实行为数据
- `user_profiles` 提供长期状态
- `learning_reports` 提供阶段性总结
- RabbitMQ 事件负责把分析结果继续传给其他智能体

这也是当前多智能体教育系统中“学习效果评估与个性化反馈智能体”的核心数据闭环。

## 11. 数据字典表

本节对当前系统中与多智能体学习平台相关的核心数据表字段进行逐项说明，便于后续数据库设计、接口联调、论文撰写与系统维护。

### 11.1 `users`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 用户唯一标识 |
| `username` | String(50) | Unique, Not Null | 用户名 |
| `password_hash` | String(255) | Not Null | 密码哈希值 |
| `role` | String(20) | Not Null | 用户角色，如 `student`、`teacher`、`admin` |
| `email` | String(255) | Nullable | 用户邮箱 |
| `is_active` | Boolean | Default `True` | 用户是否启用 |
| `created_at` | DateTime | Default / Server Default | 账号创建时间 |

### 11.2 `user_profiles`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `user_id` | Integer | PK, FK -> `users.id` | 用户画像主键，同时关联用户表 |
| `mastery_json` | JSON | Default `{}` | 各知识点掌握度、历史记录、弱点标签等 |
| `learning_style` | String(20) | Default `VARK` | 学习风格标签 |
| `cognitive_abilities` | JSON | Default `{}` | 认知能力与错误模式摘要 |
| `habits` | JSON | Default `{}` | 学习行为习惯、平均耗时、累计作答等 |
| `updated_at` | DateTime | Default / On Update | 画像最后更新时间 |

### 11.3 `knowledge_points`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 知识点唯一标识 |
| `name` | String(100) | Not Null | 知识点名称 |
| `description` | Text | Default `""` | 知识点描述 |
| `difficulty` | Integer | Default `1` | 知识点难度等级 |
| `importance` | Integer | Default `1` | 知识点重要度 |
| `subject_id` | Integer | Nullable | 所属学科编号 |

### 11.4 `knowledge_relations`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 关系记录唯一标识 |
| `from_id` | Integer | FK -> `knowledge_points.id` | 起始知识点 |
| `to_id` | Integer | FK -> `knowledge_points.id` | 目标知识点 |
| `relation_type` | String(30) | Not Null | 关系类型，如前置、依赖、拓展 |

### 11.5 `resources`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 资源唯一标识 |
| `type` | String(30) | Not Null | 资源类型，如课件、笔记、练习 |
| `content` | Text | Not Null | 资源正文内容 |
| `format` | String(20) | Default `markdown` | 资源存储格式 |
| `knowledge_point_id` | Integer | FK -> `knowledge_points.id`, Nullable | 关联知识点 |
| `generated_for_user_id` | Integer | FK -> `users.id`, Nullable | 面向的用户 |
| `created_at` | DateTime | Default / Server Default | 资源创建时间 |

### 11.6 `learning_paths`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 学习路径唯一标识 |
| `user_id` | Integer | FK -> `users.id` | 所属用户 |
| `path_data_json` | JSON | Default `{}` | 路径结构、阶段、任务等完整信息 |
| `status` | String(20) | Default `draft` | 路径状态 |
| `created_at` | DateTime | Default / Server Default | 路径创建时间 |

### 11.7 `learning_tasks`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 任务唯一标识 |
| `path_id` | Integer | FK -> `learning_paths.id` | 所属学习路径 |
| `task_type` | String(30) | Not Null | 任务类型，如 `courseware`、`exercise`、`review` |
| `resource_ids` | JSON | Default `[]` | 关联资源 ID 列表 |
| `deadline` | DateTime | Nullable | 任务截止时间 |
| `completed` | Boolean | Default `False` | 是否已完成 |

### 11.8 `exercises`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 题目唯一标识 |
| `knowledge_point_id` | Integer | FK -> `knowledge_points.id` | 主关联知识点 |
| `type` | String(30) | Not Null | 题型，如选择、填空、判断、简答、编程 |
| `difficulty` | Integer | Default `1` | 题目难度等级 |
| `content` | Text | Not Null | 题目正文与扩展元数据 |
| `answer` | Text | Not Null | 标准答案或参考答案 |
| `analysis` | Text | Default `""` | 题目解析 |

### 11.9 `answer_records`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 答题记录唯一标识 |
| `user_id` | Integer | FK -> `users.id` | 作答用户 |
| `exercise_id` | Integer | FK -> `exercises.id` | 对应题目 |
| `user_answer` | Text | Not Null | 用户提交的原始答案 |
| `is_correct` | Boolean | Nullable | 最终判定是否正确 |
| `time_spent` | Integer | Default `0` | 作答耗时，单位秒 |
| `evaluation_json` | JSON | Default `{}` | 评分明细、章节信息、错误模式、建议等 |
| `created_at` | DateTime | Default / Server Default | 答题提交时间 |

### 11.10 `learning_reports`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 报告唯一标识 |
| `user_id` | Integer | FK -> `users.id` | 报告所属用户 |
| `report_type` | String(20) | Not Null | 报告类型，如 `stage`、`monthly`、`comprehensive` |
| `content_json` | JSON | Default `{}` | 报告完整内容 |
| `created_at` | DateTime | Default / Server Default | 报告生成时间 |

### 11.11 `profile_conversations`

| 字段名 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK | 对话记录唯一标识 |
| `user_id` | Integer | FK -> `users.id` | 对应用户 |
| `role` | String(20) | Not Null | 对话角色，如 `user`、`assistant` |
| `content` | Text | Not Null | 对话文本内容 |
| `created_at` | DateTime | Default / Server Default | 对话记录创建时间 |

### 11.12 评估智能体重点扩展字段说明

以下字段是“学习效果评估与个性化反馈智能体”中特别关键的字段：

| 表名 | 字段名 | 关键作用 |
| --- | --- | --- |
| `user_profiles` | `mastery_json` | 保存知识点掌握度、正确率、连续错误、成长历史、弱点标记 |
| `user_profiles` | `habits` | 保存学习行为习惯、累计答题、平均耗时、最近作答时间 |
| `user_profiles` | `cognitive_abilities` | 保存错误模式、薄弱点摘要、最近反馈结论 |
| `answer_records` | `evaluation_json` | 保存即时评分、建议、章节信息、错误模式、是否使用 LLM |
| `learning_reports` | `content_json` | 保存阶段报告和月度报告完整内容 |
| `learning_paths` | `path_data_json` | 保存学习路径结构、阶段与任务状态 |

### 11.13 数据字典与业务流程的对应关系

从业务角度看，各表字段大致对应如下：

- 用户注册与身份认证主要依赖 `users`
- 用户画像构建与掌握度维护主要依赖 `user_profiles`
- 知识点组织与依赖关系主要依赖 `knowledge_points`、`knowledge_relations`
- 题目生成与题目管理主要依赖 `exercises`
- 答题提交、即时反馈、错误模式识别主要依赖 `answer_records`
- 阶段报告与月度报告持久化主要依赖 `learning_reports`
- 路径规划与任务推进主要依赖 `learning_paths`、`learning_tasks`
- 学习资源推荐与资源对齐主要依赖 `resources`

因此，数据字典不仅说明字段本身，也说明了各字段在整个多智能体学习系统中的职责分工。
