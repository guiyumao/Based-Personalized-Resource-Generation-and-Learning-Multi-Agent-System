# ZhiShu 融合映射与证据矩阵

> 审计日期：2026-10-15。本文记录的是一次有边界的兼容层融合，不代表把两个仓库合并。

## 1. 上游核查

- 仓库：<https://github.com/AbandonS-ED/ZhiShu>
- 分支：`main`
- 核查到的当前 commit：`936a34a905725a58d586501a7b162883f3d59db0`
- 上游公开结构：Next.js 前端、单体 FastAPI 后端、SQLAlchemy async、LangGraph、PostgreSQL/Redis/pgvector/Celery；`backend/app/agents/state.py` 定义共享 `AgentState`，`backend/app/agents/master_agent.py` 定义意图识别、任务规划、Agent 执行、结果聚合和响应生成。
- 许可证：上游根目录文件清单和仓库页面未发现 `LICENSE`/`LICENSE.md`，页面也未标注 SPDX 许可证。故本次不复制其代码、提示词、页面或资源；仅记录设计事实并重新实现兼容行为。
- 上游完成度边界：README/开发进度声称 15 Agent、106 个 pytest 和自习模式，但本次不把这些声明当作当前项目的验收证据；实际可确认的设计以公开源码中的 `AgentState`、`MasterAgent` 和页面结构为准。

## 2. 现状与差距矩阵

| 能力 | 当前项目真实实现 | ZhiShu 真实实现 | 两边优势 | 选择 | 计划改动 | 证据位置 | 验收方式 |
|---|---|---|---|---|---|---|---|
| A 编排与任务闭环 | `CoordinatorWorkflow` 已按画像、图谱、知识库、路径、资源、习题、QA、评估执行；同步执行已有部分失败返回 | `AgentState` 有 task/session/intent/plan/progress/error；`MasterAgent` 按 task plan 串行执行并跳过失败任务 | 当前服务边界、持久化和权限更完整；上游状态字段更明确 | 增强 | 增加任务状态、依赖计划、调用摘要和非法 Agent 拒绝 | `services/agent_service/app/agents/coordinator.py`：`CoordinatorState`、`_analyze_intent`、`_execute_agents`；上游 `backend/app/agents/state.py`、`master_agent.py` | 定向 Coordinator 测试：非法 Agent 不入队；同步任务返回 task state/call metadata |
| B 画像 | `UserProfile` 保存 `mastery_json`、学习风格、认知能力、习惯、分析和六维描述；`PersonalizationService` 使用真实作答快照 | 7 维画像 JSON，每项 score/confidence；画像规则更新与 AI 分析双路径 | 当前主数据和真实答题证据更清晰；上游表达更适合跨 Agent | 合并 | 通过 `common/profile_scoring.py` 输出证据评分；加入时间衰减、证据来源权重和补证据建议；未知维度明确 insufficient，不覆盖六维主数据 | `common/models/learning.py`；`common/profile_scoring.py`；`services/.../personalization.py`；`GET /users/{id}/profile/zhishu` | 冷启动、低样本、重复作答、开放题证据、目标来源、证据 ID 和时间衰减单测 |
| C 推荐 | 已有资源交互表、推荐 API 和 User/Item-CF + 画像/薄弱点/热度的混合实现 | README 声称资源中心和个性化学习包，公开结构显示推荐体验，但未作为本次源码复用依据 | 当前已有持久化交互和教师范围 | 保留 | 本轮不另建推荐器；后续只在固定查询集上比较新策略 | `services/resource_service/app/services/resource_manager.py`：`recommend_resources`；`tests/unit/test_resource_manager.py` | 既有推荐测试；后续补冷启动/范围约束固定样例 |
| D RAG 与引用 | Chroma 持久/HTTP 模式、版本、元数据过滤、词法快速路径、向量检索、缓存和来源字段已存在 | `document_parser → text_chunker → embedding → vector_store.search → reranker` | 当前安全边界、版本化和可回归检索更完整；上游流水线命名清楚 | 保留 | 不引入第二套向量库；继续用现有基准验证排序 | `services/agent_service/app/services/rag.py`：`retrieve_with_metadata`；`benchmarks/`；`tests/unit/test_performance_and_rag.py` | 引用回指真实 chunk；运行现有 RAG 单测和基准 |
| E 内容审核 | `AuditService` 已有规则审核、可选语义审核、passed/rejected/unavailable 和生成重试 | 上游描述 PatternDetector/SourceValidator/LLMValidator 三层校验，6 个 Agent 接入 | 当前审核已接入生成主链路；上游分层命名有参考价值 | 增强 | 文档化风险分层；不把 LLM 审核当绝对真值 | `services/agent_service/app/services/audit_service.py`；`resource_generation.py`；相关单测 | 结构错误、拒绝、审核不可用和重试耗尽测试 |
| F 路径/图谱 | `LearningPathService` 生成和调整路径，Neo4j/SQL 图谱为当前来源，已有历史持久化 | DAG 学习计划、节点状态、60 分解锁和综合测试 | 当前 API/权限/已有学习路径更适合主系统；上游节点体验可参考 | 合并 | 本轮不复制第二套 path 表；在现有路径上继续补依赖/解锁测试 | `learning_path.py`；`neo4j_connector.py`；`tests/unit/test_learning_path_adjustment.py` | 环路/缺依赖/状态迁移/后端解锁回归 |
| G 错题与补救 | QA 能同步错题分析、推荐练习和路径更新；作答记录是事实来源 | 5 类错因、同类题、掌握度更新、SSE 分析 | 上游错因分类更明确；当前错题和答题数据链路更真实 | 暂缓部分合并 | 本轮不新建错题表/Agent；后续把分类作为可选标签并保留置信度 | `services/agent_service/app/services/qa_service.py`；`common/models/learning.py`；`tests/unit/test_qa_service.py` | 需先补过程证据、重复提交和变式题关联测试 |
| H 对话辅导 | QA/chat 已有用户范围、会话持久化、检索和结构化分析；LLM 错误分层已在主链路 | `tutor_agent` 使用 history/context/profile，前端 SSE | 当前权限和服务拆分更强；上游共享 state 更简洁 | 保留并受益于 A/B | 让统一 task state 承载上下文摘要，不改变会话主数据 | `chat_service.py`、`qa_service.py`、`coordinator.py` | 既有 chat/QA/API 单测；真实模型仍需外部 Key |
| I 报告 | 报告数值由 `ReportService` 从真实答题/错题/路径数据确定性汇总，LLM 负责反馈综合 | LLM 报告、趋势分析、缓存表和 Celery | 当前事实来源和权限更适合现有系统 | 保留 | 不复制上游 report 表；沿用现有缓存失效策略 | `services/evaluation_service/app/services/report_service.py`；`tests/unit/test_evaluation_reports.py` | 报告指标与答题事实核对；下游故障不显示为零 |
| J 自习/本地姿态 | 当前项目未发现同等摄像头功能 | TF.js + MoveNet 浏览器本地姿态检测、番茄钟报告 | 上游有完整交互，但引入会增加隐私和前端依赖 | 暂缓 | 本轮不加入摄像头、姿态、情绪或专注排名 | 上游 README/`frontend/src/app/zixi`；当前 `web-app/src` 无对应能力 | 需独立隐私评估、浏览器兼容和用户明确授权后再立项 |
| K 教师/后台观测 | 教师范围、班级、管理员和审计接口已存在；性能 trace 已可记录 | 管理台 Agent 监控为内存计数器、30 秒刷新 | 当前权限范围和脱敏基础更强；上游监控字段直观但重启丢失 | 增强但后置 | 先输出 Coordinator 调用摘要；不新增模拟运营指标 | `teacher_service`、`system_service`、`common/performance.py`；本次 `agent_calls` | 权限/脱敏/重启持久性检查；真实指标不得伪造 |

## 3. 本次实施边界

已实施：

1. `common/profile_scoring.py`：将当前画像事实和真实作答事实按 `zhishu-scoring-v3` 计算为可审计七维行为代理，保留来源、置信度、样本量、证据 ID、窗口、时间衰减和补证据建议。
2. `services/agent_service/app/services/profile_mapping.py`：保留旧调用兼容层，但不再用聚合值伪造其他维度。
3. `services/user_service/app/services/zhishu_profile.py` 和 `/users/{id}/profile/zhishu`：让用户画像 API 也能读取同一评分结果。
4. `ProfileBuilderService`：记录目标/六维事实是用户填写还是对话提取，供学习目标置信度追溯。
5. `CoordinatorState`：增加 task/session、intent 参数、任务计划、进度、错误、中间结果和 Agent 调用摘要字段。
6. 显式 `force_agents` 白名单：未知 Agent 返回 `AGENT_NOT_ALLOWED`，不发布 RabbitMQ 任务。
7. 同步协调返回 `task_id`、`task_state` 和 `agent_calls`；输入摘要只记录字段名/存在性，不记录 Prompt、Token、Authorization 或完整学习内容。
8. 新增评分、映射和白名单回归测试。

未实施：数据库迁移、第二套推荐/RAG/错题/路径表、Next.js 页面移植、摄像头自习模式、真实模型质量宣称和上游代码复制。当前改动不改变已有 API 路径和主数据表，因此没有 Alembic 迁移。
