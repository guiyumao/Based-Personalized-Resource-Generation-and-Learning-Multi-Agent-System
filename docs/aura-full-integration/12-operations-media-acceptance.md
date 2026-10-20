# P1 运营台账、多模态与真实模型验收（2026-10-20）

本次在11检查点之后继续实际开发。新增逐调用持久台账、独立进程心跳、执行尝试、真实本地PPTX/SVG/WAV产物、导图编辑及版本历史。总体仍为PARTIAL；本报告不把已完成子链换算为24组或18项标准的100%覆盖。

## 已实现的联动

- 原LLMFactory的同步、异步、流式及链调用，通过模型原始回调写入ModelCall；HTTP之前持久预留调用额度。任务中可记录用户、功能、任务及执行代次。输入/输出/缓存输入取供应商usage；缺失为UNKNOWN，部分缺失为PARTIAL，真实零值保留，缓存输入不重复相加。LIVE与TEST分开；历史调用不回填，未闭合调用保持STARTED。DeepSeek工具HTTP尝试亦接入同一账本，本轮未真实调用工具。
- 管理员 `/admin/usage` 支持日范围、环境、用户、功能、模型、供应商、状态筛选，分页明细与模型/供应商/功能/用户/UTC日分组；未知调用存在时完整合计为UNKNOWN，另外显示已知小计。调用/用户/输出预留限额在同一SQL事务竞争。未核验供应商定价及账单，金额UNKNOWN。
- Assistant/Knowledge Worker注册独立WorkerInstance，线程在空闲或阻塞业务期间定时心跳；正常退出标记STOPPED，强制退出后按超时推断STALE。TaskAttempt保留接入后的每次执行和租约丢失/完成/失败结果；旧进程和历史尝试不伪造回填。管理员任务详情展示已保存阶段和尝试。
- 本地PPTX/SVG/WAV沿用AssistantTask队列和写入租约，绑定LearningContext和资源SHA版本；落库前复核取消、资源归属及版本。产物保存在受控目录，以哈希校验再次读取。跨用户拒绝，资源变化后旧绑定拒绝。PPTX实际解包重读；SVG为安全步骤动画；WAV使用本机Windows Speech、朗读前1600字，未调用外部TTS。非Windows/缺语音引擎明确失败。
- 导图支持节点/标签/父子关系编辑、增删、缩放和保存；服务端验证唯一ID、单根、无环，SQL比较内容和访问状态防止覆盖。保存前后ResourceRevision保留快照，旧上下文409，重新打开后读取新版本。当前历史范围为导图编辑，不宣称所有资源编辑都已有版本历史。
- 修复画像聊天与新知识点习题生成在模型调用期间持有SQLite写锁的问题。先释放业务写事务再调用模型，避免持久台账写入与业务连接互相等待；新知识点在生成结果持久化时创建。

## 文件与数据库

| 文件 | 作用 |
|---|---|
| common/models/operations.py；common/models/media.py；common/models/__init__.py | ModelCall、WorkerInstance、TaskAttempt、ResourceArtifact、ResourceRevision及注册 |
| alembic/versions/20261020_0030_operational_ledger.py；20261020_0031_resource_artifacts.py | 在0029后串联新增五表，保留0026/0027/0028/0029 |
| common/model_usage.py | 真实usage解析、逐调用回调与事务额度预留，不保存提示词/回答/密钥 |
| common/task_attempts.py；common/worker_heartbeat.py | 执行尝试与独立进程心跳 |
| common/dependencies.py | 认证后为当前性能追踪补用户归属 |
| services/agent_service/app/services/llm_factory.py | 所有模型客户端接入回调、流式usage及可配置输出上限 |
| services/agent_service/app/services/deepseek_search.py | 工具每次HTTP尝试写台账 |
| services/agent_service/app/services/assistant_tasks.py | 执行尝试记录及本地artifact任务分支 |
| services/agent_service/app/services/assistant_worker.py；knowledge_worker.py；knowledge_tasks.py | 原Worker注册/心跳及知识任务执行尝试 |
| services/agent_service/app/services/exercise_generation.py；services/user_service/app/services/profile_builder.py | 调用前释放SQLite写锁 |
| services/agent_service/app/services/resource_artifacts.py；scripts/render_local_speech.ps1 | 真实本地PPTX/SVG/WAV渲染、校验与存储 |
| services/agent_service/app/api/routes/model_usage.py；operations.py | 管理员台账、预算、心跳与任务历史读取 |
| services/agent_service/app/api/routes/resource_artifacts.py；resource_revisions.py | 资源产物排队/列表/私有文件、导图CAS保存及历史读取 |
| services/agent_service/app/api/routes/assistant.py；services/agent_service/app/main.py | 原任务重试参数及新增路由注册 |
| web-app/src/components/admin/UsageWorkerPanel.vue；TaskOperationsPanel.vue | 真实台账/心跳/任务尝试界面 |
| web-app/src/components/ResourceArtifactPanel.vue；MindmapEditor.vue；views/student/LearningWorkspaceView.vue | 工作区产物生成/播放/下载及导图编辑 |
| pyproject.toml；.env.example | 声明python-pptx依赖及可选额度配置 |
| scripts/audit_shared_schema.py | 只读共享SQLite schema差异核查，不建库/盖章/迁移 |
| scripts/verify_ops_authorized.py；tests/e2e/live_operations_business.py | 有明确授权开关、累计次数/输出预留网关及真实业务验收 |
| tests/unit/test_operational_ledger.py；test_resource_artifacts.py | SDK真实本地协议、零预算、UNKNOWN/零/缓存、权限/心跳/媒体/版本保护 |
| tests/conftest.py；test_agent_routes_use_coordinator.py；test_graph_and_remedial.py；test_learning_path_adjustment.py；test_plan_knowledge_p1.py；test_profile_analysis.py | 旧测试显式隔离知识准入/模型与后台分析用户ID，不在生产绕过门禁 |
| tests/e2e/operations_runtime.py；operations_migration.py；learning_context_migration.py；learning_workspace_runtime.py；run-learning-workspace.mjs | 独立Worker、真实浏览器、媒体播放/下载、迁移及DB读回 |

新增接口还包括 `POST/GET /learning/contexts/{id}/artifacts`、`GET /learning/artifacts/{id}/file`、`PUT /learning/contexts/{id}/mindmap`、`GET /learning/contexts/{id}/resource-history`。资源端点均要求身份及归属，文件校验哈希并禁止公共缓存。

## 验证证据

证据根为 `artifacts/aura-ops-20261020/`。无费用运行器禁dotenv、真实凭证和未声明的出站网络；每个运行目录保存command.json和日志。不同批次有重叠，不相加作为去重总数。

| 检查 | 结果/证据 |
|---|---|
| 全量unit | global-unit-v2：592 passed，2133 warnings，162.05秒，无失败 |
| 初次全量及修复 | global-unit-v1：583 passed /8 failed；正式知识夹具/后台分析ID复用及事务锁边界修复后，fixes-v2的44项定向通过，随后全量v2通过；保留失败日志 |
| 浏览器+独立Worker | browser-final：九组业务通过、pageErrors为空；真实PPTX文件、SVG帧差异、WAV可播放、导图编辑历史、跨用户/旧版本保护、三种宽度、管理员TEST台账与尝试表；真实模型调用0，截图已实际查看 |
| 独立Worker硬退出 | operations-process-result.json：空闲心跳实际推进；仅终止本测试拥有的子进程，之后心跳超时。未终止任何原服务 |
| 数据库 | migration-v1：0029→0031→0029→0031；migration-final：空库至0031，0031→0028→0027→0031，旧用户和笔记保留 |
| 前端 | build-final.log：vue-tsc与Vite退出0，2.89秒；保留既有第三方和动态导入提示 |
| Ruff | 本次12个新增业务/迁移/只读审计Python文件通过；不声称整仓lint通过 |

浏览器生成/问答为受控桩；SDK协议层真实本地HTTP，单独记TEST。不能把这两类证据冒充真实DeepSeek。真实Chroma发布/检索及Worker恢复仍引用11检查点 `artifacts/aura-p1-20261020/documents-real-v1`，本次没有额外外部Search/Fetch。

## 本轮明确授权的真实DeepSeek

用户明确授权Chat最多6次、总输出上限6000 Token；Search/Fetch、外部图片、外部TTS均为0。网关逐次预留输出上限，失败/截断亦计数，SDK自动重试关闭。

| 尝试 | 业务 | HTTP | 输入/输出Token | 结论 |
|---|---|---|---|---|
| 1 | 真实课件服务 | 200 | 1394 /604 | 课件保存并读回 |
| 2 | 真实习题服务 | 200 | 1476 /1000 | JSON被输出上限截断，检测到fallback，不作为生成通过 |
| 3 | 复用课件后重试习题 | 200 | 1476 /1236 | 三题真实模型内容，无fallback，保存并作答入库 |
| 4 | 绑定当前课件的问答API | 200 | 831 /592 | QA返回并保留结果 |

累计4次、输入5177、输出3432；缓存输入2688已包含在输入内。输出保守预留累计6000，停止调用；没有把未用满的实际Token视为自动增加请求额度。请求模型deepseek-chat，响应模型deepseek-flash。`live-authorized-v2`与`live-authorized-v3`是同一个授权账本的续跑，v3汇总包含前2次。v1本地网关鉴权配置失败，外部调用0，修正guard本地Token后继续。

`live-authorized-v3/LIVE_SUMMARY.json` 与 business-result.json 均passed；课件、三题、上下文QA、服务端标准答案评分和画像写入使用真实服务及隔离SQLite。消息总线在此小范围测试被替换，未验收真实RabbitMQ；未覆盖完整付费Coordinator/Worker复合链。QA测试用身份依赖覆盖，故该条台账用户归属为空，不能当作实名生产调用证据；正常JWT归属在浏览器/SDK测试覆盖。实际供应商扣费金额未核验。

## 共享环境与尚未完成

只读结果 `shared-schema-readonly.json`：实际learning_system.db无Alembic版本记录，缺13张表，9张现有表缺字段（包括知识建设租约/许可字段、活动、上下文、台账和产物）。不能假设共享库已经是0029，也不能直接stamp head掩盖差异。当前授权明确禁止直接升级共享库和重启8001–8007/5175；本次遵守，隔离通过不等于共享部署。后续部署要先对备份副本核定历史基线、补齐数据与约束并演练，再执行获准的共享迁移。

| 工作包 | 当前状态与具体剩余 |
|---|---|
| P1-06 | 台账/预算/心跳/尝试子链已实现并隔离验收；日志跨模块统一筛选/任务深链仍需补，金额/历史供应商账单UNKNOWN |
| P1-07 | 仍PARTIAL：原文本生成/草稿审核复用；管理员专用Prompt优化、改写、图文编排、图片Provider配置/明确BLOCKED入口未完整实现 |
| P1-08 | 导图、PPTX、步骤SVG、本机WAV子链通过；真实视频URL验证/发现、外部图片适配、完整图文及全部类型版本历史尚未完成；不是因未授权而把未实现代码归为外部阻塞 |
| P1-09 | 既有上下文笔记/闪卡/画像保留；笔记修改历史/分类、闪卡知识点证据、统一推荐和完整错误题→提案→确认→新资源场景仍待补 |
| P1-10 | unit全量通过、当前浏览器子链通过；18项全部标准、A–E全场景、真实Neo4j/PG、公网及全站性能未全验收 |

恢复入口：P1-07先读 `assistant_tasks._coordinated_result`、原Coordinator及Resource草稿审核；P1-09从 `services/user_service/app/api/routes/study_tools.py` 和 `learning_content_profile.py` 补证据；全站验收对照03原子矩阵补独立用例。本次不自动提交、不清理已有工作树、不写入共享运行库。
