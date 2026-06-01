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
