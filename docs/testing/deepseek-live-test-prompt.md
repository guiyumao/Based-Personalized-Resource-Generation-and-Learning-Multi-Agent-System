# DeepSeek 真实模型受控验收 · 执行 Prompt（v1.1，可直接复制）

> 无费用 V3 更新：普通 pytest 入口现在在导入项目配置前启用无费用隔离，强制忽略开发 `.env`、屏蔽真实凭证和非声明本地网络。`RUN_LIVE_LLM=1` 与 `DEEPSEEK_LIVE_PAID_ACK=1` 不能绕过该入口。下方真实付费步骤只作为后续受控执行设计；须另行完成用户授权、独立密钥注入、预算和专用付费运行器评审，本轮不得执行。安全本地验收入口为 `scripts/run_no_cost_tests.py`。

> 使用说明：把下面「==== 开始复制 ====」到「==== 结束复制 ====」之间的全部内容，连同 `docs/testing/deepseek-live-test-plan.md` 与 `docs/testing/deepseek-live-source-audit.md`，粘贴给执行方（或新的执行会话）。密钥通过交互注入，不要写进任何文件、截图或提交记录。**建议预算不等于费用授权**；未获明确授权不得发起真实调用。

==== 开始复制 ====

你是一名 AI 系统测试专家与全栈工程师。请对项目「基于大模型的个性化资源生成与学习多智能体系统」（根目录：`C:\Users\wdx\Desktop\基于大模型的个性化资源生成与学习多智能体系统`）执行 **DeepSeek 真实模型受控验收**。本轮只做 DeepSeek 相关用例；严格遵守授权、预算与隔离。无费用测试、本地桩测试、历史报告和 Mock 结果都不能冒充真实模型结果。

## 一、强制执行顺序

1. 先读 `docs/testing/deepseek-live-source-audit.md`（源码事实）、`docs/testing/deepseek-live-test-plan.md`（DS-01~DS-30、预算、判定规则），再读 `docs/testing/external-platform-test-context.md` §7（模型配置）、§8（隔离要求）。
2. 先核对源码事实，再执行：`git rev-parse HEAD`、`python -m alembic heads`；对涉及文件（`llm_factory.py`、`deepseek_search.py`、`knowledge_budget.py`、`resource_generation.py`、`exercise_generation.py`、`knowledge_construction.py`、`tests/integration/test_live_llm_resources.py`）记录 SHA256 到 `source-manifest.json`。
3. 建立独立证据目录 `artifacts/deepseek-live-<时间戳>/`，先写 `environment.json`、`source-manifest.json`、空的 `request-ledger.jsonl`，并注明“**本轮请求计数从零开始**”，不得暗示账户历史消耗为零。
4. 先跑无费用回归（必须全绿，不消耗 DeepSeek）：
   - `python -m pytest tests/unit/test_llm_factory.py tests/unit/test_ai_timeout_handling.py tests/unit/test_knowledge_budget.py tests/integration/test_deepseek_failure_semantics.py -q`
   - 再跑任务链：`python -m pytest tests/unit/test_assistant_tasks.py tests/integration/test_assistant_worker_process.py -q`。**这套件用默认 `ASSISTANT_TASK_EXECUTION_MODE=background`**；全局设成 `worker` 会让同步用例停在 PENDING。worker 专项测试在用例内部自行设置模式。
   - 不绿则停止，报告 FAIL，不进入真实模型阶段；无关失败单列，不无依据阻断全部工作。
5. 无费用回归通过后，才从 Tier A 开始真实测试。**在用户一次性授权的范围与总预算内可连续执行并汇报进度，不逐 Tier 重复索要确认；新增服务、扩大预算或高风险重放时再确认。**

## 二、授权与预算闸门（不满足就标记 BLOCKED，不要自行其是）

- 开工前确认：①是否明确授权使用该测试密钥（**密钥存在本身不是授权**）；②是否授权 Chat Completions；③是否授权 Search/Fetch（未开通则 DS-20/21/22 标 BLOCKED）；④最大出站尝试次数、输入/输出 Token、总时长、金额上限或 Token 预算；⑤是否允许兼容网关；⑥允许执行的场景。
- 计划里的“建议上限”只是测试规模估算，**不是已获授权**。未获授权时完成无费用准备，一次性列出缺口，不发起收费请求。
- 任一授权上限达到立即停止；按 PASS/FAIL/BLOCKED 如实记录，不超支补跑。
- 金额：用户提供实时费率才写数值，否则一律“金额未知”，禁止写 0；usage 缺失记“未知”，不能记 0。
- 知识预算只覆盖知识综合/规划与 Search/Fetch，**不覆盖**普通问答、对话、课件、练习、结构化资源、路径、画像、报告。本轮用独立计数代理/日志统计所有出站尝试，不能把知识预算当全站预算。

## 三、强制命中 DeepSeek（关键）

模型工厂顺序：Qwen 专有 key → DeepSeek 专有 key → DeepSeek base + OpenAI key → Qwen base + OpenAI key → OpenAI。启动真实调用前必须：

- 清空 `QWEN_API_KEY`、`QWEN_API_BASE`、`OPENAI_API_KEY`；只保留 `DEEPSEEK_API_KEY`、`DEEPSEEK_API_BASE`、`DEEPSEEK_MODEL`。**注意：PowerShell 的 `$env:VAR=""` 会删除变量**，删除后 `.env` 会重新生效；无费用运行请用非空哨兵或本地假地址，不要依赖空赋值。
- 真实调用需要 `RUN_LIVE_LLM=1` **且** `DEEPSEEK_LIVE_PAID_ACK=1`；后者只在用户授权预算后设置。仅 `RUN_LIVE_LLM=1` 不得出站。
- 使用**新进程**加载配置；`Settings` 在导入时读环境变量且有缓存，改环境后不能复用旧进程。
- 首个真实请求同时记录：实际目标主机、DNS 解析结果、请求模型、响应模型、请求/响应 ID（如有）、HTTP 状态、usage（如有）。**仅有 `provider=deepseek` 日志不足以证明到达官方服务。**
- 若 `api.deepseek.com` 解析到 `198.18.x.x`（fake-IP/代理）或其他非官方地址，只能标“经本机代理/网关访问”，不能写成官方直连验收。
- 设置隔离 `DATABASE_URL`（绝对路径独立 SQLite，禁止共享 `learning_system.db`）、临时 `JWT_SECRET_KEY`、`ENVIRONMENT=test`、`LLM_PREWARM_ENABLED=false`、`NEO4J_ENABLED=false`，清空 DEFAULT_ADMIN 引导变量。
- 取消/异步链路用 `ASSISTANT_TASK_EXECUTION_MODE=worker`；API 与 Worker 使用同一测试数据库与同一 JWT。

## 四、Tier 执行要点

- **Tier A（DS-01~04、DS-23~28）**
  - DS-25/26/27 以及 429/5xx/断流：**本地 HTTP 桩** `tests/integration/test_deepseek_failure_semantics.py`，不产生 DeepSeek 费用。**禁止**用“让模型必须输出非 JSON”或“设置 1 秒就一定超时”来构造失败用例；配置 1 秒会被钳到 3 秒，必须核对真实生效值。
  - DS-02/03/04/28 使用现成脚本：`$env:RUN_LIVE_LLM="1"; python -m pytest -m live_llm tests/integration/test_live_llm_resources.py -q --junitxml=...`（按用例逐个指定节点，避免一次跑超预算）。先核对脚本确实命中 DeepSeek，而不是 Qwen/OpenAI。
  - DS-23/24：真实提交长任务 → 独立 Worker → 运行中调用 `POST /assistant/tasks/{id}/request-cancel`。接受 `CANCEL_REQUESTED` **或**已终态（竞态样本），**不强制捕获短暂中间态**；用持久状态时间线和模型调用计数证明“取消后不再开始新阶段、迟到写入被拒”。**不得承诺或要求“远端在途请求停止执行/计费”**；没有账单证据时结论只能是“本地停止已验证，远端计费无法确认”。
- **Tier B（DS-05~14）**：逐业务闭环走“提交→真实生成→校验→保存→读回→导出/评分”，记录真实生成与审计调用次数。课件/练习的审计与重试会追加调用；练习若返回 `deterministic_fallback`，说明模型失败后用了确定性题兜底，**不能算真实生成通过**。`audit_status=unavailable` 是“审核未执行”，不是审计通过。画像与成绩分析不得越权读取他人数据。
- **Tier C（DS-15~22、DS-29）**：Search 与 Fetch 分别计数。Search 单次 `count≤5`；Fetch 必须验证公网 SSRF 拦截。`_ROOT` 默认 `https://api.deepseek.com`，可用 `DEEPSEEK_SEARCH_BASE` 覆盖；`DEEPSEEK_API_BASE` 不影响 Search/Fetch。如经网关，需明确标记。**本机 fake-IP DNS 会把公网 URL 判为非公网，DS-21/22 的 Fetch 可能直接 BLOCKED；不得放宽 SSRF 规则来换通过。** DS-22 走完整来源链并用固定查询+预期来源 ID 验证检索，检索失败不得报告发布成功；DS-29 用 `KNOWLEDGE_MODEL_TASK_LIMIT=0/1` 验证超限即停、父子任务预算继承。
- DS-07（20 题）典型是 2 次生成（10+10），审计/重试另计，最多 12 次尝试；DS-22 需单独确认后才执行。

## 五、硬性禁止

- 禁止对共享 SQLite 做 upgrade/stamp/故障注入；禁止停既有服务或共享容器；禁止真实模型调用共享数据库。
- 禁止把 Mock 成功、本地桩成功、构建成功、健康检查 200、历史报告通过、pytest skipped、密钥存在记为 PASS。
- 禁止为了跑绿而改业务规则、删断言、放宽内容校验/权限或改共享配置；禁止超预算补跑。
- 禁止把 `audit_status=unavailable` 改写成审计通过；禁止隐瞒首次失败只展示重跑成功。
- 禁止在报告、日志、截图中出现完整密钥、Bearer、个人敏感内容；密钥一律 `sk-***`。
- 禁止默认开启可能泄露密钥或完整提示词的第三方 DEBUG 日志。
- 每个真实产物归属隔离测试用户，结束后按用例清理；只清理本轮自己创建且路径已核实的资源。

## 六、同步与取证

- 每条用例记录：用例ID、入口、真实调用类型、计划/实际调用数、输入/输出 token、耗时、HTTP 状态、任务ID、目标主机、请求/响应模型、预期、实际、状态（PASS/FAIL/BLOCKED/NOT_RUN）、证据层级（L0~L4）、证据路径、金额。
- 每次出站尝试写 `request-ledger.jsonl`：场景ID、任务ID、阶段、尝试序号、Provider、模型、目标主机、开始/结束时间、HTTP 状态、usage、结果状态、重试原因、证据位置。
- `command-log.jsonl` 必须含真实命令、工作目录、时间、退出码、输出位置；计划执行不得写成已执行。
- 状态口径：已执行=PASS+FAIL；通过率=PASS/(PASS+FAIL)；skipped 不计入。

## 七、Tier 汇报与最终交付

- 每个 Tier 结束输出：本 Tier 结果表、真实调用/Token/花费对账、遇到的问题、是否达到下一 Tier 条件。一次性授权范围内继续执行；未授权则停下等确认。
- 全部结束（或提前停止）后在证据目录交付：`README.md`、`environment.json`、`source-manifest.json`、`request-ledger.jsonl`、`deepseek-live-matrix.csv`、`command-log.jsonl`、`defect-register.md`、`DEEPSEEK_LIVE_SUMMARY.md`、`evidence/`。
- 最终回答必须包含：①真实验证通过的业务闭环及证据层级；②FAIL/BLOCKED/NOT_RUN 清单与原因；③取消后的三个独立结论：本地后续调度是否停止、迟到写入是否被拒、远端是否停止/计费（没有账单证据就写“无法确认”）；④实际出站尝试数、Token、花费（未知部分明确标注）；⑤DeepSeek 链路能否用于当前业务，以及进入下一阶段前必须先解决的缺口。

现在开始：先做源码与环境核对、建立证据目录、跑无费用回归；完成后再一次性列出授权与预算缺口。未获授权前不发起任何收费请求。

==== 结束复制 ====
