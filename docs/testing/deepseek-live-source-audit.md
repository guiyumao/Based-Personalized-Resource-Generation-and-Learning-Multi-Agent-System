# DeepSeek 真实模型链路源码核对（无费用轮次）

- 核对时间：2026-10-19 17:33（Asia/Shanghai）
- 仓库：`C:\Users\wdx\Desktop\基于大模型的个性化资源生成与学习多智能体系统`
- HEAD：`05ee287df3f548943fdebdc267109b3fedbe65a2`，工作树含既有未提交改动
- 性质：静态源码核对 + 本地桩动态验证 + 隔离数据库无费用回归；**没有任何真实 DeepSeek 计费调用**
- 结论用途：修正 `deepseek-live-test-plan.md` / `deepseek-live-test-prompt.md` 中与实现不符的配置名、调用次数、取消语义、预算口径和失败测试构造方式。

## 1. Provider 解析（决定测试是否真的命中 DeepSeek）

`services/agent_service/app/services/llm_factory.py:27-111` 的选择顺序是：

1. `QWEN_API_BASE` + `QWEN_API_KEY` → `provider="qwen"`
2. `DEEPSEEK_API_BASE` + `DEEPSEEK_API_KEY` → `provider="deepseek"`
3. `DEEPSEEK_API_BASE` + `OPENAI_API_KEY` → `provider="deepseek-generic-key"`
4. `QWEN_API_BASE` + `OPENAI_API_KEY` → `provider="qwen-generic-key"`
5. `OPENAI_API_KEY` + `OPENAI_BASE_URL` → `provider="openai"`
6. 否则 `ValueError("No LLM credentials configured.")`

关键事实：

- Qwen 专有 key 分支**先于** DeepSeek 专有 key 分支。只要 `QWEN_API_BASE` 与 `QWEN_API_KEY` 同时存在，就会静默走 Qwen，即使 DeepSeek 也已配置。
- `provider` 只写在构造参数/日志语义里，**没有作为属性挂到 ChatOpenAI 实例上**。因此“日志出现 provider=deepseek”不是请求到达 DeepSeek 的证据；必须检查实际 `base_url`/目标主机、HTTP 响应和响应模型。
- 客户端由 `ChatOpenAI(..., max_retries=0)` 构造（`llm_factory.py:186`），SDK 层不重试。
- 工厂有进程级缓存（`_cache`），key 含 `api_key`、`base_url`、`model`、`temperature`、`timeout`；换配置后必须新进程或清缓存。
- `Settings` 是 `@dataclass(frozen=True)`，字段默认值在模块导入时读取环境变量（`common/config.py:80-207`）；`_load_dotenv_file()` 用 `os.environ.setdefault` 加载 `.env`（`common/config.py:11-26`）。**进程环境变量优先于 `.env`，空字符串也算“已设置”**，可用来屏蔽 `.env` 中的 key。
- `LLM_LIGHT_MODEL` 只在 `build_for_task()` 对 `rewrite/classify/summarize` 生效（`llm_factory.py:113-117`）；课件/练习/结构化资源走 `build_chat_model()`，不受 light model 影响。
- `LLMFactory.prewarm()` 只构造客户端，不发探测请求（`llm_factory.py:119-145`），因此不会产生 token。

## 2. 超时与重试的真实分层

| 层 | 配置/位置 | 默认 | 实际行为 |
| --- | --- | --- | --- |
| HTTP 客户端单次超时 | `LLM_REQUEST_TIMEOUT_SECONDS` (`common/config.py:173`) → `llm_factory.py:31` | 45 秒 | `max(3, 配置值)`；**配置 1 秒实际是 3 秒**。作用于每个 HTTP 请求 |
| SDK 重试 | `ChatOpenAI(max_retries=0)` (`llm_factory.py:186`) | 0 | SDK 不自动重试 |
| 业务总期限 | `QA_DEADLINE_SECONDS=60`、`CHAT_DEADLINE_SECONDS=60`、`EXERCISE_DEADLINE_SECONDS=20`、`LEARNING_PATH_DEADLINE_SECONDS=30`、`COURSEWARE_DEADLINE_SECONDS=60`、`REPORT_DEADLINE_SECONDS=30` (`common/config.py:167-172`) | 见左 | 路由用 `set_trace_context(deadline_seconds=...)` 注入（`api/routes/qa.py:37`、`chat.py:92`、`learning.py:63,321`、`resources.py:31`、`agents.py:32-58`、`evaluation_service/.../reports.py:62`）。只在**开始新阶段/新模型调用前**检查（`common/performance.py:116-122,262`），不会中断已经在途的 HTTP 请求 |
| 内容审计重试 | `MAX_TOTAL_RETRIES` (`common/config.py:166`) | 2 | 课件/练习被审核拒绝时最多再生成 2 次（即最多 3 次生成）；不是 3 次重试 |
| Worker 任务期限 | `ASSISTANT_TASK_MAX_SECONDS=1800` | 1800 秒 | 心跳与最终提交条件（`assistant_execution.py:23-33`） |
| Worker 心跳/失活 | `ASSISTANT_WORKER_HEARTBEAT_SECONDS=5`、`ASSISTANT_WORKER_STALE_SECONDS=45` | 5/45 秒 | 失活阈值至少为心跳 3 倍 |
| 取消等待 | `ASSISTANT_CANCEL_WAIT_SECONDS=60` | 60 秒 | `CANCEL_REQUESTED` 超时后收回执行权（`assistant_tasks.py:698-723`） |
| Search | `deepseek_search.py:60` | 20 秒 | 2 次尝试，间隔 0.75 秒，只对超时/408/429/5xx 重试 |
| Fetch | `deepseek_search.py:60` | 45 秒 | 同上；Fetch 还做 URL/IP 公网校验 |

**不存在的配置名**：

- `LLM_TOTAL_TIMEOUT_SECONDS`：仓库中不存在。
- `LLM_MAX_TOTAL_RETRIES`：仓库中不存在；真实名是 `MAX_TOTAL_RETRIES`，默认 2，不是 3。

旧计划第 51 行写“`LLM_TOTAL_TIMEOUT_SECONDS` 默认 40；`LLM_MAX_TOTAL_RETRIES` 默认 3”，与源码不符，已修正。

## 3. 每类业务的真实出站调用次数

计数以“每次成功进入模型的 HTTP 请求”为单位；超时、429、5xx、断流以及取消时在途的请求也可能计费，必须单独记录。

| 场景 | 典型调用 | 上限（含审计/重试） | 依据 |
| --- | --- | --- | --- |
| 课件 courseware | 1 次生成 | 3 次生成 + 最多 3 次审计 = 6 | `resource_generation.py:1250-1268,1422-1486`；默认 variant 1 |
| 练习单批 | 1 次生成 | 3 次生成 + 最多 3 次审计 = 6；LLM 失败时可能走确定性 fallback，实际模型成功 0 次 | `exercise_generation.py:67-84,300-386` |
| 练习 20 题 | 2 次生成（10+10） | 每批最多 6，共 12 | `assistant_tasks.py` 首批 `min(10, n-3)`，第二批剩余；`exercise_generation.py` 审计重试 |
| 结构化 resource（mind_map/code_case/video_script） | 1 次生成 | 2（规则审计不命中时追加 1 次 LLM 审计） | `resource_generation.py:693-713,1012-1039`；`audit_service.py:116-158` |
| 自由问答 QA | 1 次（回答+建议合并在一个 JSON bundle） | 1，另加用户显式请求的课件/练习 | `qa_service.py:849-920` |
| 小智复合任务 | 按请求的成果数 | 各成果上限相加 | `coordinator.py:344-536`；只执行请求的 agent |
| 知识学科规划 | 1 | 1 | `knowledge_construction.py:90-110` |
| 知识点综合草稿 | 1 | 1 | `knowledge_construction.py:54-74` |
| 单点建设 | 1 search + 最多 2 fetch + 1 model | 4 | `knowledge_construction.py:190-250`；fetch 最多 2 个来源 |
| 图谱后台补全 | 0–1（异步，可能不发生） | 1 | `coordinator.py` / graph enrich；不能按“必然 1 次”计 |

旧计划把 DS-02/03/04 写成固定 1 次、DS-05 写成 1–2 次、DS-06 写成 1 次、DS-07 写成 4 次，均未覆盖审计/重试和 fallback，已改为“典型值 + 上限 + 实测计数”。

## 4. 审计状态的真实含义

`AuditService` 有三种状态（`audit_service.py:22`）：

- `passed`：规则或 LLM 审核通过。
- `rejected`：规则或 LLM 明确拒绝。
- `unavailable`：审核调用抛异常，代码返回 `AuditDecision(True, "unavailable", ...)`（`audit_service.py:203-204`）。**`passed=True` 只是为了不阻断生成，不表示审计通过。**

因此：

- `audit_status in {"passed", "unavailable"}` 只能说明“未被拒绝”，不能写成“审计通过”。
- 证据表必须把 `unavailable` 单列，并记录原因（如审计超时/鉴权失败）。
- 课件/结构化资源的规则审计通常不产生额外模型调用；只有规则不命中主题时才调用 LLM 审计。

## 5. 取消的真实语义（协作式，不是远端中止）

入口：`POST /assistant/tasks/{task_id}/request-cancel`（`api/routes/assistant.py:353-375`）。

- 只有 `RUNNING` 会原子转 `CANCEL_REQUESTED`；任务已终态或已结束时，接口返回当前状态（HTTP 200），不会制造 `CANCEL_REQUESTED`。
- `CANCEL_REQUESTED` 是短暂中间态，Worker 完成当前步骤后转 `CANCELLED`；不能要求每次都捕获到该中间态，也不能把“没捕获到”判为失败。
- 协调器只在 Agent 边界检查取消（`coordinator.py:344-355,356-536`）；课件/练习在模型调用前后检查执行权（`resource_generation.py:584-586,706-708`；`exercise_generation.py:208,236,353,360`）。
- 写入在同一事务里用条件 UPDATE 围栏（`assistant_execution.py:52-71`；`resource_generation.py:640,646`；`exercise_generation.py:1973,1983`）。取消后迟到结果不能提交。
- **在途 HTTP 请求没有可跨线程安全中止的句柄**；取消不能保证远端立即停止执行或停止计费。`docs/assistant-task-reliability.md:63` 已明确这一点。
- 同步请求（`ASSISTANT_TASK_EXECUTION_MODE` 非 worker / 无 `current_execution`）不能强行中止；取消/异步链路必须用独立 Worker。

旧计划 DS-23 的“运行中取消 → 远端停止后续调用”和“必须观测到 `CANCEL_REQUESTED`”都过度承诺；正确结论应是：

> 已验证本地停止后续调度与成果提交；远端在途请求是否停止执行或计费，无法确认。

## 6. 预算覆盖范围（重要漏洞）

`knowledge_budget.reserve_usage(kind)`（`knowledge_budget.py:20-63`）的实际调用点只有：

- `deepseek_search._post()`：`search`/`fetch`，每次出站尝试前预留（`deepseek_search.py:56-75`）。
- `knowledge_construction.synthesize_point()` 与 `plan_subject()`：`model`，调用前预留（`knowledge_construction.py:67-69,101-103`）。

**没有覆盖**：普通问答、自由对话、SSE、课件生成、练习生成、结构化资源、学习路径、画像分析、成绩报告、小智普通生成任务。这些路径的模型调用不会被 `knowledge_budget` 拦截。

预算作用域：

- 全局 `day:YYYYMMDD` 默认 100，`month:YYYYMM` 默认 1000（`knowledge_budget.py:25`）。
- 任务作用域 `task:{id}` 默认 model 1、search/fetch 2；维护任务从 policy 读 `max_*_calls`（`knowledge_budget.py:31-35`）。
- 环境变量实际拼法是 `KNOWLEDGE_{KIND}_{PERIOD}_LIMIT`（如 `KNOWLEDGE_MODEL_TASK_LIMIT`、`KNOWLEDGE_SEARCH_DAY_LIMIT`），不是模糊的 `KNOWLEDGE_*_LIMIT`。
- 预留在出站前完成；但预留在重试循环内，**每次尝试都计数**，这是保守的，不是“成功次数”。
- 预算计数基线只能写成“本轮请求计数从零开始”；不能暗示账户历史消耗为零。

因此本轮必须用独立计数代理/日志记录所有出站尝试，不能依赖知识预算保护全部场景。

## 7. Search / Fetch

实现：`services/agent_service/app/services/deepseek_search.py`。

- `_ROOT` 默认 `https://api.deepseek.com`（第 16-20 行），可用 `DEEPSEEK_SEARCH_BASE` 覆盖（本轮为计数/网关新增，默认行为不变）；`DEEPSEEK_API_BASE` 不影响 Search/Fetch。
- Search：`POST /v1/tools/search`，body `{"query": ..., "count": ..., "need_content": false}`，`count` 1–5，query 1–128 字符（第 81-97 行）。
- Fetch：`POST /v1/tools/fetch`，body `{"url": ...}`；要求 URL 为公网 http(s)，拒绝内网/凭据 URL（第 25-49、99-117 行）。
- 返回：Search 取 `results[].title/url/summary|snippet`；Fetch 取 `content`、`title`、`url|final_url`，截断 50000 字符，并对 `sk-...`/`Authorization: Bearer ...` 做脱敏。
- 重试：2 次，0.75 秒间隔；每次尝试前 `reserve_usage`。
- **本机环境阻断**：`api.deepseek.com`、`api-docs.deepseek.com`、`example.com` 均被 DNS 解析到 `198.18.x.x`（fake-IP/代理地址）。`_resolve_public_host()` 要求所有解析地址 `is_global`，因此 `fetch_source()` 会把任何公网 URL 判为 `Invalid source URL`。本轮 DS-21/DS-22 的 Fetch 无法在该 DNS 环境下执行；需要用真实 DNS 或受控解析器，且不能放宽 SSRF 规则。
- Search/Fetch 默认根地址是 `https://api.deepseek.com`；本轮新增 `DEEPSEEK_SEARCH_BASE` 覆盖（默认不变），供受控网关/代理计数。经网关的正式验收必须明确标记“经网关访问”，不能写成官方直连。

## 8. 现有 live 测试的实际行为

`tests/integration/test_live_llm_resources.py`：

- 修改前只在 `RUN_LIVE_LLM=1` 时收集；修改后还要求 `DEEPSEEK_LIVE_PAID_ACK=1`，否则模块级 skip。`RUN_LIVE_LLM` 单独不再能出站。
- 修改前 `_credentials_configured()` 接受 Qwen/DeepSeek/OpenAI 任一组合，**不保证命中 DeepSeek**；修改后只接受 DeepSeek 配置，并在 module fixture 中检查实际 `base_url` 主机。
- 修改前 `test_live_non_json_answer_is_rejected` 通过 monkeypatch 把提示词替换成“只写散文”来逼模型输出非 JSON；修改后该用例已删除，失败语义移到本地 HTTP 桩。
- 修改前 `test_live_timeout_is_a_real_error` 把 `llm_request_timeout_seconds` 设为 1，但工厂会钳到 3 秒；修改后该用例已删除，本地桩验证真实 3 秒行为。
- happy path 仍接受 `audit_status in {"passed", "unavailable"}`，但现在对 `unavailable` 发 warning；文档要求单列，不能算审计通过。
- 清理只删除 `Resource` 行；练习、任务、附件等其他产物没有通用清理。本轮 INC-01 就留下了 4 个 `knowledge_points` 行，资源行被夹具删除。
- 任务链单元套件必须在默认 `background` 模式下运行；如果全局设置 `ASSISTANT_TASK_EXECUTION_MODE=worker`，`assistant_client` 创建的请求会停留在 `PENDING`，产生 9 个与代码无关的失败。worker 专项测试在用例内部自行 monkeypatch 模式。本轮的第一次任务链运行就复现了这个调用方式问题，第二次按默认模式 50 passed。

## 9. 本轮环境事实（决定了哪些用例只能 BLOCKED）

- `.env` 中 `DEEPSEEK_API_KEY` 存在，但**存在密钥不等于费用授权**。本轮没有用户对 Chat/Search/Fetch 的预算授权。
- **INC-01 事故**：为验证 live 闸门执行 `RUN_LIVE_LLM=1` 时，PowerShell 的 `$env:DEEPSEEK_API_KEY=""` 删除了变量，`.env` 的真实密钥被加载，6 个 live 测试执行，至少 4 次真实结构化生成成功。金额/Token/响应模型/请求 ID 未捕获；详见 `artifacts/deepseek-live-20261019-173354/` 的 `README.md`、`request-ledger.jsonl`、`evidence/live-gate.log`。事后新增 `DEEPSEEK_LIVE_PAID_ACK` 第二道闸门。
- DNS：`api.deepseek.com → 198.18.0.215`，`api-docs.deepseek.com → 198.18.1.110`，`example.com → 198.18.1.111`。这是本机代理/fake-IP，不是可证明的官方直连地址。
- 因同一 fake-IP，`web_fetch` 访问官方文档被拒绝；本轮只能通过搜索结果标题确认 `Search & Fetch` 文档存在，**未能逐字核对官方请求/响应契约**。
- Python 3.12.3；`langchain_openai`、`pytest`、`httpx`、`chromadb` 可用。
- 本轮不启动真实 API/Worker 服务，不触碰共享 `learning_system.db`；无费用回归使用独立 SQLite。

## 10. 已修正的文档口径

1. 删除不存在的 `LLM_TOTAL_TIMEOUT_SECONDS` / `LLM_MAX_TOTAL_RETRIES`，改为 `MAX_TOTAL_RETRIES=2` 和真实业务期限。
2. “1 秒超时”改为“配置 1 秒会被钳到 3 秒；验证真实生效值”。
3. 非 JSON/429/5xx/断流改为本地 HTTP 桩构造，不再要求模型“必须输出错误”。
4. 取消改为：接受终态/竞态，不强制捕获 `CANCEL_REQUESTED`；只承诺本地停止后续调度与写入，不承诺远端停止计费。
5. 预算表改为“建议上限（不等于授权）”；增加“本轮从零计数”的说明。
6. 练习 live 验收必须检测 `deterministic_fallback`，避免模型 0 成功却报告生成成功。
7. 证据层级加入“本地桩 / 隔离集成 / 真实直连 / 经网关”区分。
8. Search/Fetch 与 Chat 分别计数；网关限制与 fake-IP Fetch 阻断单列 BLOCKED。
9. live 套件增加 `DEEPSEEK_LIVE_PAID_ACK=1` 第二道闸门；仅 `RUN_LIVE_LLM=1` 不出站。
10. 文档明确 PowerShell `$env:VAR=""` 会删除变量，不能用它清空 `.env` 密钥；无费用运行改用非空哨兵或本地假地址。

## 11. 仍未解决、需要授权或环境条件的缺口

- Chat 真实调用：需要用户明确授权（次数/Token/金额/时长）与可用预算；不能仅凭 `.env` 密钥。
- Search/Fetch：需要单独授权与开通；且当前 DNS 下 Fetch 的公网校验会失败。
- 官方文档逐字核对：需要可访问 `api-docs.deepseek.com` 的网络路径。
- 真实 API/Worker/浏览器闭环：需要隔离端口、独立账号、独立数据库与前端构建。
- 远端计费证据：需要供应商账单或请求级 usage/账单导出；本地日志不能证明远端是否计费。
