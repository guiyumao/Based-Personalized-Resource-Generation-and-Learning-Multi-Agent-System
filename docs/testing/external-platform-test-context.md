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

