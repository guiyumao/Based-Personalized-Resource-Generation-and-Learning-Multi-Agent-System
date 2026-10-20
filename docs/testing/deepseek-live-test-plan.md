# DeepSeek 真实模型受控测试清单（Live Test Plan）

- 版本：v1.1，2026-10-19（Asia/Shanghai）
- 适用项目：基于大模型的个性化资源生成与学习多智能体系统
- 配套执行 Prompt：`docs/testing/deepseek-live-test-prompt.md`
- 源码核对：`docs/testing/deepseek-live-source-audit.md`（本版所有配置名、次数、超时、取消语义均以该核对为准）
- 定位：本清单**只列出必须使用真实 DeepSeek 才能验收的测试**。不涉及可由 Mock/本地 HTTP 桩/隔离集成完成的用例（那些走 `tests/unit`、`tests/integration` 无费用套件）。
- 状态前提：本轮未获 Chat/Search/Fetch 的费用授权。除 **INC-01 未授权事故**意外执行的 DS-02/03/04/28 外，其余真实调用用例均为 **BLOCKED/NOT_RUN**；事故结果不能作为授权验收通过，证据与根因见 `artifacts/deepseek-live-20261019-173354/` 与 `docs/testing/deepseek-live-source-audit.md` §9。
- **建议预算不是授权**：§4 的数字只是测试规模建议；未获用户逐项确认前不得出站。获得一次性范围与总预算授权后，可在范围内连续执行并汇报，不逐 Tier 重复索要确认；新增服务、扩大预算或高风险重放仍需再次确认。

---

## 0. 授权前置（不满足则全部 BLOCKED）

1. 持有人明确授权使用**专用测试密钥**（非生产主密钥），且账户有可用余额；**`.env` 或环境里存在密钥本身不等于授权**，不得据此出站；
2. 明确授权 DeepSeek **Chat Completions**；如要测来源管线，还需授权已开通的 **Search/Fetch 工具能力**（`/v1/tools/search`、`/v1/tools/fetch`，与 Chat 是独立计费能力，未开通时相关用例单列 BLOCKED，不伪造结果）；
3. 明确本轮最大出站尝试次数、输入/输出 Token、总执行时长、金额上限或 Token 预算（见 §4）；未给出金额费率时金额记“未知”，不得记 0；
4. 已按 §3 完成隔离环境，且所有服务、Worker、浏览器指向同一隔离数据库；
5. 若用户一次性给出范围与总预算，可在范围内连续执行并汇报进度；否则每完成一个 Tier 汇报并等待确认。

证据要求：开工前建立 `request-ledger.jsonl`，记“**本轮请求计数从零开始**”，不得写成“账户历史消耗为零”；密钥不写入任何报告、日志、截图（用 `sk-***` 脱敏）。

---

## 1. 为什么必须真实 DeepSeek

- **提示词工程只在真实模型上暴露**：结构化 JSON 契约、严格字段、题答一致性、超长指令遵从、中文课程语境，全部依赖真实生成，Mock 无法覆盖。
- **取消与计费语义**：浏览器断开 SSE、`/request-cancel` 协作取消、Worker 停止后续动作、远端模型是否继续计费，是四个不同层面；只有真实远端请求能观察“取消后是否还有后续模型调用”。
- **真实超时/限流/非 JSON 行为**：真实端点的 TCP/HTTP 行为与假桩不同（部分用例代码已存在，见 DS-25~DS-28）。
- **V8.3 知识链路**：大纲生成、来源综合、发布后检索验证、Search/Fetch 证据链，必须真实联网与真实生成。
- **构建成功、健康检查 200、Mock 用例通过、历史报告通过，都不等于真实模型链路可用**。

## 2. 真实计费通道（两类，分别计数）

| 通道 | 代码位置 | 端点 | 计费 | 强制路由 |
| --- | --- | --- | --- | --- |
| Chat 补全 | `services/agent_service/app/services/llm_factory.py` → `ChatOpenAI(max_retries=0)` | 兼容 OpenAI 的 Chat Completions | 按 token | 必须只配 DeepSeek，清空 Qwen/OpenAI；实际 `base_url` 与响应模型都要留证 |
| Search/Fetch | `services/agent_service/app/services/deepseek_search.py`（`search_sources` / `fetch_source`） | `https://api.deepseek.com/v1/tools/search`、`/v1/tools/fetch` | 独立调用计费 | 同一 `DEEPSEEK_API_KEY`；根地址默认官方，可用 `DEEPSEEK_SEARCH_BASE` 覆盖；`DEEPSEEK_API_BASE` 不生效；内置 SSRF 公网校验 |

### 模型工厂优先级（读源码确认，必须用环境变量强制命中 DeepSeek）

`llm_factory.build_chat_model()` 的选择顺序：
1. `QWEN_API_BASE` + `QWEN_API_KEY`（**通配分支优先**）
2. `DEEPSEEK_API_BASE` + `DEEPSEEK_API_KEY`
3. `DEEPSEEK_API_BASE` + `OPENAI_API_KEY`（generic-key）
4. `QWEN_API_BASE` + `OPENAI_API_KEY`
5. `OPENAI_API_KEY` + `OPENAI_BASE_URL`

因此真实 DeepSeek 测试启动前必须：`QWEN_API_KEY=""`、`QWEN_API_BASE=""`、`OPENAI_API_KEY=""`，只保留 `DEEPSEEK_API_KEY` 与 `DEEPSEEK_API_BASE`（默认模型 `deepseek-chat`，可用 `DEEPSEEK_MODEL` 指定）。**否则调用会被静默路由到 Qwen，DeepSeek 结论无效。**

### 已知模型配置（读源码确认）

- `LLM_REQUEST_TIMEOUT_SECONDS` 默认 45，但工厂实际使用 `max(3, 配置值)`；**配置 1 秒实际是 3 秒**，不能写“1 秒预算”。旧文档中的全局总超时/总重试配置名在仓库中**不存在**，不要照抄。
- 业务总期限用 `QA_DEADLINE_SECONDS=60`、`CHAT_DEADLINE_SECONDS=60`、`EXERCISE_DEADLINE_SECONDS=20`、`LEARNING_PATH_DEADLINE_SECONDS=30`、`COURSEWARE_DEADLINE_SECONDS=60`、`REPORT_DEADLINE_SECONDS=30`；只在开始新阶段/新模型调用前检查，不中断在途 HTTP 请求。
- 补全客户端在工厂层显式 `max_retries=0`（不在 SDK 层重试）；审计/生成重试用 `MAX_TOTAL_RETRIES`，默认 **2**（最多 3 次生成），不是 3 次重试。
- 预热 `LLMFactory.prewarm()` 只构造客户端、不发探测请求（不产生 token）；测试时 `LLM_PREWARM_ENABLED=false`。
- 知识预算由 `knowledge_budget.reserve_usage(kind)` 在出网前预留，`kind ∈ {search, fetch, model}`；支持 task/day/month 三级限额与父子任务继承，实际变量名是 `KNOWLEDGE_{KIND}_{PERIOD}_LIMIT`（如 `KNOWLEDGE_MODEL_TASK_LIMIT`）、`KNOWLEDGE_INPUT_{PERIOD}_TOKENS`、`KNOWLEDGE_OUTPUT_{PERIOD}_TOKENS`、`KNOWLEDGE_{PERIOD}_COST_MICROS`（默认 day 100 / month 1000）。
- **覆盖范围有限**：`reserve_usage` 只被知识综合/学科规划与 `deepseek_search` 调用；普通问答、对话、课件、练习、结构化资源、路径、画像、报告、小智普通生成都**不**受该预算保护。本轮必须用独立计数代理/日志记录所有出站尝试。

## 3. 统一隔离与安全（每次执行都遵守）

- 独立 `DATABASE_URL`（绝对路径 SQLite，或专属 PostgreSQL，**禁止共享库**）；
- 独立 `KNOWLEDGE_RUNTIME_ROOT`、独立 Chroma 目录/collection（如启用）；
- 独立上传/导出/日志目录；独立 API 与 Worker 进程，使用同一 JWT、模型开关、任务模式；
- 新进程加载配置：`common/config.py` 的字段在模块导入时读取环境变量，`get_settings()` 还有进程缓存；改配置后必须重启进程，不能原地改 `os.environ` 后复用。
- `.env` 可能已有密钥；进程环境中的**非空值**会阻止 `.env` 覆盖（`os.environ.setdefault`）。**PowerShell 的 `$env:VAR=""` 会删除变量，不是设为空字符串**，删除后 `.env` 会重新生效。无费用运行请使用非空哨兵或本地假地址（如 `DEEPSEEK_API_KEY=blocked`、`DEEPSEEK_API_BASE=http://127.0.0.1:9/v1`），不要依赖空赋值。
- 真实调用需要两个闸门同时满足：`RUN_LIVE_LLM=1` **且** `DEEPSEEK_LIVE_PAID_ACK=1`。后者只能在用户授权预算后设置；仅 `RUN_LIVE_LLM=1` 不得出站。
- 首个真实请求前记录 `api.deepseek.com` 的实际 DNS 解析结果。若解析到 `198.18.x.x`（fake-IP/代理）或任何非官方地址，本次只能记为“经本机代理/网关访问”，不能写成官方直连验收。
- 环境变量（PowerShell 示例，密钥从交互输入或密钥保管库注入，不写进命令历史文件）：

```powershell
$env:DEEPSEEK_API_KEY="<交互注入，不要落盘>"
$env:DEEPSEEK_API_BASE="https://api.deepseek.com"   # 如用兼容网关，改为受控地址并记录
$env:DEEPSEEK_MODEL="deepseek-chat"
$env:QWEN_API_KEY="blocked"; $env:QWEN_API_BASE="http://127.0.0.1:9/v1"; $env:OPENAI_API_KEY="blocked"
$env:RUN_LIVE_LLM="1"; $env:DEEPSEEK_LIVE_PAID_ACK="1"   # 仅在用户授权预算后设置
$env:DATABASE_URL="sqlite+pysqlite:///<RunRoot>/live.sqlite"
$env:JWT_SECRET_KEY="<本轮临时值>"; $env:ENVIRONMENT="test"; $env:DEBUG="false"
$env:DEFAULT_ADMIN_USERNAME=""; $env:DEFAULT_ADMIN_PASSWORD=""; $env:DEFAULT_ADMIN_EMAIL=""
$env:LLM_PREWARM_ENABLED="false"; $env:NEO4J_ENABLED="false"
$env:ASSISTANT_TASK_EXECUTION_MODE="worker"   # 取消/异步链路用 worker 模式
```

- 每条用例记录：开始/结束时间、调用次数、输入/输出 token、耗时、HTTP 状态、任务 ID、数据库断言、日志位置；
- 每次出站尝试还要记录：目标主机、请求模型、响应模型、请求/响应 ID（如有）、HTTP 状态、usage（如有）、是否经代理/网关。仅有 `provider=deepseek` 日志不足以证明请求到达官方服务。
- 生成产物全部归属隔离测试用户，结束后清理（测试文件已有 `created_resource_ids` 清理夹具；练习、任务、附件需另行记录并清理）；
- 失败用例保留原始模型响应（脱敏）、trace、服务与 Worker 日志；第三方 DEBUG 日志默认不开启，避免泄露密钥或完整提示词。

## 4. 预算总表（**建议规模，不是费用授权**；费率未知时金额记“金额未知”，不得记 0）

> 下表只是执行方估算测试规模用的。未获得用户对 Chat/Search/Fetch、次数/Token/金额/时长的明确授权前，一行都不能执行。用户一次性授权总预算后，在该预算内连续执行并汇报；新增服务或扩大预算再确认。

| 层级 | 内容 | 建议 Chat 尝试上限 | 建议 Search/Fetch 上限 | 建议单用例输入/输出 token | 建议单用例时长 |
| --- | --- | --- | --- | --- | --- |
| Tier A | 连通、取消、真实故障语义（最关键） | 10 | 0 | 6k / 4k | 60s |
| Tier B | 核心业务闭环（资源/练习/路径/问答/对话/画像/报告/小智） | 18 | 0 | 8k / 5k | 90s |
| Tier C | V8.3 知识建设、图谱补全、Search/Fetch 来源链 | 12 | Search ≤ 4 / Fetch ≤ 6 | 10k / 6k | 120s |
| 可选 | 20 题大请求分批（典型 2 次生成，审计/重试另计） | 6 | 0 | 12k / 8k | 180s |
| **总计建议上限** | 全 Tier 一次跑完 | **≤ 46**（含可选） | **Search ≤ 4 / Fetch ≤ 6** | 总输入 ≤ 300k / 总输出 ≤ 180k | 总时长 ≤ 60 分钟 |

- 上表按源码的“尝试次数”而非“成功次数”估算；课件/练习的审计与重试会追加，取消时在途请求也可能计费。
- **实际出站尝试数达到授权上限立即停止**，按 PASS/FAIL/BLOCKED 如实记录，不得超支补跑。
- 金额：DeepSeek 单价以授权人提供的实时费率为准；未提供时一律写“金额未知”。不要把建议数字写成已授权金额。
- usage 缺失记“未知”，不能记 0；计数基线只表示“本轮从零开始”。

### 4.1 预算覆盖现状（必须先读）

| 调用类型 | 是否受 `knowledge_budget` 保护 | 本轮需要的控制 |
| --- | --- | --- |
| 知识综合 / 学科规划模型调用 | 是（`model`） | 任务/日/月限额 + 代理计数 |
| Search / Fetch | 是（`search`/`fetch`，每次尝试预留） | 单独计数 + 授权检查 |
| 问答 / 对话 / SSE | 否 | 本地计数代理，出站前拦截 |
| 课件 / 练习 / 结构化资源 | 否 | 本地计数代理，出站前拦截 |
| 路径 / 画像 / 报告 / 小智普通任务 | 否 | 本地计数代理，出站前拦截 |

本轮无费用准备提供了本地计数代理（`scripts/deepseek_ledger_proxy.py`），Chat 可通过 `DEEPSEEK_API_BASE` 指向它；Search/Fetch 使用 `DEEPSEEK_SEARCH_BASE` 覆盖根地址后才可被代理计数（默认仍为官方地址）。**不要把知识预算当作全站预算。**

- 超时用例必须核对真实生效值：配置 1 秒会被钳到 3 秒；DS-27 已改为本地桩验证，不产生 DeepSeek 费用。若另做真实超时用例，必须承认“本地超时/取消不代表远端未计费”，并在账户侧核对。

## 5. 用例清单

字段：入口 / 真实调用 / 预期 / 关键证据 / 备注。“已有 live 脚本”指 `tests/integration/test_live_llm_resources.py`。

### Tier A：连通、取消与故障语义（最关键）

| ID | 用例 | 触发入口 | 真实调用 | 预期（通过准则） | 证据 |
| --- | --- | --- | --- | --- | --- |
| DS-01 | 强制 DeepSeek 连通与路由核对 | 直接调用 `LLMFactory(settings).build_chat_model()` 做 1 次最小补全 | 1 | 实际 `base_url` 指向 DeepSeek；响应模型为配置值；HTTP 200；返回非空文本；记录请求/响应 ID 与 usage（如有）；仅有 `provider=deepseek` 日志不算通过 | 响应片段、base_url、实际 DNS、响应模型、调用计数 |
| DS-02 | 思维导图真实全链路 | 已有 live 脚本 `[mind_map]` | 典型 1；上限 2 | JSON 解析 + Pydantic 结构 nodes 非空；结构校验通过；审计 `rejected` 为失败，`unavailable` 单列且不等于审计通过；持久化并可回读 | 用例输出、DB 行、junit |
| DS-03 | 代码案例真实全链路 | 已有 live 脚本 `[code_case]` | 典型 1；上限 2 | run_steps 非空；不含 `executed` 字段（系统不执行代码）；持久化回读 | 同上 |
| DS-04 | 视频脚本真实全链路 | 已有 live 脚本 `[video_script]` | 典型 1；上限 2 | chapters 非空；不含 `video_path`（系统不产出媒体文件）；持久化回读 | 同上 |
| DS-23 | 运行中取消 → 停止本地后续调度与提交 | 提交长任务后立即 `POST /assistant/tasks/{id}/request-cancel`，独立 Worker 执行 | 启动 1，后续取决于取消点 | 取消 HTTP 200；接受 `CANCEL_REQUESTED` **或**已终态（竞态样本），**不强制捕获短暂中间态**；取消后不再开始新的阶段/模型调用；AgentExecution 仅记录取消点之前阶段；任务最终 CANCELLED/既有终态且不伪造结果。**不承诺远端在途请求停止或停止计费。** | 任务状态时间线、执行记录、模型调用计数、DB 状态 |
| DS-24 | 取消后迟到结果不提交 | DS-23 后观察/或模拟取消后补全返回 | 0（不新增） | 迟到结果不产生重复成果；最终状态以 CANCELLED 为准；同请求键不重复；写入围栏拒绝迟到提交 | DB 成果计数、幂等键、副作用键 |
| DS-25 | 死端点必须失败不伪造 | 已有 live 脚本 `test_live_dead_endpoint_raises_instead_of_fabricating`（指向 127.0.0.1:9） | 0（不产生 DeepSeek 计费） | 抛 ResourceGenerationError；<60s 快速失败 | 用例输出、耗时 |
| DS-26 | 非 JSON 回答被拒 | **本地 HTTP 桩** `tests/integration/test_deepseek_failure_semantics.py`（返回 200 散文）；禁止用提示词逼模型输出错误 | 0（本地桩，不产生 DeepSeek 计费） | 抛错且信息含 JSON，不猜测落库；桩收到 1 次请求 | 用例输出、本地桩请求计数 |
| DS-27 | 真实生效超时（非 1 秒） | **本地 HTTP 桩** 返回延迟；配置 `LLM_REQUEST_TIMEOUT_SECONDS=1` | 0（本地桩） | 实测生效超时约为 3 秒（`max(3, 1)`），而不是 1 秒；抛真实异常；桩收到 1 次请求。若另做真实端点超时，需单独授权并核对账户计费 | 用例输出、耗时、桩计数 |
| DS-28 | 日志不泄露密钥/完整提示词 | 已有 live 脚本 `test_live_logs_do_not_leak_credentials_or_prompts` | 复用 1 次生成（可与 DS-02 合并） | DEBUG 日志无 sk-/Bearer/Authorization/完整 prompt | caplog 全文检索结果 |

### Tier B：核心业务闭环

| ID | 用例 | 触发入口 | 真实调用 | 预期 | 证据 |
| --- | --- | --- | --- | --- | --- |
| DS-05 | 课件正文生成 + 审计 | 资源生成 courseware | 典型 1；上限 3 生成 + 3 审计 | 正文与知识点相关、结构完整；`audit_status=passed` 才算审计通过；`unavailable` 不是审计通过（审核未执行），必须单列原因；DOCX 可解析且对应正文 | 响应、DB、DOCX、审计状态与原因 |
| DS-06 | 练习生成（单批，5 题） | 练习生成服务 | 典型 1；上限 3 生成 + 3 审计 | 题/答/解析一致；服务端权威答案落库；重放不重复；**必须确认不是 `deterministic_fallback`**（模型失败时系统会用确定性题兜底并仍报 `audit_status=passed`） | DB 题目、答案校验、`audit_reason` |
| DS-07 | 大请求分批（20 题，可选） | 练习生成大批量 | 典型 2 次生成（10+10）；审计/重试另计，上限 12 | 恰好 2 批、总题数正确、无重复；预算消耗可解释；**需显式授权最多 12 次尝试才跑** | 任务子项、调用计数 |
| DS-08 | 学习路径草案 | 学习路径服务 | 1 | 草案 DRAFT 不自动生效；用户确认后才成为 active | DB 状态、前端读回 |
| DS-09 | QA 自由提问 | `/qa` 问答接口 | 1（回答+建议合并为一个 JSON bundle） | 真实回答、无来源时不编造引用 | 响应、引用字段 |
| DS-10 | QA 显式知识点上下文 | 选择课程知识点后提问 | 回答 1；显式请求课件/练习再按对应上限追加；图谱后台补全 0–1，不保证发生 | 回答基于命中的知识上下文；检索无结果时如实降级 | 检索命中、响应、实际计数 |
| DS-11 | 多轮对话 SSE 流式 | `/chat` SSE | 1（stream） | 正常结束事件完整；异常/断连后前端状态恢复；无持续加载/重复/丢消息 | 事件流、前端截图、控制台 |
| DS-12 | 小智复合任务 | 助手 resource/exercise/combined 各 1（按需选择） | 1–3 | 只生成用户请求的成果；类型、数量、归属正确；历史画像默认关闭不被额外读取 | 任务链、成果清单 |
| DS-13 | 学情画像分析 | user_service 画像分析 | 1 | 仅在显式开启画像时读取本人学情；无数据走冷启动 | 响应、DB 画像 |
| DS-14 | 成绩单分析报告 | evaluation_service 报告 | 1 | 基于真实上传成绩；无越权读取他人附件；建议与数据对应 | 报告、权限断言 |

### Tier C：V8.3 知识建设与来源管线

| ID | 用例 | 触发入口 | 真实调用 | 预期 | 证据 |
| --- | --- | --- | --- | --- | --- |
| DS-15 | AI 学科大纲生成 | `plan_subject` | 1 | 大纲结构（学科/别名/章节/目标/先修）可解析；PLANNED 不等于已建成 | 大纲 JSON、任务状态 |
| DS-16 | 知识点综合草稿 | `synthesize_point`（基于真实保存来源） | 1 | 草稿引用真实 fetch 到的来源 URL；无来源不综合 | 草稿、引用来源 ID |
| DS-17 | 单点建设/补全 | `build_point` 分阶段 | 1 search + 最多 2 fetch + 1 model = 4 次尝试 | 各阶段状态 COMPLETE/PARTIAL/MISSING/STALE/UNCERTAIN/RETRIEVAL_FAILURE 区分正确；Chroma 故障不被误判为知识缺失 | 阶段记录、状态、失败分类 |
| DS-18 | 图谱异步补全 | `/graph/visualization` 触发后台补全 | 0–1（异步，可能不发生） | 缓存命中快速返回；后台补全仅丰富缓存、不阻塞请求；缓存内容可检索；不能按“必然 1 次”计 | 响应时延、缓存、后台日志 |
| DS-20 | Search 受控搜索 | `search_sources(query, count≤5)` | 每次尝试 1 search；重试可能 +1 | 真实返回来源列表；请求数受控；预算按**尝试次数** search +1 | 原始返回、计数 |
| DS-21 | Fetch 受控抓取 | `fetch_source(url)` | 每次尝试 1 fetch；重试可能 +1；**本机 fake-IP DNS 下会被 SSRF 公网校验拒绝** | 仅允许公网 http(s)；内网/凭据 URL 被 SSRF 拦截；预算 fetch +1。当前环境 DS-21 标 BLOCKED，不能放宽校验换通过 | 抓取内容、拦截用例、DNS 证据 |
| DS-22 | 来源→草稿→发布链 | Search 保存来源 → Fetch → 综合草稿 → 送审 → 批准 → 许可校验 → 发布 → 索引 → 固定查询检索 | 1 search + 最多 2 fetch + 1 model | 三阶段分别留证据；非 APPROVED 不能发布；有 URL 不等于有发布许可；发布后固定查询命中预期来源 ID；检索失败不报告发布成功。Fetch 被 fake-IP 阻断时停在候选阶段并记 BLOCKED | 全链路证据包、检索验证 |
| DS-29 | 预算超限停止 | 将 `KNOWLEDGE_MODEL_TASK_LIMIT=0`（或 1）后发起建设 | 0–1 | 超限报 `KnowledgeBudgetExceeded`，不再发起后续调用；父子任务预算继承可见；缓存命中/预留/实耗分别计量；只对知识链路有效，不代表问答/资源也受保护 | 预算表、调用日志 |
| DS-30 | 人工内容质量复核 | 基于 DS-02~DS-09 已生成产物 | 0（无新增） | 人工按结构/相关性/知识错误/难度/题答一致性评分；**无人工评审不得宣称专家质量验收通过** | 评分表 |

### 明确不纳入 DeepSeek 清单（避免误收费）

- 权限/越权、幂等、事务、围栏、崩溃恢复、租约、取消状态机、SQLite 并发：无费用套件 + 独立 harness 完成。
- 死端点 DS-25 走假地址，不产生 DeepSeek 费用。
- 非 JSON、429/5xx、慢响应、断流（DS-26/27 及扩展故障语义）走本地 HTTP 桩，不产生 DeepSeek 费用。
- PostgreSQL 并发、Chroma HTTP 模式、Neo4j 降级：各自独立依赖环境，不消耗 DeepSeek。
- 压力/性能 P95/P99：不用真实模型刷量；以 Mock 或本地桩测量，样本不足不下高可信结论。

## 6. 执行顺序与停止条件

1. 先跑无费用回归全绿，再跑 Tier A；Tier A 任一失败先定位，**不进入 Tier B**。
2. 无费用阶段至少覆盖：Provider 选择/冲突、JSON/结构校验、超时/429/5xx/断流（本地桩）、取消/租约/执行代次/迟到写入、幂等与预算、独立 Worker 恢复。
3. 每个 Tier 结束核对调用计数、token、预算余额并汇报；一次性授权范围内可继续，不逐 Tier 重复索要确认。
4. 命中以下任一情况立即停止：达到授权上限；连续 2 次真实 5xx/限流；发现取消后仍产生新的出站调用（先取证）；数据写到隔离环境之外；实际目标主机/模型与预期不符。
5. DS-07/DS-22 等多调用用例需在授权范围内确认后才执行。
6. 超时结果不明确的生成任务不自动重放；如任务已结束才提交取消，改分类为“取消竞态样本”，不伪造运行中取消。

## 6.1 证据层级（写报告时必须标注）

| 层级 | 含义 | 可用于 |
| --- | --- | --- |
| L0 | 静态源码/配置核对 | 证明“代码会这样选路/计时”，不能证明真实服务可用 |
| L1 | 本地 HTTP 桩/单测 | 证明解析、错误码、超时、断流处理；**不是真实模型结论** |
| L2 | 隔离集成/Worker/DB | 证明编排、持久化、取消围栏；模型仍可能是桩 |
| L3 | 真实 DeepSeek 官方直连 | 可写“真实链路通过”；需目标主机/响应模型/ID/usage 证据 |
| L4 | 经兼容网关/本机代理访问 | 只能写“经网关访问通过”，不能写成官方直连验收 |

## 6.2 建议的最小真实执行顺序（获授权后）

1. DS-01（1 次）：先证明实际 `base_url`、DNS/代理、响应模型；不通过则停止。
2. DS-26/27/25 本地桩（0 费用）先全绿，再执行任何真实故障用例。
3. DS-02→03→04（各 1 次典型）：真实结构化资源；每次核对计数与审计状态。
4. DS-23/24：真实长任务 + 独立 Worker；取消前后用持久记录和模型调用计数证明“不再开始新阶段”，远端计费结论保持“无法确认”。
5. 其余 Tier B/C 按授权预算逐项执行；Search/Fetch 与 Chat 分别计数。

## 7. 每条用例记录模板（写入 test-matrix.csv / evidence）

用例ID｜模块｜API/入口｜真实调用类型｜计划调用数｜实际调用数｜输入token｜输出token｜耗时(s)｜HTTP状态｜任务ID｜预期｜实际｜状态(PASS/FAIL/BLOCKED/NOT_RUN)｜证据路径｜缺陷ID｜金额（未知/数值）｜执行人｜时间

## 8. 判定规则

- PASS：真实调用链完成，预期全部满足，证据齐全，且产物在隔离环境内；必须标注证据层级 L3 或 L4。
- FAIL：真实链路上任一硬断言失败（伪造结果、错误状态、越权、取消后仍开始新阶段、实际目标主机/模型不符）。
- **不得仅因“取消后在途请求仍可能执行/计费”判 FAIL**：当前实现是协作式取消，无法中止已发出的 HTTP 请求；应判“本地停止已验证，远端计费无法确认”。
- BLOCKED：密钥/预算/开通能力/隔离环境/DNS 不具备；写明具体缺口，不用其他证据替代。
- NOT_RUN：尚未执行；**不允许把构建成功、历史记录、Mock/本地桩成功、健康 200、密钥存在记为 PASS**。
- `audit_status=unavailable` 单独统计为“审核未执行”，不能计为审计通过。
- 人工质量（DS-30）与自动检查分开统计；一次普通错误不直接定 P0，严重级别按影响范围、资金、数据安全和可恢复性判定。

## 9. 与现有文档的对应

- 取消/计费语义：见 `docs/testing/external-platform-test-matrix.md` LLM-02；实现边界见 `docs/assistant-task-reliability.md` §“技术限制和未验证范围”。
- 无费用回归基线与隔离：见 `docs/testing/external-platform-test-context.md` §7、§8、§11。
- V8.3 知识状态、来源许可、发布与索引：见 `docs/knowledge-v8-progress.md`。
- 本轮源码核对（配置名、超时、次数、预算覆盖、取消、Search/Fetch）：见 `docs/testing/deepseek-live-source-audit.md`。
- 本轮无费用证据：见 `artifacts/deepseek-live-20261019-173354/`。
- 历史无费用审计：见 `artifacts/global-audit-20261019-1714/` 与 `docs/testing/local-audit-verification-20261019.md`。
