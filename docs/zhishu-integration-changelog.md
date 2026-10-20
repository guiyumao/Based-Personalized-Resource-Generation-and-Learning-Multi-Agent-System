# ZhiShu 融合变更记录

## 2026-10-15：阶段 0 审计、阶段 1 兼容层与阶段 2 证据评分

### 已完成

- 核对上游 `AbandonS-ED/ZhiShu` 的 `main` commit：`936a34a905725a58d586501a7b162883f3d59db0`。
- 核对上游公开架构：`AgentState` + LangGraph `MasterAgent`、7 维画像、三层内容校验、RAG 流水线、学习计划/错题/自习模式。
- 因上游未发现许可证文件，本次不复制其代码或页面；仅采用重新实现的兼容设计。
- 新增 `services/agent_service/app/services/profile_mapping.py`，输出带 `source`、`confidence`、`evidence_window`、`evidence_summary` 和 `algorithm_version` 的七维兼容视图。
- 更新 `PersonalizationService`，把兼容视图挂到实时画像快照，不覆盖 `profile_dimensions`、`mastery_json`、`learning_style`、`cognitive_abilities`、`habits` 或 `profile_analysis`。
- 更新 `CoordinatorWorkflow`：加入任务 ID/会话 ID、任务计划、依赖摘要、进度、调用版本/耗时/状态/错误码，并拒绝不在白名单的 `force_agents`。
- 为画像、图谱、知识库、习题和评估阶段增加进程内异常隔离；单个 Agent 异常会记录 `AGENT_EXECUTION_FAILED` 或 typed error，并允许兄弟阶段继续，最终返回 `partial`。
- 扩展 `CoordinationResponse`，向后兼容增加 `task_id`、`session_id`、`task_state`、`agent_calls`。
- 新增七维兼容视图、冷启动、未知 Agent 不分发和 Agent 失败隔离测试。
- 新增 `common/profile_scoring.py`，将七维结果升级为 `zhishu-scoring-v2` 证据评分；记录分数、来源、置信度、样本量、证据 ID、时间窗口和解释。
- 增加知识掌握/理解/应用的答题代理评分、重复作答的记忆保持代理、有效耗时稳定性的持续作答代理；没有开放题 rubric 时，想象力保持 `insufficient_evidence`。
- 为用户画像 API 增加 `zhishu_profile` 和 `GET /users/{user_id}/profile/zhishu`，与 Agent Service 共用同一评分实现。
- ProfileBuilderService 记录六维画像事实的来源为 `user_declared` 或 `conversation_extracted`。
- 评分算法升级为 `zhishu-scoring-v3`：加入记录新鲜度衰减、客观/LLM 评分来源权重、来源混合统计、计算参数和 `next_evidence` 补证据建议。

### 数据迁移和接口影响

- Alembic：无。没有新增或改变数据库字段/表。
- 现有接口路径、请求字段保持不变。
- `/coordinate` 响应新增兼容字段；旧客户端只读取原有字段时不受影响。
- 未新增前端页面；现有前端无需迁移即可忽略新增响应字段。

### 验证结果

- `python -m py_compile services/agent_service/app/services/profile_mapping.py services/agent_service/app/services/personalization.py services/agent_service/app/agents/coordinator.py common/schemas/agent.py`：通过。
- `python -m pytest tests/unit/test_zhishu_profile_mapping.py tests/unit/test_coordinator.py tests/unit/test_coordinator_sync_agents.py -q`：`9 passed`。
- `python -m pytest -q`：阶段 2 优化后为 `288 passed, 232 warnings`。
- `ruff check` 覆盖本次修改的 Python 文件和测试：通过。

### 已知限制

- 未运行完整 pytest、完整前端构建、真实 LLM API、PostgreSQL/Neo4j/Chroma 外部服务或浏览器 E2E。
- `agent_calls` 当前记录的是 Coordinator 进程内调用，不是跨服务消费者的最终确认；RabbitMQ 消费确认、重试和持久任务状态仍需单独实现。
- 七维数值是可解释的学习行为代理，不是心理测量；置信度是证据覆盖度启发式，不是经过验证的概率；各维度仍受最少三条证据、题型覆盖和开放题 rubric 限制。
- 上游自习模式、TF.js/MoveNet、Next.js 页面、第二套学习计划/错题表和上游后台没有引入。

## 后续建议（未承诺）

1. 先以固定作答样本补画像映射评测，再决定是否持久化证据快照。
2. 为已有推荐、RAG、审核、路径解锁和错题闭环补齐固定数据集回归，再做算法比较。
3. 若要持久化跨进程 Agent 指标，应设计数据库/事件表和脱敏策略，不能沿用仅内存计数器。
