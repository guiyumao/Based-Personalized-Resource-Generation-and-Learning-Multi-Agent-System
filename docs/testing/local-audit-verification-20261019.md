# 本地核对报告：测试目录文件是否按规格实现

核对日期：2026-10-19（Asia/Shanghai）。核对对象：`docs/testing/` 四份文档（context / matrix / handoff / prompt）与仓库实际测试代码、业务源码。性质：**静态核对 + 隔离环境动态抽验**，不是第三方平台的正式验收结论。

## 一、总结论

| 维度 | 结论 |
| --- | --- |
| 四份测试文档 | 齐全（context 32KB、matrix 88KB、handoff 9.5KB、prompt 148KB），prompt 内嵌完整 context + 36 案矩阵，四份口径一致 |
| 矩阵点名的既有测试入口 | **全部真实存在**（15 个 pytest 文件、2 个进程集成测试、e2e 脚本与 lib/env.mjs、verifier 脚本） |
| 点名测试函数 | 20 个任务链函数 + 2 个进程函数全部存在；38 函数 / 参数化 43 节点，与文档静态计数一致 |
| 22 份源码指纹 | **22/22 SHA256 完全一致** |
| 核心任务链回归（45 节点） | **45 passed / 0 failed（真实运行）** |
| 组合回归（10 文件） | **115 passed / 0 failed（真实运行）** |
| 扩展回归（unit+integration） | **499 passed / 2 failed / 2 skipped**（真实运行） |
| 前端构建 `npm run build` | **通过**（tsc 类型检查 + vite build，88 个产物） |
| 需第三方新建的独立 harness（11 个） | 仓库内不存在——**符合文档设计**：它们是执行方在 RunRoot/harness 的交付物，不是仓库漏文件 |
| 真实 DeepSeek / 浏览器新取消 / PostgreSQL / 共享库迁移 | 本轮未执行（文档本身将其标为需预算/权限/BLOCKED 项） |

## 二、静态核对明细

### 1. 矩阵引用的测试文件（全部存在）

- tests/unit/test_assistant_tasks.py（67KB，38 个测试函数）
- tests/integration/test_assistant_worker_process.py（2 个真实子进程测试）
- tests/unit/ 下：test_agent_public_authz、test_assistant_privacy、test_resource_authz、test_resource_generation、test_structured_resource_generation、test_structured_resource_persistence、test_coordinator、test_coordinator_sync_agents、test_exercise_favorites、test_ai_timeout_handling、test_jwt_algorithm_hardening
- tests/integration/ 下：test_live_llm_resources（live_llm 标记）、test_external_services（external_service 标记）
- tests/e2e/：package.json、lib/env.mjs、run-all.mjs、run-assistant-*.mjs 等；playwright junction 指向 workspace/node_modules（有效）
- scripts/：verify_external_services.py、db_migration_drill.py、verify_knowledge_v83.py、start_local_services.ps1

### 2. 点名关键测试函数（均存在）

test_cancellation_does_not_overwrite_completed_task、test_concurrent_duplicate_requests_create_one_conversation_message_and_task、test_worker_mode_keeps_pending_tasks_durable_and_honors_cancellation、test_running_cancellation_stops_later_agents_and_keeps_saved_results（4 个 Agent 边界参数）、test_assistant_splits_large_exercise_request_into_existing_service_batches、test_model_reply_after_cancellation_stops_later_model_calls、test_cancel_during_failing_call_stays_cancelled、test_cancel_waits_for_inflight_database_commit（真实 SQL 事件 + 线程锁）、test_heartbeat_enforces_expiry_without_status_polling（heartbeat/deadline/cancel_wait 3 参数）、test_worker_retry_limit_and_cancel_wait_have_distinct_terminal_states、test_late_result_cannot_complete_after_task_deadline、test_stale_worker_is_fenced_and_read_only_task_recovers、test_worker_heartbeat_keeps_long_active_task_and_fences_cancelled_write、test_read_only_recovery_respects_backoff、test_failed_generation_retry_requires_explicit_duplicate_risk_confirmation、test_assistant_side_effect_keys_reuse_saved_resource_and_exercises、test_two_agents_concurrently_save_one_resource、test_exercise_flush_conflict_replays_concurrent_winner、test_public_coordinator_payload_cannot_select_assistant_operation_root、test_learning_path_draft_only_replaces_active_path_after_owner_confirms；进程：test_independent_workers_consume_persisted_task_once、test_killed_worker_read_only_task_recovers_in_another_process。

### 3. 指纹与版本

- git HEAD = `05ee287df3f548943fdebdc267109b3fedbe65a2`，与文档一致；工作树 dirty（大量修改/未跟踪），与文档一致。
- 22 份源码 SHA256 逐字一致（config.py、learning.py、assistant.py、assistant_tasks/worker/execution.py、coordinator.py、resource/exercise_generation.py、0017 迁移、两个测试文件、assistant.ts、AssistantPet.vue 等）。

### 4. 发现的偏差（非任务链实现问题）

1. **Alembic head 已漂移**：文档快照 head 为 20261019_0022，当前实际唯一 head 为 **20261019_0025**（新增 0023 active_versions、0024 source_permissions、0025 parent_budgets，均为知识库模块）。文档已预告“用户可能同时开发知识库模块；版本变化时重建基线”——后续正式验收须按 0025 重建基线，MIG-01 的 0017/0022 步骤仍有效但 head 断言要更新。
2. **前端代码已实现新取消流程**（assistant.ts 的 request-cancel；AssistantPet.vue 的 RUNNING→申请取消、PENDING→/cancel 失败回退 request-cancel、CANCEL_REQUESTED 文案、重试副作用确认对话框）；但 **e2e 浏览器脚本零覆盖** request-cancel/CANCEL_REQUESTED/TIMED_OUT，且 run-assistant-retry.mjs 未处理新的确认对话框——与矩阵 UI-01/UI-02 要求“第三方新增 external-assistant-cancel.mjs / external-assistant-ui-errors.mjs”完全吻合。

## 三、动态运行结果（隔离环境，未触付费模型）

- 环境：临时 RunRoot，独立 DATABASE_URL（SQLite 绝对路径），无 provider key，JWT 临时随机，Python 3.12.6 隔离 venv；Node v22.23.2 / Vite 8.0.14（满足 engines）。
- 注：chromadb（hnswlib 需 MSVC 编译）、neo4j、redis、minio、pika、elasticsearch 未装；任务链相关代码均为函数内懒加载，不影响核心收集与运行。
- 核心任务链：45 passed（含双 Worker 真实子进程领取、真实 kill 后恢复，无 45s sleep，用确定性心跳回拨）。
- 组合回归：115 passed（10 文件）。
- 扩展回归：499 passed / 2 skipped（live_llm、external_service 按标记正确跳过，证明 opt-in 闸门有效）/ 2 failed。
- 前端：npm run build 通过，dist 88 文件 3.97 MB。

### 2 项失败（邻接知识图谱模块，非 36 案任务链核心）

- test_graph_performance.py::test_http_endpoint_returns_graph_within_budget：1.12s 超过断言预算 1.0s（本机墙钟敏感，PERF-01 明确禁止把测试阈值当生产 SLA）。
- test_graph_performance.py::test_concurrent_identical_requests_enrich_only_once：8 并发后补全计数为 0 而非 1（后台补全 dispatcher 时序问题，隔离重跑可复现）。
- 两者均不是缺依赖错误，建议开发者按知识图谱模块（DEF-012）独立复现定性；不得据此判定任务链取消/幂等有缺陷，也不能当作已通过。

## 四、36 案当前证据状态（本地视角）

- 已有真实 pytest 覆盖并本地通过：REG-01、API-01、API-02、API-03、CAN-01、CAN-02、CAN-03（已覆盖 4 个 Agent 边界；20 题补批间隙仍需新 harness）、CAN-04、CAN-05（正向；反序需新 harness）、CAN-06、CAN-07、WRK-01、WRK-02（只读；生成类需新 harness）、WRK-03、WRK-04、WRK-05、IDM-01（同进程；跨进程需新 harness）、IDM-02（资源；题组需新 harness）、IDM-03、IDM-05、TXN-01、SEC-01 的 pytest 部分、LLM-01 的超时区分部分。
- 仓库无现成代码、须执行方新建 harness（共 11 个，matrix 明确列出）：STA-01 state_matrix、CAN-03 batch_cancel、CAN-05 cancel_before_write、WRK-06 cancel_recovery_race、IDM-04 post_commit_crash、FLT-01 db_faults、LLM-01 llm_faults、UI-01 external-assistant-cancel.mjs、UI-02 external-assistant-ui-errors.mjs、PERF-01 external_queue_load.py、API-01 api_smoke.py。
- 环境/预算阻塞项：LLM-02（受控真实 DeepSeek，≤3 请求预算）、DB-01（专属 PostgreSQL，含 DROP/CREATE 授权）、MIG-01/02（隔离副本迁移演练，禁动共享库）、UI-01/02 真实登录联动、全站 run-all.mjs。

## 五、结论

矩阵要求的“既有测试线索”在仓库中**真实、完整且可运行**，核心任务链与组合回归在隔离环境全绿；四份文档与源码指纹、测试节点计数互相吻合。尚未完成的部分都被文档明确标注为“第三方执行方新建 harness / 预算与权限阻塞”，不属于仓库漏实现。正式验收仍需按矩阵执行：第三方 harness 新增、真实浏览器与 PostgreSQL、受控 DeepSeek，并在执行时把迁移 head 基线更新到 0025，同时单独排查 2 个知识图谱性能测试。
