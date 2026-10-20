# 小智助手增量升级说明（2026-10-18）

2026-10-19 可靠性续验：心跳线程自动处理执行期限，过期租约禁止续期及写入，旧执行代次禁止提交；独立进程终止恢复、模型返回期间取消与题组 flush 冲突已验证。最新文件清单、配置、验证边界见 [小智任务可靠性验收记录](assistant-task-reliability.md)。

## 项目审查结论

本仓库实际采用 Vue 3 + Vite + Element Plus 前端，以及 FastAPI 多服务后端，数据库由 SQLAlchemy 和 Alembic 管理。用户服务 8001、智能体服务 8002、资源服务 8003、评价服务 8004、教师服务 8005、系统服务 8006。原提示中的 Spring Boot 是背景假设；本次按真实技术栈接入，未新建并行后端。

| 能力 | 原有实现 | 本次接入 | 状态 |
| --- | --- | --- | --- |
| 小智悬浮入口 | `AssistantPet.vue` 简易形象与聊天弹窗 | 蓝白 SVG、状态表情、吸边拖动、持久位置、工作台模式 | 已实现，浏览器已验收 |
| 会话与问答 | `ChatService`、`chat_sessions`、`chat_messages` | 小智复用会话；分层讲解模式、真实模型 SSE 流、受控学情上下文、来源与无资料降级提示 | 已实现，真实模型和浏览器流已验证 |
| Markdown 与公式 | 现有 MarkdownIt + KaTeX 工具 | 助手复用；外部链接安全属性 | 已实现，浏览器已验收 |
| 知识检索 | `KnowledgeBaseService`、可选 Chroma | 无空格中文问题匹配；助手搜索与来源展示 | 本地检索已验证；Chroma 深度联动未完整验收 |
| 学情 | `UserProfile`、`AnswerRecord`、`TranscriptScore` | 只从当前用户记录生成可解释摘要；无记录时明确提示 | 已实现，隔离库与浏览器已验证 |
| 多智能体与资源 | `CoordinatorWorkflow`、资源/练习/路径服务 | 有界任务路由、现有 Agent 调度、任务和执行结果落库；课件在资源库可读；11–20 题分批生成 | 单项课件、15 道练习及联合任务已在隔离库验证；外部图谱同步未验证 |
| 资源权限 | 公共资源目录与个人生成资源共用读取接口 | 公共目录继续开放；个人生成资源的列表、详情及下载按登录用户隔离 | 自动化隔离测试已通过 |
| 异步任务 | 原有生成请求主要同步 | `assistant_tasks`、执行记录、轮询及刷新恢复、独立 Worker 原子领取 | 支持 background / worker 配置；双进程和真实模型链路通过 |
| 学习记忆 | 现有画像和会话历史 | 用户确认的目标/偏好/重点记忆可查看、修正、删除，按用户和课程隔离；默认不发送给模型 | 基础 CRUD 已实现，浏览器已验收 |

## 调度和数据边界

`POST /assistant/chat` 从登录令牌取得用户 ID。`action` 只接受 `qa/profile/search/courseware/exercise/plan/recommend/combined`；自然语言使用有界规则选择动作，不能决定任意 Python 函数、SQL 或 Shell。问答复用 `ChatService`；学情直接读取已有表；资料搜索复用 `KnowledgeBaseService`；推荐复用现有 `ResourceManager`；资源类任务通过 `CoordinatorWorkflow` 调用已有画像、知识库、资源、练习和路径 Agent。复合任务先检索和生成资源，再执行路径规划。课件和练习卡片只在拿到真实资源 ID、练习 ID 时展示；学习路径先返回草案，用户确认后才保存和显示路径入口。

复合任务只执行用户实际请求的课件、练习和计划阶段；没有请求计划时不会创建计划。历史信息默认不用于生成；主动启用设置，或本次明确提出“根据我的学习情况”“我的错题”等需求时才读取本人数据。关闭时协调器跳过画像读取，并给生成器传递空的历史禁用快照，避免服务自行回退读取；缺失评分显示为 null，不把零分当作真实学情。

附件问答、课件、练习和复合生成共用现有 TXT/Markdown/PDF/DOCX 提取能力。任务仅持久化附件 ID，执行时重新检查归属并取有界文本；删除后的排队附件会使任务明确失败。附件作为不可信参考材料传给生成器，不获得工具权限，也不会伪造成教材页码；返回实际文件名来源。教师助手目前开放答疑与检索，学生专属生成入口按服务端能力隐藏。

## 作答、学情与权限闭环

生成练习在原 `Exercise` 内容中记录所有者，评价与收藏拒绝跨用户使用个人生成题。已存题目的答案、题型、难度和解析以服务端数据为准；评分不会覆盖原题和选项。生成器只向当前用户模型请求提供本人近期题目，历史来源不明的旧题不进入私人题目参考。外部自定义题目的字符串标识按用户命名空间转换，避免不同学生碰撞。

评价提交与阶段/月度报告接口统一要求登录；请求中的用户标识必须匹配当前用户或既有管理员权限。教师读取学生报告须有本人班级的有效成员关系。练习提交后直接更新原 `UserProfile`，小智学情任务从实际 `AnswerRecord` 与掌握记录读回，不另建一套权威画像。

`POST /evaluation/practice/submit` 和 `POST /evaluation/submit` 支持可选 `client_request_id`（8–80 位字母、数字、下划线或连字符）；批量提交中每条记录也可提供。前端在发送前将本题本次请求标识写入已有练习进度，刷新与网络重试复用它。回执保存在原 `AnswerRecord.evaluation_json`，无需新增表；同一用户事务加锁后再次检查，同键同答案返回原结果，改题或改答案返回 409。新标识表示新的练习尝试；旧客户端不传标识时仍按每次提交计分。数据库写入和消息队列发布之间没有持久 Outbox，进程恰在提交后退出时的消息补发仍未实现。

任务在 `assistant_tasks` 中保存请求、状态、Worker 标识、执行代次、开始时间和心跳，`assistant_agent_executions` 保存实际 Agent 调用摘要。任务完成后在现有 `chat_messages` 写入一条助手消息。相同用户的 `client_request_id` 可避免重复创建任务。访问任务、会话、学情时均按登录用户 ID 过滤。默认 `background` 模式通过 HTTP 后台执行；`worker` 模式只入队，由独立进程轮询同一张任务表，并以条件更新原子领取。Worker 重启后可继续领取 `PENDING`。`/cancel` 对 `PENDING` 原子取消，对 `RUNNING` 返回 409；`/request-cancel` 对运行中任务持久化 `CANCEL_REQUESTED`，协调器在 Agent 边界停止，生成器在模型调用前后和写入前检查执行权。已发出的模型请求不能保证立即终止或免除费用。Worker 心跳与最长执行时间分别判断失活和超时；只读任务在限次内自动重新排队，生成类任务进入 `TIMED_OUT`，经用户确认后才能重试。原任务 ID 延续为资源和题组的稳定操作键，数据库唯一约束保证已提交成果不会重复写入。保存路径仍需用户确认，练习计分仍由原提交回执保护。

状态兼容映射：`PENDING` 表示等待（QUEUED），`SUCCEEDED` 表示完成（COMPLETED）；另外使用 `RUNNING`、`CANCEL_REQUESTED`、`CANCELLED`、`FAILED`、`TIMED_OUT`。旧接口字段不改名。取消请求只允许 `RUNNING → CANCEL_REQUESTED → CANCELLED`；任务已完成时返回既有状态。失活的只读任务 `RUNNING → PENDING`，最长两次执行，按配置指数退避；生成任务失活不自动重放。

## API

所有下列接口都需要 `Authorization: Bearer <token>`，由服务端令牌读取用户身份。

| 方法和路径（8002） | 请求 | 响应 | 常见错误 |
| --- | --- | --- | --- |
| `POST /assistant/chat` | `message` 必填；可选 `conversation_id`、`client_request_id`、`action`、`knowledge_point`、`exercise_count`（3–20）、`teaching_mode`、`use_learning_context`、`attachment_ids`（最多 3 个） | `kind=message` 时含真实回答；`kind=task` 时含 `task.id` 和状态 | 401 未登录、403 角色不符、404 会话或附件不可访问、422 参数/动作错误、503/504 模型错误 |
| `POST /assistant/chat/stream` | 与 `/assistant/chat` 同结构，仅支持 `qa` | UTF-8 SSE：`start`、`stage`、`delta`、`final` 或 `error`；按 `client_request_id` 重试不会重复保存已完成回答；中断后页面保留同一请求标识重试 | 401/404/409/422；流建立后的模型错误由 `error` 事件返回 |
| `GET /assistant/tasks?conversation_id=&limit=` | 会话过滤、上限 100 | 当前用户任务列表 | 401 |
| `GET /assistant/tasks/{id}` | 路径 ID | 状态、结果、执行记录 | 401/404 |
| `POST /assistant/tasks/{id}/cancel` | 路径 ID | 已取消的待执行任务 | 401/404/409 已开始执行 |
| `POST /assistant/tasks/{id}/request-cancel` | 路径 ID | 已请求运行中任务在安全边界停止 | 401/404；已完成任务保持原状态 |
| `POST /assistant/tasks/{id}/retry` | 失败任务 ID；可选 `client_request_id`；课件、练习、路径和复合任务需 `confirm_side_effects=true` | 新任务 ID、原任务 ID；相同请求标识重放返回同一任务 | 401/404/409 非失败任务、标识冲突或生成类风险未经确认 |
| `POST /assistant/tasks/{id}/confirm-path` | 成功的学习路径或复合任务 ID；草案由服务端任务结果读取 | 本人确认后持久化新路径，返回更新后的任务及路径卡片；重复确认返回同一结果 | 401/404 非本人任务；409 无可确认草案；422 草案不完整 |
| `GET /assistant/capabilities` | 无 | 当前服务动作和能力边界 | 401 |
| `POST /assistant/attachments` | multipart `file`；TXT/Markdown/PDF/DOCX，最大 5MB | 当前用户附件 ID、文件名、类型、大小 | 401/413/422 不支持、无可提取文本或格式异常 |
| `GET /assistant/attachments` | 无 | 当前用户附件列表，上限 100 | 401 |
| `DELETE /assistant/attachments/{id}` | 路径 ID | 删除当前用户附件提取文本 | 401/404 |
| `GET /assistant/memory` | 无 | 当前用户已确认的记忆，上限 100 | 401 |
| `POST /assistant/memory` | `memory_type`、`content`、可选 `course_key` | 新记忆，来源标记为 `user_confirmed` | 401/422 |
| `PUT /assistant/memory/{id}` | 同上 | 修正后的记忆 | 401/404/422 |
| `DELETE /assistant/memory/{id}` | 路径 ID | 删除结果 | 401/404 |

会话创建、历史、详情与删除继续使用现有 `/chat/sessions` 路由。任务状态为 `PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED`。学习计划任务的 `SUCCEEDED` 表示草案已生成；需 `result.path_saved=true` 才表示用户已确认保存。确认只从服务端任务读取草案，未接受客户端自行提交的计划正文；SQLite 写锁串行处理同一任务确认，路径数据中的任务标识支持保存后重放。资源结果保存在现有资源、练习和学习路径模块。

学习任务的新会话、首条消息和任务记录在同一事务中创建。并发重放相同请求只返回同一任务，不产生多余空会话；改变任务类型、主题、题量、内容或明确会话后复用请求标识返回 409。模型问答的 SSE 重放机制沿用现有消息上下文实现，这里没有宣称所有并发问答均具有数据库级唯一保证。

现有资源服务 `GET /resources` 和 `GET /resources/{id}` 仍允许匿名读取公共资源。带 `generated_for_user_id` 的个人生成资源只在本人令牌下列出或读取；下载也要求本人令牌。教师不能通过资源状态修改或删除接口操作其他用户的个人生成资源，管理员仍保留管理权限。资源详情入口为 `/student/resources?resource=<id>`。

生成资源的旧 `POST /resources/{id}/export` 曾返回一个没有对应下载路由的地址；该旧接口仍明确返回 `501`。新增 `GET /resources/{id}/export.docx`，需要登录，个人资源仅本人可下载，公共资源允许登录用户下载。它直接返回真实 Word 文件字节，支持生成的 Markdown/TXT 课件、笔记和试卷；正文缺失、不支持的类型或正文超过 50 万字符返回 422。文档包含标题、段落、列表、表格和静态代码，数学公式保留 LaTeX 文本，没有宣称转成 Word 公式；不会抓取外部图片或执行代码。资源页加载正文后才显示“下载 Word 文档”。PDF/PPTX 导出仍不可用。已有真实文件的“下载课件文件”入口继续使用 `/resources/{id}/download`。资源状态和删除入口只向教师、管理员显示。

## 前端组成

`AssistantPet.vue` 仍由 `AppLayout.vue` 全局装载。`XiaoZhiAvatar.vue` 统一悬浮、标题、欢迎态和消息头像；支持 idle、greeting、listening、thinking、searching、working、speaking、success、encouraging、warning、error，动画可关闭并尊重 `prefers-reduced-motion`。`assistant.ts` 封装任务、记忆和资料附件接口；聊天历史继续调用 `chat.ts`。工作台左右栏与聊天区共用会话和消息状态，失败或取消的任务在刷新后仍显示，失败任务可重新提交。生成类重试先提示可能重复保存的风险。所选文档可用于问答、课件和练习生成的资料引用，历史消息显示文件名；设置中可删除已提取的资料。服务端只保存提取文本和元数据，不保存原文件。课件及推荐卡片带资源编号跳转到资源页对应详情。练习任务读取任务中保存的真实题组，再交给现有 `ExerciseView.vue` 和评价接口提交答案。学习路径草案在消息中列出阶段与任务，确认后才归档旧路径并保存新路径。学习上下文默认关闭，用户可在设置里主动启用，并指定课程；仅当前用户的全局记忆及当前课程记忆进入有界上下文。

## 配置、启动和迁移

沿用项目根目录 `.env` 中的数据库、JWT、模型与知识库配置，以及 `web-app/.env.local` 的 `VITE_*_API_BASE_URL`。不要把模型密钥写入前端。新部署的空库可以执行：

```powershell
python -m alembic upgrade head
python -m uvicorn services.agent_service.app.main:app --host 127.0.0.1 --port 8002
Set-Location web-app
npm run build
.\node_modules\.bin\vite.cmd --host 127.0.0.1 --port 5175
```

本机共享 SQLite 的 `alembic current` 没有返回版本号，属于需要先核对结构和建立安全基线的历史库；**不要对它直接执行空库迁移**。本次在隔离的临时 SQLite 上验证了从初始版本到 `20261018_0017` 的迁移，没有修改共享库的 Alembic 版本。服务启动的 `ensure_database_schema()` 会补充本次必要列和唯一索引，但这不等同于正式迁移基线。新增配置：`ASSISTANT_WORKER_HEARTBEAT_SECONDS`（默认 5）、`ASSISTANT_WORKER_STALE_SECONDS`（45，实际至少为心跳间隔的三倍）、`ASSISTANT_TASK_MAX_SECONDS`（1800）、`ASSISTANT_CANCEL_WAIT_SECONDS`（60）、`ASSISTANT_SAFE_RETRY_LIMIT`（2）、`ASSISTANT_SAFE_RETRY_BACKOFF_SECONDS`（5，指数退避上限 300）；原 `LLM_REQUEST_TIMEOUT_SECONDS`（45）仍限定模型请求。

启用持久队列时，API 与独立 Worker 必须使用相同数据库、JWT、模型与知识库配置，并均设置 `ASSISTANT_TASK_EXECUTION_MODE=worker`。在两个终端分别启动：

```powershell
$env:ASSISTANT_TASK_EXECUTION_MODE='worker'
python -m uvicorn services.agent_service.app.main:app --host 127.0.0.1 --port 8002
```

```powershell
$env:ASSISTANT_TASK_EXECUTION_MODE='worker'
python -m services.agent_service.app.services.assistant_worker
```

Worker 可用 `--once` 处理一批后退出；`--batch-size` 范围 1–20，默认 1；`--poll-interval` 默认 2 秒。SIGINT/SIGTERM 会等待当前生成返回后退出，不会假装中断模型调用。生产环境由进程管理器负责重启。Docker 可使用已通过配置检查的覆盖文件：

```powershell
docker compose -p learning -f docker-compose.yml -f deployment/assistant-worker.compose.yml config --quiet
docker compose -p learning -f docker-compose.yml -f deployment/assistant-worker.compose.yml up -d agent-service assistant-worker
```

本次只验证 Compose 配置解析，没有启动或替换已有容器。独立 Worker 没有引入新的队列服务或数据表。

## 验证记录和已知限制

- 最新回归（2026-10-18，隔离 SQLite）：`python -m pytest tests/unit/test_assistant_resource_visibility.py tests/unit/test_resource_authz.py tests/unit/test_assistant_tasks.py tests/unit/test_chat_service_titles.py tests/unit/test_ai_timeout_handling.py tests/unit/test_learning_path_prerequisites.py tests/unit/test_coordinator_sync_agents.py tests/unit/test_resource_document_export.py tests/integration/test_assistant_worker_process.py tests/unit/test_resource_generation.py tests/unit/test_learning_prompt_templates.py tests/unit/test_assistant_privacy.py tests/unit/test_evaluation_reports.py tests/unit/test_exercise_favorites.py tests/unit/test_security_auth.py -q --disable-warnings`：116 passed，479 warnings。覆盖并发 Worker、请求幂等、计划确认、附件引用、历史禁用、班级权限、评分权威数据、跨用户题目隔离、作答回执重放和并发只计一次；不代表全站回归。
- 最后一次资源权限改动后重跑 `python -m pytest tests/unit/test_assistant_resource_visibility.py tests/unit/test_resource_authz.py -q --disable-warnings`：24 项通过，覆盖教师对个人资源的修改与删除拦截，以及导出明确返回 501。
- `$env:DATABASE_URL='sqlite:///:memory:'; python -m alembic upgrade head`：内存空 SQLite 成功到 `20261017_0015`。
- `npm run build`：成功；`@vueuse`、`vis-network` 的 `INVALID_ANNOTATION` 与大 chunk 提示仍在。
- `node tests/e2e/run-assistant-pet.mjs`：桌面、移动端、拖动、工作台、动画偏好、Markdown/公式/XSS 检查通过。
- `node tests/e2e/run-assistant-profile.mjs`：在临时数据库的真实 HTTP 服务上完成登录、任务创建、无数据学情反馈及刷新恢复。
- `node tests/e2e/run-assistant-stream.mjs`：真实模型 SSE 多次增量输出、刷新恢复，以及记忆的界面创建/修正/删除通过。
- `node tests/e2e/run-assistant-retry.mjs`：隔离库中真实创建失败任务、点按钮重试、刷新后两条失败记录和重试入口仍在，浏览器无错误。
- `node tests/e2e/run-assistant-attachment.mjs`：隔离库中从浏览器上传文本，真实模型使用资料问答；刷新后附件名保留，设置中可删除提取文本，浏览器无错误。
- `node tests/e2e/run-assistant-plan.mjs`：隔离库真实 DeepSeek 生成草案，原有启用路径保持不变；取消确认、刷新恢复、保存后既有路径接口读回、重复确认均通过。已分别在 background 和独立 Worker 模式执行，浏览器无脚本错误；截图 `artifacts/global-testing/e2e/screenshots/assistant-plan-confirmed.png`。这不是全站验收，隔离环境未运行管理统计等全部服务。
- `node tests/e2e/run-assistant-resource-document.mjs`：最新真实 DeepSeek + 独立 Worker 完整链路通过（隔离库任务 22）。浏览器注册学生、上传含 XZ-TCP-042 案例的资料，生成真实课件、3 道练习及计划草案；模型正文实际使用附件案例；历史默认关闭且画像执行标记 SKIPPED。资源页预览并下载实际 DOCX，python-docx 读回 65 段、2846 字符；提交练习后携带相同请求重试返回原结果，改变答案返回 409；学情仍只读回 1 条作答与更新后的掌握记录；用户确认计划后由原路径接口读回。浏览器无脚本错误，退出码 0。证据为 `artifacts/global-testing/assistant-resource-e2e.log`、`artifacts/global-testing/e2e/screenshots/assistant-resource-document.png`、`assistant-generated-exercise-submitted.png` 和 `artifacts/global-testing/assistant-generated-courseware.docx`。未检查 Word 原生排版，Neo4j 不可达，未宣称图谱联调通过。首次重跑因隔离评价服务缺少 5185 的 CORS 来源配置在评分前失败，补配置并检查 OPTIONS 200 后全链路重跑通过。
- 配置的 DeepSeek 服务返回 HTTP 200，真实问答结果已写入隔离会话；未命中本地知识库时显示明确提示。
- 隔离数据库中真实调用现有课件生成服务和小智 `/assistant/chat`，任务为 `SUCCEEDED`，返回真实资源编号 2；`ResourceManager.get_resource(2)` 读回 3066 字符内容。该验证未使用共享业务库，且为避免外部知识图谱副作用，仅将图谱同步替换为无操作。
- 隔离数据库中对 `/assistant/chat` 发送“生成15道 TCP 协议练习题”，真实 DeepSeek 调用完成两批出题。任务 `SUCCEEDED`，结果与练习表各有 15 道，返回一个可进入现有练习页的题组卡片。
- 隔离数据库中对 `/assistant/chat` 发送“生成二十道 TCP 协议练习题”，真实 DeepSeek 两批出题，任务 `SUCCEEDED`，结果与练习表各有 20 道，未标记为部分完成。
- 修改前在隔离数据库中执行“生成 TCP 协议课件和五道练习题，并制定三天复习计划”：任务 `SUCCEEDED`，资源编号 3 可读，5 道题在练习表可读，当前用户学习路径编号 1 有 4 个阶段；执行记录包含画像、知识检索、课件生成、出题和路径规划 Agent。为避免测试环境写入外部 Neo4j，仅将课件图谱同步替换为无操作。这是旧版本记录；当前版本已用独立 Worker 重跑带附件、课件、三道练习、学情反馈和计划确认的完整浏览器链路。

### 重跑联合浏览器场景

隔离环境需同时启动用户、智能体、资源、评价服务和独立 Worker，并让 Vite 的 `VITE_*_API_BASE_URL` 指向对应端口。本次使用 8008/8009/8010/8011 和前端 5185；所有服务使用同一临时数据库及认证配置。评价等跨域服务必须设置 `CORS_ALLOW_ORIGINS=http://127.0.0.1:5185,http://localhost:5185`。不对共享业务库执行这些注册和生成测试。

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:5185'
$env:E2E_USER_URL='http://127.0.0.1:8008'
$env:E2E_AGENT_URL='http://127.0.0.1:8009'
$env:E2E_COMBINED='1'
$env:E2E_WITH_PLAN='1'
node tests/e2e/run-assistant-resource-document.mjs
```

## 实施完成情况

| 功能名称 | 原项目状态 | 本次修改 | 代码位置 | 测试状态 | 是否完成 |
| --- | --- | --- | --- | --- | --- |
| 小智形象与悬浮交互 | 简易弹窗 | 统一 SVG、状态表情、拖动吸边、工作台 | `web-app/src/components/XiaoZhiAvatar.vue`、`AssistantPet.vue` | 浏览器桌面与手机检查通过 | 基础完成 |
| 流式问答与会话 | 已有模型与会话服务 | 真实 SSE、多轮上下文、教学模式、确认记忆 | `chat_service.py`、`api/routes/assistant.py` | DeepSeek 与浏览器流测试通过 | 基础完成 |
| 学情与资料检索 | 已有画像和知识库 | 用户隔离学情、资料引用及无资料降级 | `assistant_tasks.py`、`knowledge_base.py` | 单元和浏览器无数据路径通过 | 部分完成 |
| 课件、练习及路径联合执行 | 已有生成服务 | 任务调用已有协调器；11–20 题按单次上限分批，复合任务按依赖执行；路径先预览再确认保存 | `assistant_tasks.py`、`learning_path.py`、`AssistantPet.vue` | 真实模型课件、练习和路径确认通过；附件、课件、练习评分、学情读回、计划确认的真实联合场景通过；外部图谱未联调 | 核心链路部分完成 |
| 正文预览与 Word 下载 | 普通资源详情未展示正文；旧导出返回无效地址 | 安全 Markdown/公式预览；按资源访问权限生成真实 DOCX 字节 | `ResourceView.vue`、`document_export.py`、`api/routes/resources.py` | 隔离库权限及 DOCX 解析、真实学生浏览器下载通过；Word 原生排版未检查 | 基础完成 |
| 推荐与资源隐私 | 已有推荐排序；资源公开读取 | 助手复用推荐，个人生成资源按用户隔离；移除虚假导出入口 | `resource_manager.py`、`api/routes/resources.py`、`ResourceView.vue` | 权限测试通过 | 基础完成 |
| 持久任务、记忆与附件 | 原助手未接入 | 任务/执行记录、失败重试、确认记忆、资料提取及生成引用落库 | `common/models/learning.py`、`alembic/versions/20261017_0011_assistant_tasks.py`、`20261017_0013_assistant_memories.py`、`20261017_0015_assistant_attachments.py` | 空库迁移、单元和浏览器刷新通过 | 基础完成 |
| 独立任务 Worker | 仅 HTTP 后台执行 | 复用任务表排队、原子领取、独立进程运行及 Compose 覆盖文件 | `assistant_worker.py`、`assistant_tasks.py`、`deployment/assistant-worker.compose.yml` | 双进程与真实模型浏览器链路通过；Docker 仅配置检查 | 基础完成 |
| 作答与学情闭环 | 原评价提交缺少部分认证与幂等 | 认证、本人/教师班级范围、存储答案权威、题目归属、持久作答回执 | `report_service.py`、`schemas/report.py`、`reports.py`、`common/dependencies.py`、`ExerciseView.vue` | 并发只计一次、重启重放、越权拦截测试及真实浏览器闭环通过 | 基础完成 |
| 图片 OCR | 未形成完整闭环 | 尚未实现 | — | 未验证 | 未完成 |

尚未完成整份需求：图片/扫描件 OCR、教师在助手内指定授权学生分析、PDF/PPTX 导出及全站回归。教师现有报告读取已限制班级范围。运行中取消采用协作式检查；已经发出的 DeepSeek 请求无法强行中断，已提交事务不会撤销。当前任务链的课件、练习、路径确认和计分已有各自持久化幂等保护；Neo4j 同步与消息队列发布仍没有通用 Outbox，外部写入结果未知时不能自动盲目重放。独立 Worker 使用数据库队列和执行代次；失活后只自动重试只读任务，生成任务等待人工确认。文档上传仅支持可提取文字的 TXT、Markdown、PDF、DOCX；不保存原文件，无法重新下载。Word 下载支持普通文字类生成资源，公式保留 LaTeX 原文。SSE 当前支持真实模型问答；资源类任务通过状态轮询回显。此前隔离库真实模型验证属于改动前证据；本次取消、心跳和幂等以自动化测试与前端构建验证，未在共享业务库重跑完整浏览器链路。自然语言调度仍为有界规则。旧练习所有者尚未回填，外部图谱同步未联调。
