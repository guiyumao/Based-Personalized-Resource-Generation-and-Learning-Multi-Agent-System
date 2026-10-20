# 可直接复制：第三方AI平台独立验收执行Prompt

你是独立的高级软件测试架构师、分布式系统可靠性测试专家和 AI 应用安全审计工程师。

你正在对一套由另一名 AI 开发助手实现的系统进行第三方独立验收。

你的职责不是证明原有实现正确，而是通过真实代码审查、自动化测试、故障注入、并发验证和端到端测试，寻找可以复现的问题。

你必须以证据为基础开展测试，不得依赖开发者已有的测试通过声明。

请把本文作为执行任务，不只输出测试计划。下面内嵌了从当前项目核查的上下文、36项完整用例、运行环境、源码交接清单和报告要求。只要具备条件，持续执行到测试、复现、核算与报告完成；对能力不足的项目准确记BLOCKED，不虚构工具权限、测试数据或成功结果。

## 执行边界
- 以你实际收到的当前源码为准；本快照日期2026-10-19。先核对指纹和dirty文件，若漂移先重建基线。
- 本轮是独立验收，不是业务修复。允许在隔离副本/RunRoot写独立测试、stub、日志和报告；不得修改生产数据库或擅自改变受测业务逻辑。
- 不默认你有源码、浏览器、终止进程、Docker、数据库建库或收费模型权限。先实测能力；无源码先给出下文最小充分交接清单，核心缺失时BLOCKED。
- 不外发真实API Key、密码、Bearer、Cookie、学生数据或用户附件。不要输出完整.env或环境变量、不要把token保存进JUnit/HAR/trace。仅用本轮临时账户和非私人课程数据。
- 不在共享端口、共享SQLite、共享索引或真实知识巡检计划上注入故障。退出只处理本轮登记的PID/连接，不清理用户资产。
- 架构和函数名下文已核查，仍需你独立确认；README、DEV_STATE、开发验收记录中的通过数均为待核实历史证据，不是你的结论。
- 所有新增命令/harness必须保存可复现源码并真实执行。只写伪代码、只静态推测或仅复述开发者测试，不满足动态验收。

## 按顺序完成十二步
1. **确认执行环境及可用工具**：报告OS、cwd、源码可读性、Python/Node/浏览器、网络、子进程/端口、数据库、secret和预算能力；用不泄露secret的检查确认，不猜测。
2. **读取代码、配置和测试资料**：读取本文源码表中的完整关键函数，所有import依赖、配置/迁移、前端轮询与现有测试；生成版本/文件哈希和带行号证据索引。先判定真实FastAPI/Vue链，不能使用历史Spring Boot假设。
3. **建立功能及风险矩阵**：以本文36案为最小集合，自行补充新发现风险；每案标出Mock/真实、线程/进程、DB类型、运行前提和oracle。先输出矩阵与简短执行顺序，然后直接继续。
4. **准备隔离环境**：按上下文环境脚本建立RunRoot，独立DATABASE_URL、JWT、日志、语料/索引、测试账户和端口；验证子进程配置一致。迁移/故障注入先确认绝对路径/归属和可回收PID。
5. **执行已有回归**：先collect核对节点，再核心、最终组合和扩展回归。保留exit code与JUnit；不要把113/45直接当本次结果，更不能把重复复跑累加成覆盖数。
6. **补充独立测试**：至少补取消/恢复竞态、commit后崩溃、数据库异常、HTTP模型故障次数、登录UI新取消状态、目标DB行锁；复用原服务与模型，测试预期从不变量独立推导。
7. **执行并发及故障注入**：用Event/Barrier/IPC/SQL事件精确控制时间窗，覆盖多Worker、实际kill、旧代恢复、取消/提交、唯一约束冲突和恢复。所有harness有超时/finally，不能仅sleep后断言。
8. **执行真实API与前端联动**：注册/真实登录临时账户，真实API+Worker+DB联动；provider先Mock。真实DeepSeek单独受控小样本，先有明确次数/费用上限，没有预算就不发请求。
9. **核查数据库及持久化结果**：每案有前后只读快照、任务/根键精确计数、正文SHA、消息/评分/路径关联，验证权限和终态。不能以HTTP200或截图替代持久证据。
10. **整理可复现问题**：先复现再分级，提供文件/当前行号、最小命令、预期/实际、影响、证据和建议；静态怀疑未复现的标为风险，不伪装已确认缺陷。不自行修业务掩盖问题。
11. **评估风险与验收**：用PASS/CONDITIONAL PASS/FAIL/BLOCKED限定实际已测范围；核心证据不足不得PASS，Mock、真实LLM、SQLite、PG、UI、构建和部署分别判定。
12. **输出最终测试报告并安全退出**：核算总数/通过/失败/阻塞/未执行/跳过/N/A，列全部命令与exit code、限制、原始证据索引和回归建议；关闭本轮进程/连接/浏览器，保留证据。

## 受测上下文（完整嵌入）

# 第三方独立测试：项目上下文
核查日期：2026-10-19（Asia/Shanghai）。这是源码提取材料，不是独立测试通过证明。对应 Prompt、矩阵、交接说明均在本目录。路径以仓库根目录为基准；第三方必须在自己的副本重新核实。

## 1. 当前版本与范围
当前 HEAD：**05ee287df3f548943fdebdc267109b3fedbe65a2**，分支 main；工作树有大量修改和未跟踪文件。仅克隆 HEAD 会缺失 AssistantTask 等本轮实现，不能代表待验收版本。交付必须包含当前工作树的安全源码快照及文件哈希，保留已有改动，不执行 reset/clean。
本轮读取到 Alembic 唯一 head：**20261019_0022**。DEV_STATE.md 中知识库部分仍提到 0019，属于文档漂移；0017 是本项修复版本，不能当成整个当前项目的 head。

后端：Python/FastAPI 多服务，SQLAlchemy 2、Alembic、Pydantic 2，默认本地 SQLite，声明 PostgreSQL 驱动 psycopg。Docker Compose 提供 PostgreSQL 16、Redis、RabbitMQ、Neo4j、MinIO、Elasticsearch、Chroma。Java/Spring Boot 目录是迁移骨架，不作为当前主运行链。
前端：Vue 3、Vite 8、TypeScript、Pinia、Element Plus、Axios。README 写 Python 3.12+，pyproject 声明 >=3.11；本机只读版本检查为 Python 3.12.3、Node v22.14.0，不能替代第三方版本检测。已安装 Vite 的 engines 为 ^20.19.0 || >=22.12.0，不能简单按 Node 20 任意小版本安装。
主范围：AssistantTask/CoordinatorWorkflow/数据库队列/独立 Worker/课件与题组持久化/执行权/取消/恢复。评分与路径确认做邻接回归。知识库任务有另一套 KnowledgeBuildTask 状态，不能混作 AssistantTask。

## 2. 目录与运行入口
| 目录 | 用途 |
| --- | --- |
| common/ | 配置、JWT、数据库模型/会话、日志与性能追踪 |
| services/{user,agent,resource,evaluation,teacher,system}_service/app/ | 六个 FastAPI 服务 |
| services/agent_service/app/agents/ | 路由分析、同步多 Agent 协调 |
| prompts/ | 模型生成模板，测试副本必须提供 |
| alembic/versions/ | 全量连续迁移，不能仅上传 0017 |
| web-app/src/ | 实际 Vue 应用，AssistantPet 全局挂载 |
| tests/unit/、tests/integration/、tests/e2e/ | pytest 与 Node/Playwright library 脚本 |
| knowledge_base/corpus/ | 教材 Markdown；提供经许可的非私人样例即可 |
| deployment/sakurafrp/、infrastructure/nginx/ | 本地同源网关资料，公网部署另需验收 |
| java-services/、ui-demo/ | 历史/预研，不作为本轮运行入口 |

默认本地服务端口：用户 8001、智能体 8002、资源 8003、评价 8004、教师 8005、系统 8006；脚本另有 8007 QA 兼容进程，Vite 默认 5175。这些是脚本/配置默认值，不是本轮确认正在运行的端口。
脚本 scripts/start_local_services.ps1 会启动更多进程（包括知识 Worker），第三方隔离测试优先逐个启动所需服务，不能直接复用共享端口和共享 .env。

## 3. 调用链与提交边界
1. POST /assistant/chat → assistant_chat()：验证登录和角色、附件归属、动作及参数；qa 调 ChatService，同步消息/SSE不属于持久任务链；其余动作进入 create_task()。
2. create_task() 将首条用户消息、会话及 AssistantTask 提交；同用户 client_request_id 有唯一约束，重放内容不同返回 409。background 模式用 FastAPI BackgroundTasks；worker 模式只入库。
3. assistant_worker.run_pending_tasks() 读到期 PENDING，按 ID 排序、batch_size 限制候选；execute_task() 条件 UPDATE 原子领取，写 worker_id、started_at、heartbeat_at，execution_attempt+1，清 next_attempt_at。batch_size 不是同进程并发数，循环顺序执行。
4. execute_task() 启动独立心跳线程，设置 current_execution ContextVar。只读动作走 profile/search/recommend；生成走 _coordinated_result() → _run_task_workflow() → CoordinatorWorkflow.run()/ _execute_agents()。
5. CoordinatorWorkflow 的可信 assistant_operation_root 属性由持久执行器设置，公共 payload 中同名字段被覆盖。Agent 启动前检查取消/租约，回调记录阶段；课件/练习调用前后还有执行权检查。11–20 题分两批，combined 中路径在成果之后生成，persist_path=False。
6. ResourceGenerationService 与 ExerciseGenerationService 各自打开 SessionLocal 并提交成果；ensure_write_allowed(db) 在同一事务条件更新任务行，串行化取消/保存。资源有知识点创建的独立提交，练习有 flush，必须审计这些更细边界，不能假定整项任务一个事务。
7. 成果先提交，AssistantTask 终态/AssistantAgentExecution/助手 ChatMessage 后提交。最终条件更新核对状态、worker_id、execution_attempt 和有效租约；失败/取消也防止旧代覆盖。SUCCEEDED 可以含 partial=true，不能把字符串成功理解为所有成果都完整。
8. 路径只生成草案；confirm_learning_path() + LearningPathService.save_assistant_draft() 在用户确认后保存，并更新消息卡片。评分复用 ReportService 的 submission_receipt，而非新建统一幂等账本。
9. 当前 assistant_worker.main() 还调用 dispatch_due_plans()、knowledge_tasks.expire_interrupted_tasks()/run_pending_tasks()。必须提供这些依赖，并测试其异常、长任务对助手队列的影响；不存在已核实的“仅助手模式”开关。

## 4. 实际状态转换
| 起点 | 条件/入口 | 终点及可见行为 |
| --- | --- | --- |
| 无记录 | create_task，身份与请求有效 | PENDING，用户消息/任务入库 |
| PENDING | execute_task 原子领取且 next_attempt_at 到期 | RUNNING，attempt 增 1 |
| PENDING | 本人 /cancel 赢得条件更新 | CANCELLED，completed_at 有值 |
| RUNNING | /cancel | HTTP 409，状态不变 |
| RUNNING | 本人 /request-cancel | CANCEL_REQUESTED；此时不能宣称已停止 |
| PENDING/终态 | /request-cancel 无 RUNNING 可更新 | 返回原状态，不会替代 /cancel |
| RUNNING | 有效 owner/attempt/租约，结果提交赢得竞争 | SUCCEEDED；已确认完成不能被取消覆盖 |
| RUNNING | 业务异常且仍拥有有效执行权 | FAILED |
| CANCEL_REQUESTED | 安全边界返回/失败终结/取消等待超时或失活 | CANCELLED；保留可确定已提交的成果，异常分支可能只有提示 |
| RUNNING | worker 模式，只读 profile/search/recommend，心跳失活、未超总时长且未达次数 | PENDING，清 worker/heartbeat，设置 next_attempt_at |
| RUNNING | 生成类失活、执行超时、只读次数耗尽 | TIMED_OUT，需核对 error_code 和成果 |
| background 的老 PENDING | 长期未执行且超配置期限 | TIMED_OUT；worker 模式不会仅因排队久而失败 |
| FAILED/TIMED_OUT | /retry，生成类显式确认副作用 | 新 PENDING 任务；原任务仍为终态，继承 side_effect_root_task_id |
| 其他状态 | /retry | HTTP 409 |
| SUCCEEDED/CANCELLED 且有路径草案 | /confirm-path | 状态不改名，result.path_saved=true |

名称兼容：PENDING 表示 QUEUED，SUCCEEDED 表示 COMPLETED。不要要求数据库改用 QUEUED/COMPLETED。具体异常状态与 HTTP 包装以源码及隔离 OpenAPI 为准。

租约：coalesce(heartbeat_at,updated_at) >= now - max(3*心跳间隔,失活阈值)；started_at 为 null 的历史行有兼容分支，否则不能超过单次最长时限。心跳先执行期限处理再尝试续租。取消等待以 updated_at 计算，不是独立 cancel_requested_at。数据库锁等待、时钟偏移、兼容历史行、重复取消是否延后等待都应独立测试。

## 5. 表与幂等事实
| ORM / 表 | 关键约束或字段 | 核验重点 |
| --- | --- | --- |
| AssistantTask / assistant_tasks | UNIQUE(user_id,client_request_id)；request_json/result_json；worker_id/execution_attempt/heartbeat_at/started_at/next_attempt_at；completed_at | 合法终态、所有权、重试根、队列顺序 |
| AssistantAgentExecution / assistant_agent_executions | task_id、agent_code、status、elapsed_ms、error_code | 结果提交时保存；不是逐阶段永久 checkpoint，也没有单独操作账本 |
| Resource / resources | nullable UNIQUE assistant_operation_key；generated_for_user_id；content/audit_status | 同键同 ID 同正文，拒绝跨用户；已拒审资源不能重放为有效成果 |
| Exercise / exercises | nullable UNIQUE assistant_operation_key；content JSON 含 generated_for_user_id | 题组所有行同事务；逐题 index，数量完整、所有者正确 |
| ChatSession / chat_sessions；ChatMessage / chat_messages | user_id/session_id；metadata_json.task_id | 同 task 仅一条最终助手消息，不多建空会话 |
| AnswerRecord / answer_records | evaluation_json.submission_receipt | 同提交标识重放不重复计分/更新画像/发事件 |
| LearningPath / learning_paths；LearningTask / learning_tasks | user_id、tasks_json 的助手草案来源 | 未确认不替换路径；并发确认只保存一次 |
| User/UserProfile / users,user_profiles | JWT 对应实际活动用户 | A/B 用户、教师权限、真实学习证据 |
| KnowledgeBuildTask/KnowledgeMaintenancePlan | 另一套队列/计划 | 当前 Worker 邻接依赖，隔离库不得导入真实计划 |

资源键：assistant:{原任务根ID}:resource。
题目键：assistant:{原任务根ID}:exercise:{batch}:{index}，batch 首批 0、补批 1，index 从 0 起。
重试创建新任务，但请求 JSON 的 side_effect_root_task_id 延续原根。不同新业务任务合法生成新成果，不应按主题相同合并；不能宣称跨所有独立请求的语义去重。
现有路径确认、作答回执分别保护；没有通用外部副作用 Outbox。Neo4j 同步使用已有 MERGE；同步执行 execute=True 时不发布异步 Agent 队列。没有在此学习任务链发现 GitHub 写操作。

## 6. 真实 API（均需再次核对隔离 /openapi.json）
基址分服务，不能把 resource-service 和 agent-service 都当成一个 /resources 路由。
| 服务 | 方法/路径 | 请求/响应与权限 |
| --- | --- | --- |
| user | POST /users/register | username 3–50、password 6–128、role=student；201，access_token/user_id/role，令牌仅留内存 |
| user | POST /users/login；GET /users/me | JSON username/password；Bearer 后查询身份 |
| agent | POST /assistant/chat | message 1–4000，client_request_id 8–80，action、knowledge_point、exercise_count 3–20、use_learning_context、conversation_id、attachment_ids；任务响应 kind/task/conversation_id |
| agent | POST /assistant/chat/stream | 仅 qa；资源动作422，SSE不等于任务取消 |
| agent | GET /assistant/tasks?conversation_id=…&limit=… | 当前用户列表，limit 被夹在1–100 |
| agent | GET /assistant/tasks/{task_id} | 当前用户状态、result、执行记录；非本人404、未登录401 |
| agent | POST /assistant/tasks/{task_id}/cancel | 无请求体，PENDING取消、RUNNING409 |
| agent | POST /assistant/tasks/{task_id}/request-cancel | 无请求体，运行中取消申请，幂等返回当前状态 |
| agent | POST /assistant/tasks/{task_id}/retry | client_request_id、confirm_side_effects=false 默认；失败/超时才能重试 |
| agent | POST /assistant/tasks/{task_id}/confirm-path | 无请求体，有草案且本人；重复调用复用 |
| agent | GET /assistant/capabilities | 学生动作全集；教师仅 qa/search |
| agent | POST/GET /assistant/attachments；DELETE /assistant/attachments/{attachment_id} | multipart file；TXT/MD/PDF/DOCX文字提取，5MB/份、最多3份引用，按用户隔离 |
| agent | POST /agents/coordinate | CoordinationRequest；验证 user_id 的权限，公共 payload 不得注入内部操作根 |
| agent | POST /resources/generate；POST /exercises/generate | 同步生成入口，不能当成 durable task；需认证且限定目标用户 |
| resource | GET /resources；GET /resources/{resource_id} | 公共资源可匿名；个人生成资源限定本人 |
| resource | GET /resources/{resource_id}/export.docx | 登录、有权限，真实DOCX字节；不是 task 副作用重放入口 |
| evaluation | POST /evaluation/practice/submit | user_id/exercise_id/knowledge_point/question_type/user_answer/correct_answer/analysis/client_request_id；服务端已存题目权威，不信客户端答案 |
| evaluation | POST /evaluation/submit | 另一评分模型，不能拿 practice payload 混用 |
各 FastAPI 服务有 /health，OpenAPI 默认 /openapi.json。不能以 health=200 证明 Worker 正常或模型可达。

## 7. 配置（只给名称、默认与测试用值）
| 名称 | 代码默认/作用 |
| --- | --- |
| DATABASE_URL | sqlite+pysqlite:///./learning_system.db；测试必须覆写独立绝对路径 |
| JWT_SECRET_KEY | 必需；第三方临时随机生成，API/Worker共享，不上传/不输出值 |
| ASSISTANT_TASK_EXECUTION_MODE | background；队列验收用 worker，两端一致 |
| ASSISTANT_WORKER_HEARTBEAT_SECONDS | 5；实际 interval 至少1 |
| ASSISTANT_WORKER_STALE_SECONDS | 45；实际至少 interval*3 |
| ASSISTANT_TASK_MAX_SECONDS | 1800；与心跳独立，最小1 |
| ASSISTANT_CANCEL_WAIT_SECONDS | 60；最小1 |
| ASSISTANT_SAFE_RETRY_LIMIT | 2；表示最多执行次数，最小1，并非额外两次 |
| ASSISTANT_SAFE_RETRY_BACKOFF_SECONDS | 5；基数*2^(attempt-1)，夹到0–300 |
| LLM_REQUEST_TIMEOUT_SECONDS | 45；客户端 timeout 至少3 |
| MAX_TOTAL_RETRIES | 2；生成/审计层预算，不等于SDK自动重试，ChatOpenAI max_retries=0 |
| COURSEWARE/EXERCISE/LEARNING_PATH/QA/CHAT/REPORT_DEADLINE_SECONDS | 对应60/20/30/60/60/30；不同入口的 trace 建立方式不同，必须测 Worker 路径是否实际生效 |
| DEEPSEEK_API_KEY/DEEPSEEK_API_BASE/DEEPSEEK_MODEL | 名称从配置取；真实密钥从第三方受控secret注入 |
| QWEN_API_KEY/QWEN_API_BASE/QWEN_MODEL；OPENAI_API_KEY/OPENAI_BASE_URL/OPENAI_MODEL | 多provider优先级必须检查；LLMFactory有Qwen优先分支，不能只看到DeepSeek变量就宣称调用DeepSeek |
| LLM_PREWARM_ENABLED | true；无费用基础测试设false |
| CORS_ALLOW_ORIGINS | 代码默认空列表；隔离前端来源要配置到每个服务 |
| KNOWLEDGE_RUNTIME_ROOT | common/knowledge_paths.py 支持的隔离根，默认源码根 |
| CHROMA_MODE/CHROMA_PERSIST_DIRECTORY | 代码persistent/./knowledge_base/index；隔离目录，避免碰共享索引 |
| NEO4J_ENABLED/NEO4J_URI；REDIS_URL/RABBITMQ_URL/ELASTICSEARCH_URL | 非必要服务在隔离测试禁用/置空，记录降级，不能宣称这些服务通过 |
| AI_PERFORMANCE_LOG_PATH | 默认./logs/ai-performance.jsonl；覆写至测试产物目录 |
| VITE_USER/AGENT/RESOURCE/EVALUATION/TEACHER/SYSTEM_API_BASE_URL | web-app/src/api/http.ts 必需六项；同源模式另有VITE_SAKURAFRP_SAME_ORIGIN |
| FRONTEND_PORT/FRONTEND_HOST | Vite读取；默认5175/127.0.0.1 |
| RUN_LIVE_LLM、RUN_EXTERNAL_SERVICES | pytest显式选择开关，不是服务可靠性配置 |

## 8. 隔离环境可执行准备（PowerShell）
以下是第三方执行步骤，本轮未运行。示例 18001–18006/15175 是新分配的测试端口，不是声称项目原来使用这些端口。先检查空闲，有冲突则整体改映射。
必须在安全源码副本根目录执行；不要拷贝真实 .env、数据库、用户上传文件、logs、trace。源码副本没有 .env 时，各模板默认也必须由下面环境覆盖。

~~~powershell
$RepoRoot = (Get-Location).Path
$RunRoot = Join-Path ([IO.Path]::GetTempPath()) ("external-ai-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $RunRoot | Out-Null
New-Item -ItemType Directory -Path (Join-Path $RunRoot "evidence") | Out-Null
$env:DATABASE_URL = "sqlite+pysqlite:///" + (Join-Path $RunRoot "runtime.sqlite").Replace("\","/")
$env:JWT_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:ENVIRONMENT = "test"
$env:DEBUG = "false"
$env:DEFAULT_ADMIN_USERNAME = ""
$env:DEFAULT_ADMIN_PASSWORD = ""
$env:DEFAULT_ADMIN_EMAIL = ""
$env:OPENAI_API_KEY = ""
$env:QWEN_API_KEY = ""
$env:DEEPSEEK_API_KEY = ""
$env:LLM_PREWARM_ENABLED = "false"
$env:NEO4J_ENABLED = "false"
$env:NEO4J_URI = ""
$env:REDIS_URL = ""
$env:RABBITMQ_URL = ""
$env:ELASTICSEARCH_URL = ""
$env:KNOWLEDGE_RUNTIME_ROOT = $RunRoot
$env:CHROMA_MODE = "persistent"
$env:CHROMA_PERSIST_DIRECTORY = Join-Path $RunRoot "index"
$env:AI_PERFORMANCE_LOG_PATH = Join-Path $RunRoot "evidence/ai-performance.jsonl"
$env:ASSISTANT_TASK_EXECUTION_MODE = "worker"
$env:USER_SERVICE_URL = "http://127.0.0.1:18001"
$env:AGENT_SERVICE_URL = "http://127.0.0.1:18002"
$env:RESOURCE_SERVICE_URL = "http://127.0.0.1:18003"
$env:EVALUATION_SERVICE_URL = "http://127.0.0.1:18004"
$env:TEACHER_SERVICE_URL = "http://127.0.0.1:18005"
$env:SYSTEM_SERVICE_URL = "http://127.0.0.1:18006"
$env:VITE_SAKURAFRP_SAME_ORIGIN = "false"
$env:VITE_USER_API_BASE_URL = $env:USER_SERVICE_URL
$env:VITE_AGENT_API_BASE_URL = $env:AGENT_SERVICE_URL
$env:VITE_RESOURCE_API_BASE_URL = $env:RESOURCE_SERVICE_URL
$env:VITE_EVALUATION_API_BASE_URL = $env:EVALUATION_SERVICE_URL
$env:VITE_TEACHER_API_BASE_URL = $env:TEACHER_SERVICE_URL
$env:VITE_SYSTEM_API_BASE_URL = $env:SYSTEM_SERVICE_URL
$env:CORS_ALLOW_ORIGINS = "http://127.0.0.1:15175,http://localhost:15175"
$env:RUN_LIVE_LLM = "0"
$env:RUN_EXTERNAL_SERVICES = "0"
python --version
node --version
python -m pip install -e ".[dev]"
# 新源码副本中安装；有锁文件时使用锁文件，不复用未知node_modules
npm --prefix web-app ci
python -m alembic heads
python -m alembic upgrade head
~~~

不要打印完整环境变量。安装可能访问包仓库；若网络受限，列为安装阻塞，不自动改依赖版本。空 corpus/索引可验证无证据降级，不能据此验收RAG成功；必要教材从授权的非私人样例复制到隔离根。Chroma/embedding可能自行访问网络，Mock阶段应按用例隔离/替换retriever，监测出站访问。

在分别继承同一环境的终端启动（cwd为RepoRoot；或使用隐藏Start-Process、-PassThru记录本轮PID，stdout/stderr分文件）：
~~~powershell
python -m uvicorn services.user_service.app.main:app --host 127.0.0.1 --port 18001
python -m uvicorn services.agent_service.app.main:app --host 127.0.0.1 --port 18002
python -m uvicorn services.resource_service.app.main:app --host 127.0.0.1 --port 18003
python -m uvicorn services.evaluation_service.app.main:app --host 127.0.0.1 --port 18004
# 教师/全站扩展时另起18005和18006，不把未启动服务当通过
python -m services.agent_service.app.services.assistant_worker --batch-size 1 --poll-interval 2
# 另一个相同配置终端可起第二个Worker，不能只把batch-size调大就宣称并发
npm --prefix web-app run dev -- --host 127.0.0.1 --port 15175 --strictPort
~~~
先验证四个服务 /health、/openapi.json，再OPTIONS测试；Worker无HTTP健康路由，检查日志、心跳和实际领取。排队取消用例在尚未启动Worker时执行。启动前一律确认DATABASE_URL指向本轮RunRoot；get_settings和env在导入时缓存，换配置要启动新进程，单纯事后改os.environ不可靠。

## 9. 基础API脚本（无模型、令牌仅在内存）
第三方先在 $RunRoot 下创建 harness 目录，将下面代码保存为 $RunRoot/harness/api_smoke.py，再在同一 PowerShell 环境执行 python "$RunRoot/harness/api_smoke.py"。这是本轮由执行者创建的脚本，不是仓库现有文件。不要把响应中的access_token写入证据。先保持Worker停止，以便PENDING断言可重复。
~~~python
import os, secrets, uuid
import httpx
user_url = os.environ["USER_SERVICE_URL"]
agent_url = os.environ["AGENT_SERVICE_URL"]
accounts = []
with httpx.Client(timeout=20) as c:
    for label in ("a", "b"):
        password = secrets.token_urlsafe(18)
        r = c.post(user_url + "/users/register", json={
            "username": "ext_" + label + "_" + uuid.uuid4().hex[:12],
            "password": password, "role": "student"})
        assert r.status_code == 201
        body = r.json()
        accounts.append({"id": body["user_id"], "headers": {
            "Authorization": "Bearer " + body["access_token"]}})
    a, b = accounts
    payload = {"message": "分析我的学情", "action": "profile",
               "use_learning_context": False, "client_request_id": "ext_" + uuid.uuid4().hex}
    r = c.post(agent_url + "/assistant/chat", headers=a["headers"], json=payload)
    assert r.status_code == 200
    task = r.json()["task"]
    assert task["status"] == "PENDING"
    tid = task["id"]
    assert c.post(agent_url + "/assistant/chat", headers=a["headers"], json=payload).json()["task"]["id"] == tid
    assert c.post(agent_url + "/assistant/chat", headers=a["headers"], json={**payload, "message": "other"}).status_code == 409
    assert c.get(agent_url + f"/assistant/tasks/{tid}", headers=b["headers"]).status_code == 404
    assert c.post(agent_url + f"/assistant/tasks/{tid}/cancel", headers=a["headers"]).json()["status"] == "CANCELLED"
    assert c.post(agent_url + f"/assistant/tasks/{tid}/cancel", headers=a["headers"]).json()["status"] == "CANCELLED"
    assert c.get(agent_url + f"/assistant/tasks/{tid}").status_code == 401
    print("api_smoke passed; task_id=", tid)  # 不打印headers、password或账户响应
~~~
HTTP示例：重试 JSON 为 {"client_request_id":"ext_retry_唯一后缀","confirm_side_effects":true}；请求主体的action只取真实ACTIONS，教师生成入口预期403。不要用公开注册接口创建teacher/admin；需要这两种测试用户时，只在隔离库由测试夹具/ORM创建并生成隔离JWT，或经测试管理员的真实用户创建接口，禁止改共享用户。

## 10. 数据核验与日志
第三方在每阶段执行只读查询，使用真实ID参数绑定，不使用“所有用户总数量”证明单任务幂等。
~~~sql
SELECT id,user_id,session_id,client_request_id,status,worker_id,execution_attempt,
       heartbeat_at,started_at,next_attempt_at,error_code,completed_at
FROM assistant_tasks WHERE id = :task_id;
SELECT id,task_id,agent_code,status,error_code FROM assistant_agent_executions WHERE task_id=:task_id;
SELECT assistant_operation_key,COUNT(*) FROM resources
WHERE assistant_operation_key=:resource_key GROUP BY assistant_operation_key;
SELECT assistant_operation_key,COUNT(*) FROM exercises
WHERE assistant_operation_key LIKE :exercise_prefix GROUP BY assistant_operation_key;
SELECT id,metadata_json FROM chat_messages WHERE session_id=:session_id AND role='assistant';
SELECT id,evaluation_json FROM answer_records WHERE user_id=:user_id AND exercise_id=:exercise_id;
~~~
使用JSON解析筛选metadata_json.task_id、submission_receipt，不把SQL通配符当成精确操作匹配；独立测试要加入下划线/百分号等键输入的安全检查。SQLite结构核查用PRAGMA table_info、index_list、index_info、foreign_key_list和foreign_key_check；PostgreSQL用对应系统目录，不能照搬PRAGMA。
日志来自configure_logging的控制台格式和AI_PERFORMANCE_LOG_PATH，收集时记录task_id/worker_id/attempt/agent/幂等键/最终状态/恢复原因。并非每条日志都具备全部字段，缺少关联能力可以作为可观测性问题。stdout、HTTP、HAR和DB快照必须先脱敏再共享。

## 11. 自动化入口和证据解释
本轮只审查源文件/配置、静态解析和文档一致性，不重新执行业务测试。下列是第三方要运行的命令，不是本轮新增通过声明。
环境必须先按第8节隔离、禁用付费凭证。tests/conftest.py 的session autouse fixture会执行ensure_database_schema；即使单元夹具另建tmp_path，未设置DATABASE_URL仍可能改变共享schema。

~~~powershell
python -m pytest tests/unit/test_assistant_tasks.py tests/integration/test_assistant_worker_process.py -q --junitxml="$RunRoot/evidence/task-chain.xml"
python -m pytest tests/unit/test_assistant_tasks.py tests/unit/test_assistant_privacy.py tests/unit/test_resource_generation.py tests/unit/test_structured_resource_generation.py tests/unit/test_structured_resource_persistence.py tests/unit/test_resource_authz.py tests/unit/test_coordinator.py tests/unit/test_coordinator_sync_agents.py tests/unit/test_exercise_favorites.py tests/integration/test_assistant_worker_process.py -q --junitxml="$RunRoot/evidence/combined.xml"
# 扩展回归，在核心通过后独立统计，不将跳过live用例视为通过
python -m pytest tests/unit tests/integration -m "not live_llm and not external_service" -q --junitxml="$RunRoot/evidence/expanded.xml"
npm --prefix web-app run build
~~~
不可执行tests/global下的_patch_*、_normalize_eol等改码脚本来“测试”；需另审只读probe_api.py的目标地址和参数再运行。
现有重点定义：test_running_cancellation_stops_later_agents_and_keeps_saved_results（4个Agent边界参数）；test_heartbeat_enforces_expiry_without_status_polling（3个期限参数）；两个独立进程测试验证双Worker领取与真实kill恢复。当前文件有38个task test函数，参数展开预计43；这是静态计数预期，真实数量必须由自己的pytest收集/JUnit确定。

真实LLM入口：RUN_LIVE_LLM=1 与 -m live_llm，文件 tests/integration/test_live_llm_resources.py 主要验证mind_map/code_case/video_script，不是专门的真实运行中取消套件；不能无预算运行整个文件来替代本轮验证。外部服务入口 RUN_EXTERNAL_SERVICES=1 与 tests/integration/test_external_services.py，会调用 scripts/verify_external_services.py（包含DROP/CREATE测试数据库等操作），必须先审其数据库名/容器/网络权限，不能对已有业务服务直接启用。
MySQL没有在当前依赖/Compose中形成同等已验证路径；PostgreSQL是有声明和入口但尚需本任务并发验证。没有MySQL环境则N/A并说明，不能泛称多数据库已支持已通过。

E2E真实入口是 tests/e2e/*.mjs + Playwright library，tests/e2e/package.json只声明现有命令，未声明Playwright安装依赖，env.mjs优先本地junction并回退workspace/node_modules。没有已核实的assistant-worker.spec.ts或npx playwright test配置。现有run-assistant-retry.mjs未处理当前确认对话框的步骤，且多数脚本读仓库.env管理员凭据；第三方必须审查并在自己的副本适配测试账户/来源，不能照搬到共享实例。
源码检索未发现现有E2E覆盖 /request-cancel/CANCEL_REQUESTED/TIMED_OUT，因此需新增登录浏览器用例。browser route mock只算UI隔离验证，不能冒充真实Worker端到端。

## 12. 历史限制是否已改善（当前证据等级）
| 项目 | 当前静态发现 | 本轮结论与第三方义务 |
| --- | --- | --- |
| 最终组合回归 | 文档仍记113在较早补丁、最终45仅任务链 | 当前更有0020–0022及Worker耦合改动；没有本轮运行证据，必须重跑组合 |
| 真实DeepSeek取消 | 有Mock late reply测试；现有live资源测试不是取消用例 | 不能判定真实取消已验证，按预算新增 |
| 登录浏览器任务取消 | 有旧mjs登录/附件/重试；未搜到新取消状态覆盖 | 按矩阵补UI真实联动；构建通过不能替代 |
| PostgreSQL/MySQL | 有PostgreSQL opt-in脚本；默认SQLite | 单独核验真实task租约/并发；MySQL先评估支持 |
| 全站E2E | 有run-all.mjs，依赖旧账户/端口及外部工具 | 有脚本不等于当前执行通过 |
| 共享SQLite部署迁移 | 历史库缺可信基线，0017兼容bootstrap有代码 | 本轮没触碰业务库；只对隔离副本演练，不准擅自迁移共享库 |

静态优先审计：ContextVar跨线程/asyncio执行传播；无guard分支是否可到达写入；worker/attempt是否能被payload覆盖；LIKE前缀与操作语义冲突；临界时间 >= 与 <、取消updated_at基准及wall clock偏移；错误结果丢失已存卡片；心跳阻塞/数据库锁与总deadline；新知识队列占用同一Worker。发现怀疑写成待复现假设，不先给确认缺陷结论。

## 13. 源码定位与哈希快照
下面行号仅对应本次静态快照，漂移后按函数重定位。SHA256用于核对交付，不能用HEAD替代dirty工作树。

| 文件 | 关键符号（行号） | SHA256 |
| --- | --- | --- |
| common/config.py | Settings():81 | 3b0c811a44ec4b90e721db973792af83b9c2587471fb804d1445952b1242b63a |
| common/models/learning.py | Resource():103；Exercise():188；AnswerRecord():265；AssistantTask():561；AssistantAgentExecution():701 | c37d5fc620bac48a548019e5255f722bced63e3e901c55b91c3b8ebbf4df22cb |
| common/schemas/agent.py | 见文件正文 | 54921404042888916641e9c446feeda8bc90492aa54952c75cd82cace35c193b |
| common/db/bootstrap.py | ensure_database_schema():16；_ensure_legacy_columns():82 | d31ea69bb2f7e42db7a87e84981eae24f7d5e9fd79396d6b0ea50954d3ca1051 |
| common/db/session.py | 见文件正文 | a22a65a8a4d10566357095f949914d0486c52334c16163e64396c08c6df71659 |
| common/knowledge_paths.py | 见文件正文 | 0655da2d7805fb2e38a1e31b29223df2c7a645603bfbc0b6d5d100ef60209a23 |
| services/agent_service/app/main.py | 见文件正文 | 6dbcde54d999076f10c7056b45038babbc34c38490c0554e1b53892863d4a5f1 |
| services/agent_service/app/api/routes/assistant.py | assistant_chat():163；cancel_task():320；request_running_task_cancel():350；retry_task():375；confirm_learning_path():433 | b55eb7ca4f7277a8ac3584171b3c256a362bbca234789c838a25595777273774 |
| services/agent_service/app/services/assistant_tasks.py | create_task():146；_heartbeat():321；_run_task_workflow():341；_coordinated_result():354；execute_task():538；expire_stale_tasks():660 | c2f374fdb97c61da32f4295e2c03a58ccdc407d7bfd3f32ab15f7a29d1a0e98a |
| services/agent_service/app/services/assistant_worker.py | run_pending_tasks():27；main():42 | f91d2efd59dbd543104c6014e79475a420153c3057908fce9a0376a5fd4e1008 |
| services/agent_service/app/services/assistant_execution.py | lease_conditions():23；ensure_execution_active():36；ensure_write_allowed():52 | 62d19d454796e38e4890c775309e5e47dd980da8b43f5a0ff5baf57f786c81c4 |
| services/agent_service/app/agents/coordinator.py | run():266；_execute_agents():308；_run_resource_agent():752；_run_exercise_agent():839 | 9112bbb2870e9d80a7839dc1a7f3b3f063bf6f856cf1dc91a3782828eee8ad63 |
| services/agent_service/app/services/resource_generation.py | _invoke_llm():546；_persist_generated_resource():619；generate_courseware_with_plan():1286 | 5d0d787cb4f6409257873ebb6760abe6f83b0ded687fb2d1d724f94e0e2c101d |
| services/agent_service/app/services/exercise_generation.py | generate_exercises():47；_persist_exercises():1965 | e071d351ae8d49e861da3a16a4099730845615b2c993045baaaea16e49d54bea |
| services/agent_service/app/services/llm_factory.py | build_chat_model():27；_get_or_create():147 | 916ffd1311a0c1217803fea7a2dec8055a26663434879ba4edf9bdcb3ac43d25 |
| services/agent_service/app/services/learning_path.py | save_assistant_draft():103 | c7025daff7434b9f82e8ee447b7ce1ae5edc0bc80ef58defe4178a3ab105a543 |
| services/evaluation_service/app/services/report_service.py | 见文件正文 | 8231a77da25601955d9687eb86e0144aec5b4169d2ae5d29c46212d9f3c4cbde |
| alembic/versions/20261018_0017_assistant_side_effect_keys.py | 见文件正文 | 40473fa0ac484a7624cdeff5d967b8784baf9ec1118048cdc730c601a4d5cb48 |
| tests/unit/test_assistant_tasks.py | 见文件正文 | d93137432c6b32ef715b63612513ae5c29c04a684ddffbb184f1778b9d2ee98e |
| tests/integration/test_assistant_worker_process.py | 见文件正文 | 9b96cd0ab47cc13c4468d8fc1f1b8c5c470b0ba255dea7e24b2c32536a989e3b |
| web-app/src/api/assistant.ts | 见文件正文 | 2ab69f17a3843f3868461049f04ba7b675a3b23a4aca58f04d6b599d3bf12239 |
| web-app/src/components/AssistantPet.vue | 见文件正文 | 3629c734c1c794fef59ef4fcc7a6ee69917449d8581a8122b0f667557cae6c9f |


## 独立用例与验收矩阵（完整嵌入）

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

## 源码与工具交接、安全退出（完整嵌入）

# 第三方AI平台测试交接说明
日期：2026-10-19。主交付物为 external-platform-test-prompt.md，可完整复制；它内嵌当前上下文和36案矩阵。其余三个文档提供便于维护/审阅的分册视图，不是四套不同验收标准。

## 1. 能力与受限替代
| 能力 | 用途 | 缺失时的处理 |
| --- | --- | --- |
| 读取完整当前源码/配置模板/迁移/测试 | 核实实现、API、状态机、哈希 | 无源码不能独立动态验收；列缺失清单，BLOCKED |
| Python >=项目声明、隔离venv、pip包源 | pytest/FastAPI/SQLAlchemy与故障harness | 用预装依赖可替代安装；依赖缺失不得“跳过后全通过” |
| Node满足Vite engines、npm和前端构建依赖 | Vue构建/Playwright library | 可静态审UI；UI动态用例BLOCKED |
| HTTP客户端、回环端口绑定 | 真实服务API与联动 | 可TestClient补接口隔离测试，但不能冒充live API |
| 子进程启动/终止、stdout/IPC与超时控制 | 真正双Worker/崩溃/恢复 | 线程可补充局部竞争，进程用例仍BLOCKED |
| 可写临时目录/独立数据库 | 测试数据、迁移、故障注入 | 只读审计，不得借用共享库绕过限制 |
| Chromium、Playwright library | 真实登录/小智取消/刷新/错误 | 浏览器手动有证据可替代部分UI自动化；无浏览器则BLOCKED |
| 专属PostgreSQL及建库权限 | 真实行锁/唯一约束/迁移 | SQLite结果不能替代，数据库适用性单独列明 |
| 受控DeepSeek secret、明确预算、网络 | 真实provider取消/超时/计数 | Mock先执行；真实用例BLOCKED，不能自行寻找/复用私人凭证 |
| CPU/RSS/线程/连接等观测 | 队列负载及资源泄漏 | 有限指标可报告；未测项不可捏造 |
| 外部基础设施隔离/权限 | PostgreSQL/Neo4j/Chroma opt-in脚本 | 先审DDL和目标；受限时记录环境原因，不对现有容器破坏 |

## 2. 源码提供方式
### 能直接访问工作区
先读取根目录指令、DEV_STATE和四份测试文档，核对HEAD、dirty工作树和上下文SHA256。用户可能同时开发知识库模块；版本发生变化时重建基线，不把前一天的通过记录用于新代码。只读审计现有业务实现；新增独立测试只写临时harness或安全副本。不得擅自修复业务实现来让测试通过。

### 无法访问工作区
提供**安全源码快照**，不能只给提示词/截屏/113 passed报告，也不能只git clone旧HEAD。上传清单：
1. README.md、DEV_STATE.md、docs/project-structure.md、docs/xiaozhi-assistant-upgrade.md、docs/assistant-task-reliability.md、本目录四份文档、pyproject.toml、alembic.ini、.env.example、docker-compose.yml（仅模板）。
2. common/ 的全部Python源码，services/ 的实际运行Python包及包内依赖（不包括运行缓存/数据库）。不要只上传assistant_worker.py：当前Worker直接import knowledge_tasks、knowledge_maintenance，缺它们会导入失败。
3. alembic/ 全部源码，尤其0011、0015、0016、0017及后续到当前0022；迁移图决定实际head，不能凭本列表假设长期不变。
4. prompts/ 全部文本模板，以及经许可的非私人少量教材样例；不传当前向量索引或真实学习资料。
5. tests/conftest.py、相关tests/unit/、tests/integration/，tests/e2e/源码与package.json/README/lib/env.mjs；测试harness可能依赖其他测试文件，优先提供全部安全测试源码。
6. web-app/src/全部源码、package.json、package-lock.json、vite.config.ts、tsconfig*.json、index.html；所需public静态非私人素材/图片，.env配置只给重新制作的模板。
7. 需要外部服务验证时提供scripts/verify_external_services.py、db_migration_drill.py、verify_knowledge_v83.py和其实际引用的源码；明确它们不是默认可执行白名单，先审目标和副作用。
8. 新包manifest（路径、字节数、SHA256）、提交ID和dirty状态。接收方重新计算对比，不能以Git提交ID代替未提交文件内容。

明确排除：真实.env/.env.local/.env.sakurafrp值、任何私钥/token、数据库及-wal/-shm、logs/原HAR/Playwright trace、用户附件和导出文件、完整真实学生数据、node_modules/.venv/缓存、Git凭证、工作区无关文档。公共模板中的占位符不能直接当作可用secret。不要复制整个用户Desktop或.codex目录。
默认不提供二进制全量工作树zip以避免混入隐私；若需要压缩，用上述白名单在新空目录组包、扫描后压缩，禁止在原仓库执行清理。没有源代码时受测平台先报告BLOCKED并列出缺失文件，不编造运行结果。

## 3. 进入测试前的检查点
- 可执行环境信息以平台实际检测为准；文档写的本机版本只是准备参考。
- 原始业务库严禁作为DATABASE_URL。先验证绝对路径落在本轮RunRoot；SQLite/WAL/索引/语料/性能日志均隔离；每个子进程和服务配置一致。
- 项目导入时读取并缓存配置，tests/conftest autouse会bootstrap。环境必须在导入pytest/应用前设置；不能指望修改os.environ自动改变已建Engine。
- 当前Assistant Worker还调知识计划队列，新建空库无真实计划；不导入现有巡检计划。start_local_services.ps1和docker compose的固定容器名、端口、卷及生产.env不能盲用。
- 禁用真实provider key、默认管理员seed和不必要外部服务后先跑Mock；局部检索可能下载embedding，监测网络。
- 学生A/B通过真实/users/register临时创建；教师/管理员由隔离夹具或隔离管理员流程准备。测试账户不使用真实密码，返回token只保留内存。
- PostgreSQL verifier包含DROP/CREATE命令，只有专属实例/确认目标才可执行。共享SQLite必须先有副本及可信版本基线才能做部署演练；本轮要求不执行共享迁移。
- 任何故障注入只作用本轮PID、连接和端口。记录PID/命令/数据库关联，不能taskkill所有python/node或删除共享数据库/容器卷。
- 真实DeepSeek缺预算即阻塞此项。预算默认建议至多3个实际provider请求、审计重试0、变体1，执行前由受测平台与委托方确认费用上限；这不是项目已有总费用保护开关。

## 4. 推荐执行顺序
1. ENV-01和静态源码/指纹核对，确认路由、schema、迁移与能力。
2. 按上下文§8建立新源码副本和RunRoot，安装/核对依赖，建立两条独立迁移轨道。
3. REG-01核心→组合，记录新版本真实结果；扩展回归在后。
4. API-01/02/03及CAN-01，先不启动Worker。
5. CAN-02至07、WRK-01至07、IDM-01至05及TXN-01，以Mock模型+真实DB进行独立复验。
6. FLT-01、LLM-01，运行故障注入；先证明清理/finally能执行，再扩到长时稳定性。
7. UI-01/02：真实登录/HTTP/Worker，provider可Mock；之后有预算才LLM-02真实provider小样本。
8. MIG-01/02、DB-01目标数据库专项，PERF-01稳定性，SEC-01证据脱敏。
9. 全站现有E2E按账户/来源/工具实际适配后独立执行，不能把旧脚本的样例截图当本次验收。
10. 核对每条SQL与时序证据，确认缺陷复现，输出正式报告和回归建议。

## 5. 独立性的要求
开发者已有测试是线索，不是结论。至少新增：取消/重排队竞争、保存commit后进程退出、数据库故障、实际HTTP provider故障计数、真实UI新取消状态、目标数据库行锁。测试预期从接口合同、持久不变量和用户语义独立推导，不照抄开发代码的if分支。
发现问题先保留最小复现、数据前后快照、版本与时序，不擅自修业务。若临时改stub/进程配置，报告准确范围和还原动作。疑似问题需动态复现或标记“静态风险”，不能把怀疑写成已确认漏洞。

## 6. 交付证据与报告
目录建议：RunRoot/evidence/环境与指纹、case_id子目录、JUnit、脱敏HTTP/SQL/日志、浏览器截图、独立harness源码、report.md、defects.json。
缺陷记录必需：ID、P0–P3、影响、前置、完整复现步骤/命令、实际/预期、稳定复现比例、代码文件+重验行号、数据/日志/截图链接、最小建议修复、回归建议、Mock/真实与数据库类型。
最终报告必需：环境、源码版本/哈希、实际命令与退出码、总数/通过/失败/阻塞/未执行/跳过/N/A、数据库核验、并发/故障结果、缺陷清单、限制、验收结论。参考Prompt中的模板，计数必须能从JUnit/执行账本核算。
资料仅体现开发者历史113/45；本轮文档生成没有执行业务回归或收费模型。真实DeepSeek取消、登录浏览器新取消、PG任务并发、全站E2E和共享库部署仍需接收平台核验，不能仅因存在脚本就认定已改善。

## 7. 结论边界与安全退出
PASS只限定实际已测范围；核心环境不足给BLOCKED，不改成“预计通过”。无已确认阻断但存在待验范围可CONDITIONAL PASS并列明条件；已确认关键标准失败给FAIL。构建成功、Mock成功、SQLite成功分别报告，不自动升级成UI、真实provider、多数据库或生产部署通过。
结束时停止登记的测试PID、关闭连接/浏览器/IPC、解除故障注入、恢复测试副本；保留RunRoot证据供复核。没有用户明确要求不递归删除；即使清理临时目录，也先核对其绝对路径及归属，不能以模糊通配符删除共享文件。


## 附录A：第三方独立harness起点（必须实际保存并运行）
以下样例是新测试素材，不是声称仓库已有的用例。你应使用它建立可控测试环境，然后完成矩阵规定的故障/时序变体。运行前环境必须在import前设置；所有数据库均在tmp_path/RunRoot，不能复用共享Engine。

将下例保存为RunRoot/harness/test_external_fencing.py，用RepoRoot为cwd执行：
~~~powershell
python -m pytest "$RunRoot/harness/test_external_fencing.py" -q --junitxml="$RunRoot/evidence/independent-fencing.xml"
~~~

~~~python
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from common.db.base import Base
from common.models.learning import User, ChatSession, AssistantTask, Resource
from services.agent_service.app.services import assistant_execution

@pytest.mark.parametrize("fault", ["wrong_worker", "wrong_attempt", "expired_lease"])
def test_external_fencing_preserves_database(tmp_path, monkeypatch, fault):
    engine = create_engine("sqlite:///" + (tmp_path / "isolated.sqlite").as_posix())
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(assistant_execution, "SessionLocal", factory)
    monkeypatch.setattr(assistant_execution, "get_settings", lambda: SimpleNamespace(
        assistant_worker_heartbeat_seconds=1, assistant_worker_stale_seconds=10,
        assistant_task_max_seconds=60))
    now = datetime.utcnow()
    token = None
    try:
        with factory() as db:
            user = User(username="ext_fence_student", password_hash="test", role="student")
            db.add(user)
            db.flush()
            session = ChatSession(user_id=user.id, title="independent", subject="TCP")
            db.add(session)
            db.flush()
            task = AssistantTask(user_id=user.id, session_id=session.id,
                client_request_id="external_fence", task_type="courseware", status="RUNNING",
                worker_id="actual-worker", execution_attempt=2, request_json={}, result_json={},
                started_at=now, heartbeat_at=now - timedelta(seconds=20)
                    if fault == "expired_lease" else now)
            db.add(task)
            db.commit()
            task_id, user_id = task.id, user.id
        owner = "old-worker" if fault == "wrong_worker" else "actual-worker"
        attempt = 1 if fault == "wrong_attempt" else 2
        token = assistant_execution.current_execution.set((task_id, owner, attempt))
        with factory() as db:
            with pytest.raises(assistant_execution.ExecutionStopped):
                assistant_execution.ensure_write_allowed(db)
                # 若guard被错误放行，下面写入会使本案失败，不能仅检查返回状态。
                db.add(Resource(type="courseware", title="forbidden", content="must not save",
                                generated_for_user_id=user_id,
                                assistant_operation_key="assistant:external:resource"))
                db.commit()
        with factory() as db:
            assert db.query(Resource).count() == 0
            task = db.get(AssistantTask, task_id)
            assert task.worker_id == "actual-worker"
            assert task.execution_attempt == 2
            assert task.status == "RUNNING"  # guard自身拒绝写；本案未调用恢复器改状态
    finally:
        if token is not None:
            assistant_execution.current_execution.reset(token)
        engine.dispose()
~~~

故障注入harness的约束：
- 不从HTTP增加生产调试接口；仅在测试子进程启动前导入并替换所需模型/Agent协作者，用真实Session/路由/事务写入。
- IPC marker应在实际领取/commit成功后发出。父进程先收到marker再kill，而非kill后猜测保存到哪一步。
- 子进程停止时使用本轮Popen对象/PID；finally释放所有等待事件、管道、数据库锁和ContextVar；任何等待都有上限。
- 数据库不可用分别注入SQL锁、连接错误与commit确认丢失；不要只patch最终返回固定success。
- 新pytest位于RunRoot时不会自动拥有tests/unit/test_assistant_tasks.py中的局部assistant_client fixture，你需要在自己的harness创建fixture，并patch assistant_tasks/assistant_execution/coordinator及生成器实际使用的SessionLocal；HTTP依赖get_db也要覆盖。不要只替换一个SessionLocal后误连共享库。
- 保留被测源码不变，新增测试源码和所有时序/调用计数作为证据交付。

## 附录B：可运行的登录浏览器排队取消起点
先保持Worker停止（排队取消用例），四服务/前端已按隔离端口启动。该脚本通过真实注册API和真实登录页，不使用localStorage注入代替登录。它不调用收费模型。将JS保存到RunRoot/harness/external-assistant-queued-ui.mjs。
先设置 E2E_BASE_URL=http://127.0.0.1:15175 和 EXTERNAL_TEST_EVIDENCE_DIR=RunRoot/evidence/UI-01；后一个是本测试脚本自定义变量，不是业务配置。Playwright优先复用项目实际library解析；没有库时先在临时harness安装适配依赖/Chromium并说明网络操作，不声称仓库已有@playwright/test。

~~~javascript
import assert from 'node:assert/strict'
import path from 'node:path'
import fs from 'node:fs/promises'
import { randomBytes } from 'node:crypto'
import { createRequire } from 'node:module'
import { pathToFileURL, fileURLToPath } from 'node:url'

const ui = process.env.E2E_BASE_URL
const userUrl = process.env.USER_SERVICE_URL
const agentUrl = process.env.AGENT_SERVICE_URL
const evidence = process.env.EXTERNAL_TEST_EVIDENCE_DIR
assert(ui && userUrl && agentUrl && evidence, 'configure isolated endpoints/evidence first')
const username = 'ext_ui_' + randomBytes(6).toString('hex')
const password = randomBytes(18).toString('base64url')
const register = await fetch(userUrl + '/users/register', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username, password, role: 'student' })
})
assert.equal(register.status, 201) // 不输出注册响应，其中含token
let pw
try {
  const helpers = await import(pathToFileURL(path.resolve('tests/e2e/lib/env.mjs')).href)
  pw = helpers.loadPlaywright().module
} catch {
  const req = createRequire(path.join(path.dirname(fileURLToPath(import.meta.url)), 'package.json'))
  pw = req('playwright') // 仅在本harness已安装库时成功，否则明确阻塞
}
await fs.mkdir(evidence, { recursive: true })
const browser = await pw.chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page = await context.newPage()
const errors = []
page.on('pageerror', e => errors.push(e.name)) // 不记录包含secret的错误正文
try {
  await page.goto(ui + '/login', { waitUntil: 'domcontentloaded' })
  await page.locator('input[autocomplete="username"]').fill(username)
  await page.locator('input[autocomplete="current-password"]').fill(password)
  await page.locator('button.auth-button').click()
  await page.waitForURL(url => url.pathname.startsWith('/student'), { timeout: 20000 })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  const panel = page.locator('.assistant-pet-panel')
  await panel.locator('textarea').fill('分析我的学情')
  const queuedResponse = page.waitForResponse(r =>
    r.url() === agentUrl + '/assistant/chat' && r.request().method() === 'POST')
  await panel.getByRole('button', { name: '发送', exact: true }).click()
  const created = await (await queuedResponse).json()
  assert.equal(created.kind, 'task')
  assert.equal(created.task.status, 'PENDING')
  const taskId = created.task.id
  const cancelResponse = page.waitForResponse(r =>
    r.url() === agentUrl + '/assistant/tasks/' + taskId + '/cancel')
  await panel.getByRole('button', { name: '取消任务', exact: true }).click()
  const cancelled = await (await cancelResponse).json()
  assert.equal(cancelled.status, 'CANCELLED')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  await page.locator('.assistant-pet-panel').getByText('任务已取消', { exact: false }).first()
    .waitFor({ timeout: 15000 })
  assert.equal(errors.length, 0)
  await page.screenshot({ path: path.join(evidence, 'cancelled-after-reload.png') })
  await fs.writeFile(path.join(evidence, 'summary.json'),
    JSON.stringify({ taskId, status: cancelled.status, pageerrorCount: errors.length }, null, 2))
} finally {
  await context.close()
  await browser.close()
}
~~~

此脚本只证明排队取消/登录/刷新，不能作为运行中取消通过证据。继续按UI-01/02扩充：用隔离Worker模型stub的IPC/Event保持RUNNING，通过真实/request-cancel进入CANCEL_REQUESTED，验证按钮禁用、连点请求次数、放行后CANCELLED；再分别做超时、401/500、断网恢复、历史会话多任务和人工确认重试。浏览器route-mock结果单列，不能替代真实API/DB/Worker验证。先读当前可访问性树和实际响应再写新selector，当前selector漂移则记录差异，不盲猜。

## 附录C：最终报告格式和验收门槛
请生成 report.md、可机读results.json、defects.json及evidence索引，至少包括：

1. 环境：OS/CPU/RAM、Python/Node/依赖版本、源码HEAD+dirty摘要+哈希、数据库版本/隔离级别、API/前端/Worker映射与PID、测试时间和时区；secret只记“已配置/未配置”。
2. 范围和执行账本：每条实际命令、cwd、开始结束、exit code、对应case与产物路径；当前补丁完整组合回归的明确版本和结果。
3. 数量表：按case去重后的总数、PASS、FAIL、BLOCKED、NOT_RUN、SKIPPED、N/A；pytest参数展开/复跑单独列，能回算到JUnit，不把skip算pass。
4. 分层结果：静态/API/真实多进程/故障/幂等/SQLite/PG/Mock模型/真实DeepSeek/浏览器真实登录与联动/构建/性能。每层说明实际做了什么及未做什么。
5. 数据库结果：关键SQL与参数标签、状态序列、owner/attempt、根键唯一计数、正文SHA、作答/画像/路径/消息关联、迁移/FK检查；不复制私人正文或token。
6. 关键日志与并发证据：调用计数、IPC/SQL marker、pid、时间窗、deadline/heartbeat配置和有效阈值；证据没有则不编造。
7. 缺陷清单：ID、P0/P1/P2/P3、影响、版本、预置、完整复现、实际/预期、稳定性、当前文件+行号、证据、最小修复建议与回归用例。未复现风险另表。
8. 历史限制逐项复核：最终组合、真实DeepSeek取消、登录UI、PG/MySQL、全站E2E、共享迁移。分别标当前新证据/仍待验/不适用，不能只重复历史结论。
9. 最终结论只用以下之一，并列明确范围、阻断点、后续条件及责任：
   - PASS：明确范围的所有必需测试实际通过。
   - CONDITIONAL PASS：没有已确认阻断缺陷，但有具体限制/待验条件；不能隐藏核心缺证。
   - FAIL：已确认阻断缺陷，或已执行关键验收标准不满足。
   - BLOCKED：核心环境/权限/依赖/工具不足，无法作足够判断。
10. 环境回收：本轮PID停止、故障释放、连接/浏览器关闭、临时库及证据保留位置，未触碰共享业务数据。

特别禁止：把测试结束当测试通过、把Mock当真实DeepSeek、把build当UI、把SQLite当PG/MySQL、把单元通过当生产可部署、把开发报告的通过数当你执行的结果。费用不可见时直说不可见，停止后续保存不等于取消计费。

现在开始第1步，完成可执行工作直到报告。若遇到能力阻塞，继续执行不依赖它的测试，再准确报告不足；不要仅给计划后结束。

