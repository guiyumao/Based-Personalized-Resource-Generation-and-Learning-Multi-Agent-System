# 小智任务可靠性修复验收记录

更新：2026-10-19（Asia/Shanghai）。范围为现有 AssistantTask、CoordinatorWorkflow、数据库队列与独立 Worker。

## 实际问题和修复

1. 原失活检测只看 `updated_at`，阈值写死为 30 分钟，没有独立心跳或执行所有权。现在记录 `worker_id`、`execution_attempt`、`heartbeat_at`、`started_at`、`next_attempt_at`；条件更新领取任务，心跳自行检查任务期限和取消等待期限，无需用户轮询。过期心跳不能续租，旧 Worker 不能更新已失去所有权的任务结果。
2. 协调器只能在 Agent 边界识别取消，模型返回后和生成器写入前缺少保护。现在课件/练习模型调用前后检查执行权，数据库写入在同一事务中条件更新任务行取得锁，再保存成果；取消请求与当前事务串行，已经提交的成果保留。资源生成后的图谱同步也先检查取消。
3. 资源、练习生成器各自提交，任务最终结果稍后提交；崩溃可能出现“成果已保存、任务未完成”。现在稳定操作键随失败重试继承原任务 ID，资源键为 `assistant:{root}:resource`，题目键为 `assistant:{root}:exercise:{batch}:{index}`。唯一约束阻止重复提交，重复执行读取既有 ID、正文和题组。题组 `flush()` 和 `commit()` 的唯一键冲突均处理。不同任务和不同批次保持独立。
4. 内部操作标识不能由公共 Coordinator payload 决定；只有持久任务执行器设置可信标识。请求内容变化复用原 `client_request_id` 仍返回冲突。

## 状态和接口

为兼容现有客户端，`PENDING` 对应 QUEUED，`SUCCEEDED` 对应 COMPLETED，继续使用 `RUNNING/FAILED/CANCELLED`，新增运行中取消的 `CANCEL_REQUESTED` 和超时的 `TIMED_OUT`。

- `POST /assistant/tasks/{id}/cancel`：本人 PENDING 立即取消；RUNNING 保持 409。
- `POST /assistant/tasks/{id}/request-cancel`：本人 RUNNING 原子转 CANCEL_REQUESTED；重复调用和终态调用返回当前状态。
- 完成、失败与取消均检查任务状态、Worker 标识和执行代次；成功提交还要求租约和最长执行期限有效。旧 Worker 不得覆盖新结果。
- 前端复用小智任务区，真实调用接口，显示“正在取消”，禁用重复点击，并持续轮询到后端终态。

## 配置与恢复

API 和 Worker 使用相同数据库及配置。Worker 启动命令保持 `python -m services.agent_service.app.services.assistant_worker`，两端设置 `ASSISTANT_TASK_EXECUTION_MODE=worker`。

| 配置 | 默认值 | 作用 |
| --- | --- | --- |
| ASSISTANT_WORKER_HEARTBEAT_SECONDS | 5 秒 | 独立心跳间隔 |
| ASSISTANT_WORKER_STALE_SECONDS | 45 秒 | 失活阈值，实际至少为心跳间隔三倍 |
| ASSISTANT_TASK_MAX_SECONDS | 1800 秒 | 单次执行最长时长，独立于心跳 |
| ASSISTANT_CANCEL_WAIT_SECONDS | 60 秒 | 取消等待上限，超时收回执行权 |
| ASSISTANT_SAFE_RETRY_LIMIT | 2 次 | 只读任务最大自动执行次数 |
| ASSISTANT_SAFE_RETRY_BACKOFF_SECONDS | 5 秒 | 指数退避基数，最大 300 秒 |
| LLM_REQUEST_TIMEOUT_SECONDS | 45 秒 | 沿用现有模型请求超时 |

只对 profile/search/recommend 的 Worker 失活执行限次自动重排队；达到次数或最长时限进入 TIMED_OUT。生成类任务不自动重放模型请求，必须检查成果并显式确认重试；重试继承稳定写入键。取消与重排队通过条件更新互斥。

迁移文件为 `alembic/versions/20261018_0017_assistant_side_effect_keys.py`，前置版本 0016。支持已经由本地 schema bootstrap 补列/索引的情况。共享 SQLite 缺少可信 Alembic 基线，不能直接执行空库迁移；本轮没有修改其 Alembic 版本。需要停止旧版本 API/Worker，再按部署基线升级并启动新版本，避免新旧执行器混跑。

## 修改文件

- 配置/结构：`.env.example`、`common/config.py`、`common/models/learning.py`、`common/schemas/agent.py`、`common/db/bootstrap.py`、上述 0017 迁移。
- 执行链：`services/agent_service/app/services/assistant_tasks.py`、`assistant_worker.py`、新增 `assistant_execution.py`、`services/agent_service/app/agents/coordinator.py`。
- 写入/接口：`services/agent_service/app/services/resource_generation.py`、`exercise_generation.py`、`services/agent_service/app/api/routes/assistant.py`。
- 前端：`web-app/src/api/assistant.ts`、`web-app/src/components/AssistantPet.vue`。
- 回归：`tests/unit/test_assistant_tasks.py`、`tests/integration/test_assistant_worker_process.py`。
- 交接：`DEV_STATE.md`、`docs/xiaozhi-assistant-upgrade.md`、本记录。

## 实际验证

- 隔离临时数据库组合回归：113 passed / 840 warnings；涵盖任务、隐私、资源生成/持久化/权限、协调器、收藏和独立双 Worker 进程。
- 新增真实进程终止恢复测试：1 passed；在任务领取后用 stdout 信号同步终止 Worker，以确定性数据库时间推进模拟租约失效，另一进程恢复只读任务到第二代，只写一条最终消息。
- 最终执行权提交条件补丁后再次运行任务单元与两个独立进程测试：45 passed / 803 warnings（43 项任务单元 + 2 项进程测试）。较早的 113 项组合回归不是最终补丁后的全量重跑；本次补丁影响的任务链已复验。
- 取消测试使用 Event/Barrier 和 SQL 执行事件控制竞态，覆盖排队、Agent 执行期间、模型返回期间、数据库提交期间、重复取消、终态取消、跨用户拒绝。
- 幂等测试覆盖并发资源保存、正文与 ID 一致、服务实例重建后重放、不同批次不合并、题组 flush 冲突复用。
- Worker 测试覆盖正常长任务、心跳失活、过期续租拒绝、无轮询期限处理、旧代结果拒绝、取消等待上限、次数上限及退避。
- `npm run build` 退出码 0；已有第三方构建提示未作为错误。
- 隔离 SQLite 空库升级到 0017、0017→0016→0017、先 bootstrap 后迁移均通过。初次降级发现历史基线缺少 chat_sessions 导致 batch 反射失败，已改用直接删除新增任务列，往返复验通过。

一次未隔离测试在共享 fixture 初始化时遇到并行建表冲突（knowledge_candidates already exists）；随后所有验收命令均指定独立临时 DATABASE_URL。未据此修改其他任务的知识库模块。

## 技术限制和未验证范围

同步 LangChain/DeepSeek 调用没有暴露可安全跨线程中止的请求句柄；本轮阻止后续请求和写入，但不能保证已发出请求立即终止或不计费。线程卡死时不使用强制线程中断；执行权可被收回，另一 Worker 或重启后的 Worker 可领取安全任务，原进程仍需运维终止或等待底层请求超时。

当前任务链没有 GitHub 写操作或任意文件写任务。路径确认和练习评分沿用原持久回执及事务保护。Neo4j 同步使用已有 MERGE；RabbitMQ/外部系统没有通用持久 Outbox，不能宣称任意外部副作用 exactly-once。结果未知的生成操作不自动重放。此次并发验证使用 SQLite；PostgreSQL/MySQL、真实 DeepSeek 取消和登录浏览器点击没有复验，全站端到端也未运行。
