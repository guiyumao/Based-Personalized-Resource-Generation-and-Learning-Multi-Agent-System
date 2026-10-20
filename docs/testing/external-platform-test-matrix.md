# 第三方独立测试矩阵与逐项执行规格
日期：2026-10-19。以下均为**待第三方执行**，不是通过结论。源码依据与配置见 external-platform-test-context.md；独立Prompt会嵌入本矩阵。已有测试用作起点，独立补充不得复制实现的同一判断当唯一oracle。

## 风险、执行与公共约定
- P0：越权/隐私、重复业务写、过期Worker写入、终态损坏。P1：取消、领取、恢复、配置和迁移关键正确性。P2：体验/稳定性/性能；P3：纯诊断或文档问题。发现严重度由实际影响定，不按用例等级自动判缺陷等级。
- 每案使用上下文§8隔离环境；既有pytest节点用其tmp_path/fixture，额外harness自己实现隔离DB、User A/B、真实路由依赖替换。除明确真实provider用例外不得持付费凭证。
- 下列 $RunRoot/harness/... 是要求第三方新建的测试产物路径，不是声称仓库已有脚本。平台须按本案算法写出完整断言、执行并保存源码。不能仅报告“设计了测试”；若不具备所需能力，记BLOCKED并给替代证据。
- 现有pytest命令在RepoRoot和已隔离环境执行。首次先collect验证节点存在；若漂移，按真实函数重定位，记录差异。
- 统一证据目录为RunRoot/evidence/{case_id}/：command.txt、环境/源码指纹、stdout-stderr.log、HTTP脱敏记录、before-after.json、JUnit、必要截图/trace及新增测试源码。证据必须标明真实/Mock、数据库类型、进程/线程、时间推进方式。
- 所有时间竞态采用Event/Barrier/IPC/SQL事件，带超时与finally释放；最多允许为了轮询有限间隔，不能以sleep固定秒数作为唯一同步或证明。
- 默认恢复：关闭本案连接、释放Event/事务、还原monkeypatch，终止仅自己登记的PID，保留临时库供复核；不对共享数据执行删除、清空、迁移、reset或批量格式化。
- P0/P1为默认必需验收集。真实provider/PG/全站能力不足时显式协商范围并记阻塞；缺少核心取消/所有权证据不能给PASS。测试窗口预算由委托方确认，矩阵中的负载数量只是实验设计。
- 当前初始状态一律NOT_RUN；执行后只用PASS/FAIL/BLOCKED/NOT_RUN/N/A（后者需适用性依据），另保留SKIPPED但不计PASS。

## 总览
| 编号 | 模块 | 风险 | 独立验证重点 |
| --- | --- | --- | --- |
| ENV-01 | 环境与版本 | P1 | 确保验收对象是当前dirty源码而非旧HEAD，防止测错库/错服务。 |
| REG-01 | 现有回归 | P1 | 对最终工作树重跑组合与邻接回归，不照抄113/45历史结果。 |
| STA-01 | 状态与事务静态审计 | P0 | 独立推导状态转换，寻找丢失终态、非法跳转及旧代覆盖路径。 |
| API-01 | 创建与请求重放 | P0 | 同键同语义只建一个任务/会话/首条消息，异语义冲突。 |
| API-02 | 认证与对象权限 | P0 | 任务查询/取消/重试/确认、资源与题目不越权。 |
| API-03 | 输入与模式兼容 | P1 | 检验真实schema边界、background/worker差异和SSE边界。 |
| CAN-01 | 排队取消 | P1 | 在领取前阻止任务执行。 |
| CAN-02 | 运行中取消合同 | P1 | 验证旧接口409与新申请入口、重复点击和权限。 |
| CAN-03 | 跨Agent传播与分批 | P1 | 覆盖knowledge/resource/exercise/plan各阶段及第二题组。 |
| CAN-04 | 模型调用期间取消（Mock） | P1 | 在外部调用前/中/返回后取消，区分计算与写入。 |
| CAN-05 | 数据库提交竞争 | P0 | 取消与成果事务串行，已提交记录保留且不重复。 |
| CAN-06 | 取消等待与无轮询期限 | P1 | 不依赖用户GET也能收回慢取消执行权。 |
| CAN-07 | 完成/失败/取消终态竞态 | P0 | 已完成结果不可被取消/晚异常覆盖。 |
| WRK-01 | 双进程领取 | P0 | 真实独立Worker竞争不会双重领取。 |
| WRK-02 | Worker真实崩溃恢复 | P1 | 进程被kill后，另一Worker能按安全策略恢复。 |
| WRK-03 | 旧Worker复活与fencing | P0 | 旧执行代次不能续租、写入或提交过期结果。 |
| WRK-04 | 心跳与最长执行时间 | P1 | 活跃长任务不被误当失活，但不能无限执行。 |
| WRK-05 | 重试次数与退避 | P1 | 只读自动恢复有上限，生成重试需确认且根不丢失。 |
| WRK-06 | 取消与恢复同时发生 | P0 | 取消和失活重排队的竞争不复活已取消业务。 |
| WRK-07 | 生命周期与邻接调度 | P1 | 审计新增知识巡检耦合、信号退出、资源释放和饥饿。 |
| IDM-01 | 持久幂等与重启 | P0 | 相同根资源/题组跨实例重放复用有效成果。 |
| IDM-02 | 并发成果保存 | P0 | 两个Agent/Worker相同业务根只落一份成果。 |
| IDM-03 | flush冲突与批次隔离 | P0 | 覆盖commit前flush失败、不同题组批次和危险前缀。 |
| IDM-04 | 保存后崩溃的真实恢复窗口 | P0 | 检验成果commit成功、task终态尚未写时崩溃。 |
| IDM-05 | 内部键注入与语义冲突 | P0 | 公共payload不能冒充内部任务/执行权。 |
| TXN-01 | 路径/计分邻接闭环 | P0 | 本轮改动不导致重复计分或提前覆盖学习路径。 |
| FLT-01 | 数据库故障与资源释放 | P1 | 数据库短暂不可用时不伪造成功或复活旧租约。 |
| LLM-01 | 模型错误与预算（Mock） | P1 | 检查timeout/429/500/断链/非法JSON及审计重试真实行为。 |
| LLM-02 | 受控真实DeepSeek | P1 | 验证真实provider链路与取消后行为，严格区分已发出请求和计费。 |
| UI-01 | 登录浏览器任务闭环 | P1 | 验证真实API/Worker状态能在AssistantPet正确展示并刷新恢复。 |
| UI-02 | 前端故障/多任务/切换 | P1 | 检验轮询中断、超时、取消/领取竞争与历史恢复。 |
| MIG-01 | SQLite迁移/已有数据 | P1 | 验证0017修复及当前完整迁移图，不修改共享基线。 |
| MIG-02 | bootstrap/Alembic交互 | P1 | 检验启动自补结构与正式迁移兼容、重复启动/并发建表风险。 |
| DB-01 | PostgreSQL适用性 | P1 | 验证真实行锁/唯一冲突/租约，并明确MySQL支持边界。 |
| PERF-01 | 稳定性与性能 | P2 | 测队列积压/吞吐/锁等待/心跳负载和资源泄漏，不虚构生产SLA。 |
| SEC-01 | 日志与交付脱敏 | P0 | 保证测试证据不泄露密钥/令牌/真实学习隐私，并审异常路径。 |

## ENV-01 · 环境与版本

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | ENV-01；初始NOT_RUN |
| 2. 测试模块 | 环境与版本 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 确保验收对象是当前dirty源码而非旧HEAD，防止测错库/错服务。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 核对四份文档及源码可访问性。2. 记录git HEAD/status、核心文件SHA256、Python/Node版本。3. 读取实际迁移图和端口映射。4. 从独立数据库启动服务，存OpenAPI与健康响应；核对Worker PID及命令行。 |
| 8. API/执行命令 | git rev-parse HEAD；git status --short --branch；python --version；node --version；python -m alembic heads；GET 各隔离服务 /health 和 /openapi.json |
| 9. 预期结果 | 版本可追溯，迁移唯一head；端口的服务身份正确，API/Worker共用隔离库。 |
| 10. 数据库验证 | SELECT version_num FROM alembic_version；核对数据库绝对路径、表清单；不查询私人数据。 |
| 11. 日志验证 | 每个服务启动日志和本轮PID/命令行（脱敏）；health不是Worker健康证明。 |
| 12. 通过标准 | 版本/哈希/环境映射齐全，所有运行目标仅本轮副本。 |
| 13. 失败标准 | 仅交付HEAD漏未跟踪实现、共享DATABASE_URL、未知旧进程、多个迁移head。 |
| 14. 证据保存 | RunRoot/evidence/ENV-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## REG-01 · 现有回归

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | REG-01；初始NOT_RUN |
| 2. 测试模块 | 现有回归 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 对最终工作树重跑组合与邻接回归，不照抄113/45历史结果。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 在启动任何pytest前设独立DATABASE_URL及禁用付费凭证。2. 收集测试节点。3. 执行上下文§11核心、组合、扩展三组。4. 区分收集失败/失败/skip，记录每条命令的exit code。5. 只保留本次时间与哈希匹配的报告。 |
| 8. API/执行命令 | python -m pytest tests/unit/test_assistant_tasks.py tests/integration/test_assistant_worker_process.py --collect-only -q；按上下文§11三个现有pytest命令执行并生成各自JUnit；npm --prefix web-app run build |
| 9. 预期结果 | 现有断言真实通过，未启用的外部测试标记skip；组合回归在最终版本上完成。 |
| 10. 数据库验证 | 确认tests/conftest autouse bootstrap仅写RunRoot；测试前后共享库不在连接目标中。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 必需集合全部执行且通过，报告数量自洽；构建单独统计。 |
| 13. 失败标准 | 导入/夹具失败当pass、skip计入pass、历史113+45相加、测试修改业务实现掩盖失败。 |
| 14. 证据保存 | RunRoot/evidence/REG-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## STA-01 · 状态与事务静态审计

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | STA-01；初始NOT_RUN |
| 2. 测试模块 | 状态与事务静态审计 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 独立推导状态转换，寻找丢失终态、非法跳转及旧代覆盖路径。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 阅读路由、execute_task、expire_stale_tasks和guard全部写点。2. 为每条UPDATE记录WHERE和commit位置。3. 在独立测试夹具为7种状态分别调用/cancel、/request-cancel、/retry、execute_task。4. 用Event控制成功与取消先后顺序，比较结果摘要。 |
| 8. API/执行命令 | 现有节点 tests/unit/test_assistant_tasks.py::test_cancellation_does_not_overwrite_completed_task；另创建并执行 $RunRoot/harness/test_external_state_matrix.py，逐状态走实际路由而非直接赋期待结果。 |
| 9. 预期结果 | 只有上下文状态表允许转换；PENDING/终态上的request-cancel是返回原状态；已完成结果不被覆盖。 |
| 10. 数据库验证 | 每次状态/owner/attempt/result_json/completed_at前后快照；统计同task助手消息数量。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 所有允许/拒绝路径及竞态均有证据，结果摘要稳定。 |
| 13. 失败标准 | SUCCEEDED被改为CANCELLED/FAILED，CANCEL_REQUESTED被当立即完成，旧代覆盖新结果。 |
| 14. 证据保存 | RunRoot/evidence/STA-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## API-01 · 创建与请求重放

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | API-01；初始NOT_RUN |
| 2. 测试模块 | 创建与请求重放 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 同键同语义只建一个任务/会话/首条消息，异语义冲突。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 保持Worker未启动。2. A用上下文api_smoke创建profile任务并精确重放。3. 相同key改message/action/topic/count/conversation各一次。4. 用Barrier同时发送4份相同请求。5. B复用相同字符串key发自己的合法请求。 |
| 8. API/执行命令 | POST /assistant/chat，payload见上下文§9；python -m pytest tests/unit/test_assistant_tasks.py::test_concurrent_duplicate_requests_create_one_conversation_message_and_task -q |
| 9. 预期结果 | A相同请求同task；更改语义409；B独立任务，不能被A的key合并。 |
| 10. 数据库验证 | 按(user_id,client_request_id)计数1；同会话用户消息/空会话数量；原请求JSON不被覆盖。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 并发4个响应关联同一A任务，合法B任务独立。 |
| 13. 失败标准 | 多任务/多空会话、异payload复用旧结果、跨用户返回同任务。 |
| 14. 证据保存 | RunRoot/evidence/API-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## API-02 · 认证与对象权限

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | API-02；初始NOT_RUN |
| 2. 测试模块 | 认证与对象权限 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 任务查询/取消/重试/确认、资源与题目不越权。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 注册A/B学生；隔离夹具创建教师。2. 对任务所有路由分别无token、过期/伪签名token、B token、A token请求。3. 用B读取A课件/题组并提交评分。4. 教师请求profile/生成动作。5. 确认错误不会泄露A正文。 |
| 8. API/执行命令 | GET /assistant/tasks/{id}；POST同任务/cancel、/request-cancel、/retry、/confirm-path；pytest tests/unit/test_agent_public_authz.py tests/unit/test_assistant_privacy.py tests/unit/test_resource_authz.py -q |
| 9. 预期结果 | 缺失/无效token401；非本人任务404；教师不支持动作403；有token不等于有对象权限。 |
| 10. 数据库验证 | 被拒请求不新增任务/资源/作答/路径，A数据快照不变。 |
| 11. 日志验证 | 只记录脱敏用户标签和HTTP状态，不写Authorization。 |
| 12. 通过标准 | 所有越权尝试被拒且没有副作用或私人正文。 |
| 13. 失败标准 | 越权成功、状态先写后鉴权、伪token被接纳、拒绝返回500或隐私。 |
| 14. 证据保存 | RunRoot/evidence/API-02/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## API-03 · 输入与模式兼容

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | API-03；初始NOT_RUN |
| 2. 测试模块 | 输入与模式兼容 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 检验真实schema边界、background/worker差异和SSE边界。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 测message空/4000/4001、key长度7/8/80/81、count2/3/20/21、未知action、非法附件归属。2. SSE发送资源动作。3. 两个新进程分别background/worker配置做无费用profile任务。4. 错误模式配置启动，捕获真实报错。 |
| 8. API/执行命令 | POST /assistant/chat、POST /assistant/chat/stream；pytest tests/unit/test_assistant_tasks.py::test_worker_mode_keeps_pending_tasks_durable_and_honors_cancellation -q；非法模式调用task_execution_mode()。 |
| 9. 预期结果 | 按真实schema拒绝无效请求；worker无Worker保持PENDING；background可完成；SSE资源动作422。 |
| 10. 数据库验证 | 验证拒绝参数没有写首条消息/任务/附件引用；按mode核对status。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 边界无500/幽灵任务，模式语义可解释。 |
| 13. 失败标准 | 无效输入部分落库、worker API自行执行、SSE请求被当持久资源成功。 |
| 14. 证据保存 | RunRoot/evidence/API-03/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## CAN-01 · 排队取消

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | CAN-01；初始NOT_RUN |
| 2. 测试模块 | 排队取消 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 在领取前阻止任务执行。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. Worker停止，API以worker模式创建profile。2. A/cancel两次。3. 启动Worker --once。4. 查询终态及执行记录。5. 加入Event让取消和领取竞争，按谁先赢分支断言。 |
| 8. API/执行命令 | POST /assistant/tasks/{id}/cancel；python -m services.agent_service.app.services.assistant_worker --once；pytest tests/unit/test_assistant_tasks.py::test_worker_mode_keeps_pending_tasks_durable_and_honors_cancellation -q |
| 9. 预期结果 | 排队取消CANCELLED且completed_at非空；已取消任务不会被领取。若领取先赢，旧接口409。 |
| 10. 数据库验证 | execution_attempt未被已取消任务增加；无agent执行、无助手成果、无资源/题目。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 重复取消幂等，任务留存可查询，不启动业务。 |
| 13. 失败标准 | 只隐藏UI但后台执行、取消后被RUNNING覆盖、重复取消报500。 |
| 14. 证据保存 | RunRoot/evidence/CAN-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## CAN-02 · 运行中取消合同

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | CAN-02；初始NOT_RUN |
| 2. 测试模块 | 运行中取消合同 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 验证旧接口409与新申请入口、重复点击和权限。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 隔离stub在首个Agent设置entered Event并等待release。2. 进入RUNNING后先/cancel。3. A/request-cancel两次，B一次。4. release当前步骤并等终态。5. 比较所有时间及结果。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_running_cancellation_stops_later_agents_and_keeps_saved_results -q；真实API POST /assistant/tasks/{id}/request-cancel |
| 9. 预期结果 | 旧409不改状态；新入口CANCEL_REQUESTED时completed_at仍null；B404；最终CANCELLED。 |
| 10. 数据库验证 | task状态序列、worker/attempt不伪增；已有成果保留，不多写终态消息。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 状态/HTTP均符合兼容合同，取消请求后的后续Agent未启动。 |
| 13. 失败标准 | RUNNING旧入口200、申请时伪装已取消、重复申请覆盖已完成结果。 |
| 14. 证据保存 | RunRoot/evidence/CAN-02/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## CAN-03 · 跨Agent传播与分批

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | CAN-03；初始NOT_RUN |
| 2. 测试模块 | 跨Agent传播与分批 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 覆盖knowledge/resource/exercise/plan各阶段及第二题组。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 独立stub记录每Agent开始/结束。2. 依次在知识检索、课件、首批练习、路径四处阻塞并取消。3. 另测20题首批结束后补批前取消。4. 断言不会发起后续模型、子阶段、图谱同步。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_running_cancellation_stops_later_agents_and_keeps_saved_results tests/unit/test_assistant_tasks.py::test_assistant_splits_large_exercise_request_into_existing_service_batches -q；补充 $RunRoot/harness/test_external_batch_cancel.py |
| 9. 预期结果 | 已提交成果可读；尚未开始的Agent/补批/路径/图谱同步不执行；取消状态优先，partial不掩盖取消。 |
| 10. 数据库验证 | 按根键、批次检查Resource/Exercise记录，未开始批次0行；核对path草案与path_saved。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 四个已有码参数及新增补批间隙均验证通过。 |
| 13. 失败标准 | 取消后启动新Agent/补批，raw partial覆盖cancelled或创建未请求的计划。 |
| 14. 证据保存 | RunRoot/evidence/CAN-03/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## CAN-04 · 模型调用期间取消（Mock）

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | CAN-04；初始NOT_RUN |
| 2. 测试模块 | 模型调用期间取消（Mock） |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 在外部调用前/中/返回后取消，区分计算与写入。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. Runnable/HTTP stub用Event阻塞首个响应并计请求次数。2. 调用前取消应0次。3. 调用中申请取消后放行响应。4. 尝试审计重试/下一变体/练习生成。5. 模型报错与取消同时发生再测。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_model_reply_after_cancellation_stops_later_model_calls tests/unit/test_assistant_tasks.py::test_cancel_during_failing_call_stays_cancelled -q；新增独立HTTP stub不改服务源码 |
| 9. 预期结果 | 调用前取消0次；在途可能1次，后续0次；结果不再保存；最终CANCELLED而非FAILED覆盖。 |
| 10. 数据库验证 | 取消后没有新resource/exercise/分数；保留原已提交记录。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 有provider调用计数与时序，不以计费停止作为断言。 |
| 13. 失败标准 | 在途结束后再重试/写入，宣称取消必定零费用。 |
| 14. 证据保存 | RunRoot/evidence/CAN-04/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## CAN-05 · 数据库提交竞争

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | CAN-05；初始NOT_RUN |
| 2. 测试模块 | 数据库提交竞争 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 取消与成果事务串行，已提交记录保留且不重复。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 写线程设置有效guard、ensure_write_allowed后持锁。2. SQL事件确认取消UPDATE已开始，再release写事务。3. 检验已提交资源及CANCEL_REQUESTED。4. 反序：先取消提交，再进入写guard必须拒绝。5. 重复至少20次并保存每轮task根。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_cancel_waits_for_inflight_database_commit -q；反序独立用例 $RunRoot/harness/test_external_cancel_before_write.py |
| 9. 预期结果 | 取消在锁释放后生效；已成功事务不被撤销；取消先赢则无新成果。 |
| 10. 数据库验证 | 原task状态、资源唯一key计数、事务前后内容SHA；无半组题。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 两种顺序均只出现可解释结果；无线程异常泄漏/未释放锁。 |
| 13. 失败标准 | 取消后未守卫写、覆盖已提交记录、同键多行、用强制线程异常回滚已提交事务。 |
| 14. 证据保存 | RunRoot/evidence/CAN-05/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## CAN-06 · 取消等待与无轮询期限

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | CAN-06；初始NOT_RUN |
| 2. 测试模块 | 取消等待与无轮询期限 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 不依赖用户GET也能收回慢取消执行权。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 用独立配置缩小cancel_wait且保持valid heartbeat。2. 不调用状态查询/人工expire。3. 用可控clock/OneBeat驱动真实_heartbeat期限分支。4. 对重复request-cancel检查updated_at是否被刷新。5. 超时后旧guard写入/提交应拒绝。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_heartbeat_enforces_expiry_without_status_polling tests/unit/test_assistant_tasks.py::test_worker_retry_limit_and_cancel_wait_have_distinct_terminal_states -q |
| 9. 预期结果 | CANCEL_REQUESTED超过等待变CANCELLED；心跳存活不能永久延期；重复取消不重置已有申请。 |
| 10. 数据库验证 | updated_at、heartbeat_at、completed_at时序；超时后写入数量不变。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 无GET触发仍终结，旧Worker无法续租或提交。 |
| 13. 失败标准 | 只能轮询才取消、重复点击无限延后、心跳把取消重置RUNNING。 |
| 14. 证据保存 | RunRoot/evidence/CAN-06/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## CAN-07 · 完成/失败/取消终态竞态

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | CAN-07；初始NOT_RUN |
| 2. 测试模块 | 完成/失败/取消终态竞态 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 已完成结果不可被取消/晚异常覆盖。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 正常完成保存result摘要。2. 请求两个取消入口并模拟晚异常回调。3. 取消与成功CAS分别先赢各一轮。4. 过deadline返回结果再测。5. 检查最终助手消息与task一致。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_cancellation_does_not_overwrite_completed_task tests/unit/test_assistant_tasks.py::test_late_result_cannot_complete_after_task_deadline -q；扩充并发Case |
| 9. 预期结果 | 最终只一个终态；完成先赢保持SUCCEEDED；取消先赢CANCELLED；超deadline不能SUCCEEDED。 |
| 10. 数据库验证 | 任务result_json散列、completed_at、ChatMessage.task_id计数、AgentExecution计数。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 终态互斥且结果一致，不出现旧结果覆盖。 |
| 13. 失败标准 | 同task两条助手终态消息、状态回退、SUCCEEDED/CANCELLED同时被当权威。 |
| 14. 证据保存 | RunRoot/evidence/CAN-07/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## WRK-01 · 双进程领取

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | WRK-01；初始NOT_RUN |
| 2. 测试模块 | 双进程领取 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 真实独立Worker竞争不会双重领取。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 用隔离库持久化一条PENDING profile。2. 启动两个真实Python --once Worker，PID各异，Barrier或现有脚本协调。3. 等两进程退出。4. 同一输入重复10轮，再以N个任务测分配。 |
| 8. API/执行命令 | pytest tests/integration/test_assistant_worker_process.py::test_independent_workers_consume_persisted_task_once -q；python -m services.agent_service.app.services.assistant_worker --once --batch-size 1 |
| 9. 预期结果 | 每个任务只一个有效owner/attempt成功；另一候选可以空跑，不把候选数视为已执行数。 |
| 10. 数据库验证 | execution_attempt、最终消息数1、AgentExecution数与真实Agent匹配，资源/评分无重复。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 多进程实测，不用线程测试代替进程领取。 |
| 13. 失败标准 | 两个owner都提交、漏任务、把batch-size当并发参数。 |
| 14. 证据保存 | RunRoot/evidence/WRK-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## WRK-02 · Worker真实崩溃恢复

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | WRK-02；初始NOT_RUN |
| 2. 测试模块 | Worker真实崩溃恢复 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 进程被kill后，另一Worker能按安全策略恢复。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 等stdout/IPC明确首Worker已领取并进入只读步骤。2. 仅kill本轮PID。3. 推进隔离库持久心跳时间，避免sleep45秒。4. 新Worker --once。5. 再用courseware任务同样故障，不允许自动生成。 |
| 8. API/执行命令 | pytest tests/integration/test_assistant_worker_process.py::test_killed_worker_read_only_task_recovers_in_another_process -q；补生成类独立进程故障注入 |
| 9. 预期结果 | 只读attempt到2并成功；原Worker不能写；生成类TIMED_OUT且不自动调用模型。 |
| 10. 数据库验证 | 崩溃前owner/attempt/heartbeat；恢复后attempt/result/助手消息唯一。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 真实进程终止证据+数据库时序+新进程成功；没有重放未知生成。 |
| 13. 失败标准 | 仅改状态模拟崩溃却声称kill验证、生成类自动重放或重复保存。 |
| 14. 证据保存 | RunRoot/evidence/WRK-02/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 若子进程残留仅终止已登记测试PID，回收所有pipe/thread，不触碰其他Worker。 |

## WRK-03 · 旧Worker复活与fencing

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | WRK-03；初始NOT_RUN |
| 2. 测试模块 | 旧Worker复活与fencing |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 旧执行代次不能续租、写入或提交过期结果。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. Event暂停attempt1。2. 令其租约失效并安全重排队。3. attempt2先提交。4. 放行attempt1，分别尝试模型后检查、resource写、exercise写和最终结果。5. 覆盖worker_id相同但attempt不同。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_stale_worker_is_fenced_and_read_only_task_recovers tests/unit/test_assistant_tasks.py::test_heartbeat_enforces_expiry_without_status_polling -q；独立扩展同worker_id不同代次 |
| 9. 预期结果 | 新结果保持；旧代UPDATE影响0行或抛ExecutionStopped，不能续租复活。 |
| 10. 数据库验证 | 比较owner/attempt/resultSHA/operation keys及消息计数；旧guard写0行。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 不是只拦最终消息，还逐一验证持久化入口。 |
| 13. 失败标准 | 只验status不验代次、过期心跳被更新为now、旧代覆盖新成果。 |
| 14. 证据保存 | RunRoot/evidence/WRK-03/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## WRK-04 · 心跳与最长执行时间

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | WRK-04；初始NOT_RUN |
| 2. 测试模块 | 心跳与最长执行时间 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 活跃长任务不被误当失活，但不能无限执行。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 用有效新心跳+5分钟started_at运行，max>该时长。2. 独立推进心跳过期/总deadline，检查边界相等与下一微秒。3. 检验stale小于3*interval被夹值。4. 老行heartbeat=null/started=null、时钟前后漂移作为兼容风险单独测。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_worker_heartbeat_keeps_long_active_task_and_fences_cancelled_write tests/unit/test_assistant_tasks.py::test_heartbeat_enforces_expiry_without_status_polling -q；边界新增用例 |
| 9. 预期结果 | 心跳正常且未达max保持RUNNING；不同超时原因准确；兼容分支不绕过owner检查。 |
| 10. 数据库验证 | 时间字段、错误码WORKER_INTERRUPTED/TASK_DEADLINE_EXCEEDED；日志超时原因。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 以可控clock而非长sleep判定，边界行为符合源码且无不可解释早超时。 |
| 13. 失败标准 | 把总deadline与心跳混用、正常长任务误杀、wall clock漂移可无限续租且无诊断。 |
| 14. 证据保存 | RunRoot/evidence/WRK-04/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## WRK-05 · 重试次数与退避

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | WRK-05；初始NOT_RUN |
| 2. 测试模块 | 重试次数与退避 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 只读自动恢复有上限，生成重试需确认且根不丢失。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 连续两次只读失活，分别检查PENDING和TIMED_OUT。2. 恢复前next_attempt_at未到时直接execute_task和Worker领取均应拒绝。3. 推进clock到期。4. 多attempt核对指数退避及300秒上限。5. 生成失败retry先false再true，重复相同retry key。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_read_only_recovery_respects_backoff tests/unit/test_assistant_tasks.py::test_worker_retry_limit_and_cancel_wait_have_distinct_terminal_states tests/unit/test_assistant_tasks.py::test_failed_generation_retry_requires_explicit_duplicate_risk_confirmation -q；POST /assistant/tasks/{id}/retry |
| 9. 预期结果 | limit表示总执行次数；生成false409，true新任务，同retry key重放同任务，side_effect_root_task_id不改根。 |
| 10. 数据库验证 | attempt/next_attempt_at/原任务终态/新任务request_json；记录自动与人工重试数。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 无无限自动循环，未到期不领取，重复人工重试不新建任务。 |
| 13. 失败标准 | 错误将limit当额外次数、退避未生效、取消任务可直接retry、重试丢根键。 |
| 14. 证据保存 | RunRoot/evidence/WRK-05/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## WRK-06 · 取消与恢复同时发生

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | WRK-06；初始NOT_RUN |
| 2. 测试模块 | 取消与恢复同时发生 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 取消和失活重排队的竞争不复活已取消业务。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 构造只读RUNNING且接近失活。2. Barrier释放request-cancel与expire_stale_tasks两个独立连接。3. 两种先后顺序与双Worker条件更新各执行20轮。4. 若已重排队，按当前/cancel语义取消PENDING。5. 验证旧owner不能写。 |
| 8. API/执行命令 | 第三方新增并执行 python -m pytest "$RunRoot/harness/test_external_cancel_recovery_race.py" -q；调用真实request_running_task_cancel()/expire_stale_tasks()，禁止固定成功返回 |
| 9. 预期结果 | 合法顺序可为先重排队再取消，或先取消后终结；不得自动复活已确认CANCELLED任务。 |
| 10. 数据库验证 | 每轮task状态时间线、owner/attempt/next_attempt_at和SQL影响行数。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 所有轨迹落在提取状态机内且副作用计数守恒。 |
| 13. 失败标准 | 丢取消请求且无可解释竞争分支、CANCELLED重新PENDING、旧Worker仍提交。 |
| 14. 证据保存 | RunRoot/evidence/WRK-06/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## WRK-07 · 生命周期与邻接调度

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | WRK-07；初始NOT_RUN |
| 2. 测试模块 | 生命周期与邻接调度 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 审计新增知识巡检耦合、信号退出、资源释放和饥饿。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 先空知识计划库运行助手队列。2. 在隔离库构造一条合法测试巡检计划及助手任务。3. 分别令助手长阻塞、知识任务异常、dispatch_due_plans异常。4. 测--once与持续模式、SIGTERM、heartbeat stop/context reset。5. 恢复后队列可继续处理。 |
| 8. API/执行命令 | python -m services.agent_service.app.services.assistant_worker --once；持续模式 --batch-size 1 --poll-interval 2；独立harness注入知识调度异常，先读其真实模型字段 |
| 9. 预期结果 | 异常可诊断；任务不静默遗失；SIGTERM不谎称中止在途同步调用；退出/重启释放可释放资源。 |
| 10. 数据库验证 | assistant_tasks与knowledge_build_tasks分别计数，不混状态；检查未遗留错误owner。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 明确单进程串行限制和长任务处理影响，出现饥饿须报告而非默认通过。 |
| 13. 失败标准 | 知识异常令助手永久停摆、旧心跳线程持连接不退、测错另一套Worker。 |
| 14. 证据保存 | RunRoot/evidence/WRK-07/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## IDM-01 · 持久幂等与重启

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | IDM-01；初始NOT_RUN |
| 2. 测试模块 | 持久幂等与重启 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 相同根资源/题组跨实例重放复用有效成果。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 保存课件及3题，记录ID和正文SHA。2. 关闭session并重建service实例/进程。3. 相同键但不同待生成正文再次保存。4. 再建新根同主题业务。5. 验证只重放相同操作，不合并独立任务。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_assistant_side_effect_keys_reuse_saved_resource_and_exercises -q；独立进程扩展同根重放 |
| 9. 预期结果 | 同根同ID同旧正文，题组完整；新根新ID，不能拿新正文配旧ID。 |
| 10. 数据库验证 | resources/exercises按精确key查询行数1，题目后缀0..2、所有者及内容散列。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 进程/实例重建后仍幂等，不依赖进程内Set。 |
| 13. 失败标准 | 重复记录、旧ID新正文、不完整题组仍返回success、同主题不同根被合并。 |
| 14. 证据保存 | RunRoot/evidence/IDM-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## IDM-02 · 并发成果保存

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | IDM-02；初始NOT_RUN |
| 2. 测试模块 | 并发成果保存 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 两个Agent/Worker相同业务根只落一份成果。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 两个有效执行上下文、独立DB连接，Barrier同时保存相同resource key。2. 两边生成正文不同。3. 检查冲突方返回的是获胜正文。4. 对3题组并发同批再做。5. 在目标数据库上重跑而非只靠SQLite写锁。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_two_agents_concurrently_save_one_resource -q；第三方新增题组并发测试 |
| 9. 预期结果 | 所有返回同持久ID/正文；每题后缀唯一，数量完整；冲突不向客户端泄露500。 |
| 10. 数据库验证 | 索引真实存在、key计数、并发双方返回与DB比对；DB唯一约束不只ORM声明。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 两类成果均无重复，目标DB隔离级别/锁等待记录完整。 |
| 13. 失败标准 | 题组partial重复、唯一冲突未恢复、SQLite通过被泛化为PostgreSQL通过。 |
| 14. 证据保存 | RunRoot/evidence/IDM-02/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## IDM-03 · flush冲突与批次隔离

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | IDM-03；初始NOT_RUN |
| 2. 测试模块 | flush冲突与批次隔离 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 覆盖commit前flush失败、不同题组批次和危险前缀。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 在首次flush前令另一连接提交相同完整题组。2. 原连接继续触发唯一冲突。3. 验证rollback后可读取获胜组。4. 首批0/补批1、不同根生成，断言不合并。5. 构造缺题组、错误owner、前缀包含LIKE通配符的非法来源。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_exercise_flush_conflict_replays_concurrent_winner tests/unit/test_assistant_tasks.py::test_assistant_side_effect_keys_reuse_saved_resource_and_exercises -q；新增前缀/owner反例 |
| 9. 预期结果 | flush和commit冲突均处理；不完整或跨owner安全拒绝；批次独立。 |
| 10. 数据库验证 | 每批精确键列表、总题数、rollback后connection可用；不得只用LIKE大计数作证。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 恢复返回原完整题组且不损坏Session。 |
| 13. 失败标准 | 只捕获commit遗漏flush、部分组误认完成、wildcard误复用其他业务。 |
| 14. 证据保存 | RunRoot/evidence/IDM-03/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## IDM-04 · 保存后崩溃的真实恢复窗口

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | IDM-04；初始NOT_RUN |
| 2. 测试模块 | 保存后崩溃的真实恢复窗口 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 检验成果commit成功、task终态尚未写时崩溃。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 独立Worker子进程stub模型但使用真实持久化。2. 在资源/首批题组commit后通过IPC通知父进程，阻塞task最终提交。3. kill测试PID。4. 令租约失效，生成任务应TIMED_OUT。5. 用户明确确认retry，运行新Worker，检查根继承和成果关联。6. 再模拟commit确认丢失，禁止盲目外部重发。 |
| 8. API/执行命令 | 第三方新增并执行 python -m pytest "$RunRoot/harness/test_external_post_commit_crash.py" -q；实际API POST /assistant/tasks/{id}/retry，confirm_side_effects=true |
| 9. 预期结果 | 不自动重放生成；人工重试后已存成果ID复用，不重复题目/课件；未完成步骤可生成，结果真实关联。 |
| 10. 数据库验证 | 崩溃前/后/重试后key行数、task根/消息/卡片ID，核对DB而非仅UI。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 通过真实子进程和真实commit窗口复现，持久结果无重复。 |
| 13. 失败标准 | 只用抛异常代替进程崩溃却声称已验、丢失关联、原成果重建。 |
| 14. 证据保存 | RunRoot/evidence/IDM-04/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## IDM-05 · 内部键注入与语义冲突

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | IDM-05；初始NOT_RUN |
| 2. 测试模块 | 内部键注入与语义冲突 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 公共payload不能冒充内部任务/执行权。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 公共/agents/coordinate注入assistant_operation_root和batch。2. /assistant/chat与同步生成schema注入assistant_operation_key、worker_id、execution_attempt。3. 同key更改主题/类型/题量及换用户。4. 直接guard伪造owner/attempt。5. 真实模型前用spy检查可信key来源。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_public_coordinator_payload_cannot_select_assistant_operation_root -q；POST /agents/coordinate；POST /assistant/chat；POST /resources/generate（agent服务） |
| 9. 预期结果 | 公共输入被忽略/拒绝且不能选别人的操作根；异语义key409；伪guard无写权限。 |
| 10. 数据库验证 | 请求JSON允许字段、DB根/key、owner；其他用户资源不返回正文。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 最终实际生成调用的key来自可信executor，不能只检查HTTP返回码。 |
| 13. 失败标准 | 用户指定内部root导致复用或覆盖、跨用户读取、无ContextVar分支绕过持久任务保护。 |
| 14. 证据保存 | RunRoot/evidence/IDM-05/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## TXN-01 · 路径/计分邻接闭环

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | TXN-01；初始NOT_RUN |
| 2. 测试模块 | 路径/计分邻接闭环 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 本轮改动不导致重复计分或提前覆盖学习路径。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. plan/combined生成草案，确认前读取原路径。2. 两个连接同时confirm-path。3. 取实际exercise_id提交答案，同client_request_id重放；改答案再发，新key合法重练。4. 检查取消任务的已生成草案仍按真实规则处理。 |
| 8. API/执行命令 | pytest tests/unit/test_assistant_tasks.py::test_learning_path_draft_only_replaces_active_path_after_owner_confirms -q；POST /assistant/tasks/{id}/confirm-path；POST /evaluation/practice/submit（模型见上下文§6） |
| 9. 预期结果 | 无确认不保存；并发确认仅一套路径，path_saved=true；同键答案重放、改答案409，新key一条新作答。 |
| 10. 数据库验证 | LearningPath.tasks_json来源、LearningTask数量；AnswerRecord.receipt、UserProfile.mastery及事件spy次数。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 实际DB证据证明计分/路径幂等；生成SUCCEEDED不等于path_saved。 |
| 13. 失败标准 | 重复作答更新画像或发布事件、草案提前替换路径、客户端correct_answer覆盖服务端题。 |
| 14. 证据保存 | RunRoot/evidence/TXN-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## FLT-01 · 数据库故障与资源释放

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | FLT-01；初始NOT_RUN |
| 2. 测试模块 | 数据库故障与资源释放 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 数据库短暂不可用时不伪造成功或复活旧租约。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 仅测试库：用外部连接持BEGIN IMMEDIATE锁，分短于/长于busy_timeout两组，或stub连接OperationalError。2. 覆盖领取、心跳、成果commit、终态commit。3. 恢复连接，推进期限。4. 检查Session rollback、线程退出/ContextVar reset，执行下一任务。 |
| 8. API/执行命令 | 第三方新增 python -m pytest "$RunRoot/harness/test_external_db_faults.py" -q；SQLite配置实际busy_timeout=30000ms，不能修改共享库做锁注入 |
| 9. 预期结果 | 错误明确、无虚假SUCCEEDED；失活后旧代无权续租，恢复不重复写；其他任务可继续。 |
| 10. 数据库验证 | 故障窗口前后task/成果/消息、事务原子性和连接可用性；记录锁等待耗时。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 每写边界都验证，不只模拟一个SELECT失败。 |
| 13. 失败标准 | 异常处理本身再次DB异常令任务永久RUNNING且无恢复路径、锁未释放、泄漏线程。 |
| 14. 证据保存 | RunRoot/evidence/FLT-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 释放测试事务、关闭连接、还原monkeypatch/网络阻断，仅结束本案PID。 |

## LLM-01 · 模型错误与预算（Mock）

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | LLM-01；初始NOT_RUN |
| 2. 测试模块 | 模型错误与预算（Mock） |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 检查timeout/429/500/断链/非法JSON及审计重试真实行为。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 本地OpenAI兼容stub按固定序列返回429、500、timeout、断链和非JSON。2. 用LLMFactory实际链路统计HTTP次数，不仅patch最终结果。3. 失败后用户取消，再检查重试。4. 检查SDKmax_retries=0与生成审计层MAX_TOTAL_RETRIES区别，练习fallback必须标记真实来源。 |
| 8. API/执行命令 | pytest tests/unit/test_ai_timeout_handling.py -q；第三方新增并执行 $RunRoot/harness/test_external_llm_faults.py；设DEEPSEEK_API_BASE为本轮stub且清除其他provider密钥 |
| 9. 预期结果 | 无无限重试；错误映射可解释；fallback不冒充真实模型；取消后不新增HTTP调用。 |
| 10. 数据库验证 | 资源审核状态/题组audit_reason与API返回一致；失败不留不完整成果。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 每种故障有请求计数/预算/状态证据；不发收费请求。 |
| 13. 失败标准 | 将timeout当“未成功”盲目重放业务写、隐藏fallback、泄露API Key到错误日志。 |
| 14. 证据保存 | RunRoot/evidence/LLM-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## LLM-02 · 受控真实DeepSeek

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | LLM-02；初始NOT_RUN |
| 2. 测试模块 | 受控真实DeepSeek |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 验证真实provider链路与取消后行为，严格区分已发出请求和计费。 |
| 5. 前置条件 | 有受控测试密钥、明确费用/次数上限、可记录provider名称及调用次数；未获预算则此项BLOCKED而不是跑全live套件。 |
| 6. 环境准备 | 独立新进程只配目标DeepSeek，清其他provider key，允许受控外网；MAX_TOTAL_RETRIES=0、变体1、短非私人主题；预算按实际HTTP请求计数。 |
| 7. 具体操作步骤 | 1. 先申明最多3次provider请求，预算一旦到达硬停止。2. 一次最小真实课件成功。3. 第二次在确定模型已发起后取消，保存响应及DB时序。4. 若预算允许才加第三次受控超时，禁止自动重发未知结果。5. 记录模型/基址主机/响应ID与费用可见性。 |
| 8. API/执行命令 | 真实POST /assistant/chat action=courseware；确认RUNNING及发起证据后POST /assistant/tasks/{id}/request-cancel；不默认运行整个 tests/integration/test_live_llm_resources.py |
| 9. 预期结果 | 调用确为DeepSeek；取消后后续Agent/写入停止；在途请求可返回/超时，费用未知如实标注。 |
| 10. 数据库验证 | 实际task/资源key/题目行数和取消时间；若保存先赢，保留记录且说明顺序。 |
| 11. 日志验证 | 仅留脱敏provider请求计数、耗时/ID，禁止密钥或完整Authorization。 |
| 12. 通过标准 | 真实服务证据完整、未超预算，无未授权重试；Mock结果另列。 |
| 13. 失败标准 | 超预算、用Mock冒充真实、把CANCELLED解释为零费用、只看provider配置名称不看实际分支。 |
| 14. 证据保存 | RunRoot/evidence/LLM-02/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## UI-01 · 登录浏览器任务闭环

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | UI-01；初始NOT_RUN |
| 2. 测试模块 | 登录浏览器任务闭环 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 验证真实API/Worker状态能在AssistantPet正确展示并刷新恢复。 |
| 5. 前置条件 | 具备Chromium/Playwright library与隔离用户/四服务/Worker；无浏览器则此项BLOCKED；真实模型不是Mock UI阶段必要依赖。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 从/login真实登录A（不能仅注入localStorage代替登录验收）。2. 打开可拖动小智，发combined，受控Worker模型stub暂停。3. 观察RUNNING并点取消。4. 捕获实际/request-cancel响应和正在取消文案，连点确认无重复请求。5. 释放stub，观察CANCELLED，刷新并读回；核对后端与DB。6. 再跑一次正常完成/草案确认。 |
| 8. API/执行命令 | 现有browser入口 tests/e2e/lib/env.mjs 的loadPlaywright；第三方创建并运行 node $RunRoot/harness/external-assistant-cancel.mjs，按Prompt中的library骨架执行 |
| 9. 预期结果 | 不只停动画：HTTP、任务、卡片一致；按钮请求期间禁用；刷新保留终态，已有成果可访问。 |
| 10. 数据库验证 | GET任务与DB终态、消息卡片ID、资源所有者匹配；截图不代替持久证据。 |
| 11. 日志验证 | pageerror/console error/网络状态+脱敏trace；删除Authorization/cookie/localStorage token后再交付。 |
| 12. 通过标准 | 真实登录与真实后端/Worker的E2E通过；provider使用Mock需注明。 |
| 13. 失败标准 | UI显示已取消但后端RUNNING、刷新丢任务、重复点击多次操作、凭据被截图/HAR泄露。 |
| 14. 证据保存 | RunRoot/evidence/UI-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## UI-02 · 前端故障/多任务/切换

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | UI-02；初始NOT_RUN |
| 2. 测试模块 | 前端故障/多任务/切换 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 检验轮询中断、超时、取消/领取竞争与历史恢复。 |
| 5. 前置条件 | 同UI-01环境；可用page.route故障注入，但与真实E2E结果分开统计。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 取消前GET为PENDING，实际/cancel因领取先赢返回409，验证fallback发request-cancel。2. 注入GET500/401/断网再恢复。3. TIMED_OUT/FAILED展示并重试，生成类确认对话框先拒绝再接受。4. 两会话多任务切换、刷新、关闭面板、卸载登录登出，检查只轮询currentTaskId的限制是否误判其他任务。 |
| 8. API/执行命令 | 新增 node $RunRoot/harness/external-assistant-ui-errors.mjs；参考 AssistantPet.loadSession/refreshTask/cancelCurrentTask/retryFailedTask；不要直接跑旧run-assistant-retry.mjs宣称新对话框通过 |
| 9. 预期结果 | 错误可见且不伪造终态；401按实际路由登录过期；TIMED_OUT停止轮询并可重试；没有卡片串会话。 |
| 10. 数据库验证 | 每个真实task独立状态/会话/根，UI请求错误不更改DB终态。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 任务间隔离、按钮恢复、真实后端状态可重新读取，定时器无泄漏。 |
| 13. 失败标准 | catch任意异常导致误申请取消或吞错、只轮询一个任务却把全部当完成、确认拒绝仍发重试。 |
| 14. 证据保存 | RunRoot/evidence/UI-02/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## MIG-01 · SQLite迁移/已有数据

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | MIG-01；初始NOT_RUN |
| 2. 测试模块 | SQLite迁移/已有数据 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 验证0017修复及当前完整迁移图，不修改共享基线。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 全新隔离迁移库与完整versions树，记录heads。2. upgrade到0016，创建迁移允许的最小非私人历史数据。3. upgrade0017，核对列/唯一约束/数据数目与内容。4. downgrade0016再upgrade0017。5. 另一新库upgrade当前head，核对ORM与DB差异；差异当发现，不自动修表。 |
| 8. API/执行命令 | python -m alembic heads；python -m alembic upgrade 20261018_0016；upgrade 20261018_0017；downgrade 20261018_0016；upgrade 20261018_0017；新库另运行upgrade head |
| 9. 预期结果 | 历史记录保留，新key nullable允许旧记录；新key重复实际失败；head以当前0022图为准，缺表风险有证据。 |
| 10. 数据库验证 | PRAGMA表/索引/FK检查；alembic_version；前后数据SHA和重复键INSERT约束验证。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 两个数据库轨道均验证；不把bootstrap create_all成功混同完整迁移成功。 |
| 13. 失败标准 | 直接对共享库upgrade head、数据损坏、漏唯一约束、只跑0017当作当前head。 |
| 14. 证据保存 | RunRoot/evidence/MIG-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 保留临时迁移库与日志；回退只对本案副本执行，不删除共享DB。 |

## MIG-02 · bootstrap/Alembic交互

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | MIG-02；初始NOT_RUN |
| 2. 测试模块 | bootstrap/Alembic交互 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 检验启动自补结构与正式迁移兼容、重复启动/并发建表风险。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 隔离库升级0016后运行ensure_database_schema两次，再迁移0017。2. 反序：迁移0017后bootstrap。3. 完整head库双API/Worker同时首次启动。4. 断言重复索引/约束和既有内容；记录known chat_sessions历史基线差异。 |
| 8. API/执行命令 | 独立脚本调用common.db.bootstrap.ensure_database_schema()；python -m alembic upgrade 20261018_0017；两个测试进程同库启动，禁止锁住共享库 |
| 9. 预期结果 | 必要字段/唯一键存在且数据保留；并发首次启动若报table exists须记录可复现问题，不能假定所有路径通过。 |
| 10. 数据库验证 | sqlite_master/PRAGMA indexes、列默认、外键；启动前后任务/资源数。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 单线程顺序及并发首次启动均有明确结果，异常属于报告而非自动修复。 |
| 13. 失败标准 | 启动把待测数据库偷偷改成ORM并掩盖迁移缺失、重建表丢数据、重复约束冲突。 |
| 14. 证据保存 | RunRoot/evidence/MIG-02/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## DB-01 · PostgreSQL适用性

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | DB-01；初始NOT_RUN |
| 2. 测试模块 | PostgreSQL适用性 |
| 3. 风险等级 | P1 |
| 4. 测试目标 | 验证真实行锁/唯一冲突/租约，并明确MySQL支持边界。 |
| 5. 前置条件 | 可创建专属PostgreSQL数据库的授权，已审scripts/verify_external_services.py中的DDL；没有环境则BLOCKED。MySQL先核查驱动/迁移支持，不具备则N/A并说明依据。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 专属数据库从当前迁移图建库。2. 读取schema与事务隔离。3. 将WRK-01/03、CAN-05、IDM-02/03迁移到真实PG session factory。4. 原assistant_client硬编码SQLite，必须用新夹具，不能仅换DATABASE_URL就宣称这些测试跑PG。5. 并发提交/rollback/时间比较核验。 |
| 8. API/执行命令 | 受控授权后可用RUN_EXTERNAL_SERVICES=1 pytest tests/integration/test_external_services.py -m external_service -q；另执行新PG task用例，先审verifier会DROP/CREATE的目标名 |
| 9. 预期结果 | 真实PG无重复/旧代提交，flush/commit竞争都能恢复；一般外部连通测试不算任务并发验收。 |
| 10. 数据库验证 | PG唯一索引、外键、锁等待、事务隔离、任务owner与成果精确计数。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 目标DB的全部必需并发用例独立通过；跨库结论限定范围。 |
| 13. 失败标准 | 用SQLite夹具跑出绿点就声称PG通过，未授权DDL，MySQL没有驱动仍写支持通过。 |
| 14. 证据保存 | RunRoot/evidence/DB-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## PERF-01 · 稳定性与性能

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | PERF-01；初始NOT_RUN |
| 2. 测试模块 | 稳定性与性能 |
| 3. 风险等级 | P2 |
| 4. 测试目标 | 测队列积压/吞吐/锁等待/心跳负载和资源泄漏，不虚构生产SLA。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 无模型profile任务从10条基线到50条，单Worker再双Worker，各至少3轮。2. 独立稳定性阶段持续15分钟上限（测试预算，非产品SLA）。3. 记录入队/领取/完成p50/p95、积压、DB锁等待、心跳更新数、CPU/RSS/线程/FD。4. 高锁等待与慢只读模拟。5. 与配置推导的心跳/轮询阈值比较，按实测确定是否退化。 |
| 8. API/执行命令 | 第三方创建 python $RunRoot/harness/external_queue_load.py；POST /assistant/chat action=profile；Worker --batch-size 1 --poll-interval 2；不使用收费生成做压测 |
| 9. 预期结果 | 所有唯一任务最终数量守恒、无重复副作用或泄漏趋势；耗时随串行设计解释；超过自定预算安全停止。 |
| 10. 数据库验证 | queued/running/terminal总数与请求数一致；按根键重复0；记录WAL大小与锁等待。 |
| 11. 日志验证 | 保存本案PID的stdout/stderr，关联task_id、worker_id、attempt、agent和最终状态/错误原因；幂等测试另核key/hit日志。实际不存在的字段记诊断缺口，禁止伪造。 |
| 12. 通过标准 | 给硬件/配置/样本量/分位数和基线，不无证据写支持千并发；必要SLA由委托方确认。 |
| 13. 失败标准 | 无限压测、压收费API、遗失任务/连接持续增长、只报平均值掩盖锁饥饿。 |
| 14. 证据保存 | RunRoot/evidence/PERF-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## SEC-01 · 日志与交付脱敏

| 字段 | 执行规格 |
| --- | --- |
| 1. 测试编号 | SEC-01；初始NOT_RUN |
| 2. 测试模块 | 日志与交付脱敏 |
| 3. 风险等级 | P0 |
| 4. 测试目标 | 保证测试证据不泄露密钥/令牌/真实学习隐私，并审异常路径。 |
| 5. 前置条件 | 可读取当前源码并执行Python/HTTP；已有隔离测试账户A/B或对应pytest fixture。凡涉及并发必须具备独立连接和进程/线程控制；缺失时记BLOCKED。 |
| 6. 环境准备 | 按上下文§8新建RunRoot/独立DATABASE_URL，禁用付费provider；本案证据单独目录，不导入真实学习数据。使用已有码fixture时仍先隔离全局autouse数据库。 |
| 7. 具体操作步骤 | 1. 在隔离环境使用唯一假secret marker，触发401、provider错误和DB异常。2. 检索stdout、jsonl、HAR、trace、截图、JUnit与错误repr。3. 检查文件名/附件正文引用权限。4. 以schema/AST/字符串检索秘密字段，不输出匹配原文。5. 交付前脱敏并验证链接。 |
| 8. API/执行命令 | 只对RunRoot evidence执行本地扫描；pytest tests/unit/test_jwt_algorithm_hardening.py tests/unit/test_assistant_privacy.py -q；对假marker只输出文件名/匹配数量 |
| 9. 预期结果 | 不出现真实/测试token、Authorization、密码或模型key；错误信息保留可诊断ID且无用户隐私。 |
| 10. 数据库验证 | 证据DB只含测试用户，报告仅保留必要ID/散列/聚合；原始tokens不写盘。 |
| 11. 日志验证 | 本用例验证日志本身，只输出布尔值、数量和脱敏上下文。 |
| 12. 通过标准 | 脱敏后仍能复现且不暴露秘密；疑似泄漏封存处理而非公开粘贴。 |
| 13. 失败标准 | 完整环境/headers/账号响应出现在报告、HAR携带Bearer、用真实学生数据作默认样例。 |
| 14. 证据保存 | RunRoot/evidence/SEC-01/ 按公共约定存命令、断言、脱敏响应、数据库前后值、JUnit和必要时序图；新增harness源码一起保存，预期与实际逐项对照。 |
| 15. 环境恢复 | 仅释放本案事务/连接/事件/测试PID，恢复stub与配置；保留隔离库/证据，禁止清理共享资源。 |

## 结果汇总规则
报告分别列API断言、pytest参数展开数、浏览器场景数，避免把同一个既有测试在多个用例中的复跑重复计总覆盖。用例总数 = PASS + FAIL + BLOCKED + NOT_RUN + N/A + SKIPPED；参数化子项另外列明分母。真实LLM、Mock、SQLite、PostgreSQL、浏览器route-mock、真实Worker E2E不能混成一个通过率。

最终验收：PASS只限明确范围中所有必需测试实际通过；CONDITIONAL PASS用于无已确认阻断缺陷但仍有列明限制/待验；FAIL用于确认阻断缺陷或已执行关键标准不满足；BLOCKED用于核心环境/权限/工具不足致无法判断。若仅静态审计，结论必须注明“静态审计”，不得冒充动态验收。
