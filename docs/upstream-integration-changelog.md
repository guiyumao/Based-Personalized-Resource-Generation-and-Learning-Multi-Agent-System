# 上游融合变更记录

> 记录 LearnMate + ZhiShu 融合的逐阶段代码、迁移、页面与测试变化。
> 逐项取舍见 [`upstream-integration-matrix.md`](upstream-integration-matrix.md)，架构见
> [`upstream-integration-architecture.md`](upstream-integration-architecture.md)。

## 前置说明：工作区保护

- 审计开始时工作区已有大量未提交改动，全部视为用户资产：**102 个已修改、88 个已删除、68 个未跟踪**。
- 全程未执行 `git reset --hard`、`git clean`、`git checkout --` 或任何可能丢弃工作区改动的命令。
- 未创建任何提交，未推送。
- 两个上游仓库克隆到 `%TEMP%\upstream-audit\`（工作区之外），未执行其脚本，未读取其 `.env` 值，
  未复制其代码、密钥、数据库或生成数据到本仓库。

## 2026-10-15：阶段 0 审计 + 阶段 1 统一状态 + 阶段 2 校验与新资源 + 阶段 3 路径门禁

### 上游核实（阶段 0）

| 项目 | 分支 | commit | 日期 | 提交数 | 许可证 |
|---|---|---|---|---|---|
| LearnMate | `master` | `c601e5e0849dd442e8593cc868ae21eb8e5bb39b` | 2026-06-24 | 1 | **无** |
| ZhiShu | `main` | `936a34a905725a58d586501a7b162883f3d59db0` | 2026-07-20 | 244 | **无** |

修正前一版 ZhiShu 记录里的一处事实：commit 日期是 2026-07-20（前一版记录的是审计运行日期 2026-10-15），
SHA 与分支不变。许可证结论经三种独立方式复核后**维持**：git 索引、工作区遍历、仓库页面均无
LICENSE；README 的 `## 许可证` 正文是参赛声明而非授权。**因此本次不复制任何上游代码或提示词。**

同时记录到两项上游安全事实（仅作反面依据，未复制其内容）：ZhiShu 的根目录 `.env` 与
`release/后端/.env` 被提交进公开仓库并含 `JWT_SECRET` 与多个厂商 API Key；LearnMate 在
`JWT_SECRET` 为空时回退到硬编码签名密钥，且 `/api/knowledge/*` 等写接口无鉴权。

### 阶段 1：统一任务状态与确定性校验

**修复的真实缺陷**

- `CoordinatorWorkflow._execute_agents` 在 `execute=True` 分支用只含 5 个键的 `task_state`
  **整体覆盖** `run()` 的完整状态，导致 `selected_agents`、`intent`、`task_plan`、
  `learner_profile` 等在同步执行时丢失。现改为合并。

**新增**

- `_build_task_state` 补齐全部要求字段：`user_id`、`task_id`、`session_id`、`intent`、
  `intent_params`、`learner_profile`、`learning_evidence`、`selected_agents`、`task_plan`、
  `agent_handoff`、`intermediate_results`、`citations`、`validation_results`、`status`、
  `progress`、`current_step`、`error`。
- `_summarize_learner_profile`：任务状态中的画像只保留下游消费的事实白名单，不含原始作答或对话。
- `_collect_citations` / `_collect_validation_results`：把资源校验的引用与结论汇总进任务状态；
  无法回指的引用以 `resolved=false` 保留而非丢弃。
- `services/agent_service/app/services/content_validation.py`（新文件，约 700 行）：确定性结构与
  来源校验，**不调用模型**。
- `RESOURCE_TYPES` 常量与 `ResourceType` 字面量（`common/schemas/agent.py`）。

### 阶段 2：多类型资源生成

**新增资源类型**（复用 `Resource.type`，**无需数据库迁移**）

- `mind_map`：结构化 `nodes` + `edges`，按 `parent_id` 渲染 Markdown 大纲；`mermaid_source` 可选。
- `code_case`：语言、目标、前置知识、**静态**示例代码、预期输出、人工运行步骤、常见错误、拓展练习。
- `video_script`：章节化拍摄脚本（旁白/画面建议/屏幕文字/时长），总时长取各章之和。

**新增文件**

- `prompts/mind_map_gen.md`、`prompts/code_case_gen.md`、`prompts/video_script_gen.md`（本仓库新写）。
- `resource_generation.py` 新增 `generate_mind_map` / `generate_code_case` / `generate_video_script`、
  `_invoke_structured`、`_parse_json_object`、`_prepare_structured_request`、
  `_structured_context_variables`、`_finalize_structured_resource` 与三个 Markdown 渲染器。
- `coordinator._generate_resource`：按类型分发；`exercise` 指向习题 Agent，未知类型**拒绝而非降级**。

**校验接入点**

- `generate_courseware_with_plan` 与 `_finalize_structured_resource` 均在返回前写入
  `content_validation`。校验对象是**模型原始 JSON**（叠加本系统已重算字段），因为 `model_dump()`
  会静默丢掉模型幻觉出的 `executed`/`video_path` 等额外字段。

### 阶段 3：学习路径后端门禁

- `LearningPathService.adjust_path`：完成前校验前置任务，未满足抛
  `LearningPathPrerequisiteError`（`error_code=LEARNING_PATH_PREREQUISITE_UNMET`）。
- **跳过不算满足前置**——否则按顺序跳过全部任务即可绕过门禁。
- 自引用视为坏数据（不永久锁死）；未知依赖引用被忽略并在完整性报告中报出，避免死锁。
- `find_dependency_problems`：三色 DFS 环检测 + 未知引用统计；`generate_path` 写入
  `dependency_problems` 并告警，不持久化会卡死学习者的路径。
- 阈值配置化：`LEARNING_PATH_PASS_THRESHOLD`（默认 60）、`LEARNING_PATH_ENFORCE_PREREQUISITES`、
  `LEARNING_PATH_ALLOW_SKIP`；`LearningTaskItem.pass_threshold` 支持逐任务覆盖。
- 提示词要求 LLM 产出 `depends_on`；`_normalize_payload` 为历史路径回填 `[]`（位置语义继续生效）。
- `POST /paths/adjust` 门禁未满足时返回 **409**，`detail` 含 `error_code`、`message`、`blocked_task_ids`。

### 阶段 4：前端

- `web-app/src/api/types.ts`：新增 `ResourceType` 联合类型（7 类）；`ResourcePayload.resource_type`
  改用该类型；`ManagedResourceItem.type` 改为 `ResourceType | string`（历史未知类型仍可加载）；
  `LearningTaskItem` 新增可选 `status`、`depends_on`、`pass_threshold`。
- `web-app/src/views/student/ResourceView.vue`：`typeLabel` 补齐 `mind_map`/`code_case`/`video_script`
  标签，未知类型回退为原值而不是渲染空白。

### 接口与迁移影响

> **2026-10-16 补充**：本节描述的是阶段 1–4 的改动（当时确实没有迁移）。
> 之后为「结构化载荷可读回」与「修正迁移漂移」新增了两个迁移，见
> `20261016_0008` / `20261016_0009`。

- **Alembic：无。** `Resource.type` 是 `String(30)`；本次没有新增/修改表或列。
- 现有接口路径与请求字段全部兼容；`ResourceGenerationResponse` 只新增可选字段
  （`mind_map`/`code_case`/`video_script`/`content_validation`）。
- `ResourceItem.type` 由封闭 `Literal` 改为开放 `str`——`Literal` 会让任何历史/未知类型在反序列化时
  整表读取失败，读取历史不应因生成器演进就报错。
- `CoordinationResponse` 字段未变；`task_state` 内容更完整且向后兼容。
- `POST /paths/adjust` 新增 409 分支（此前任何任务都可直接完成）。

### 验证结果（真实输出）

| 命令 | 结果 |
|---|---|
| `python -m pytest -q`（基线，改动前） | `288 passed, 232 warnings in 113.08s` |
| `python -m pytest -q`（全部改动后） | `364 passed, 232 warnings in 112.08s` |
| `python -m pytest tests/unit/test_content_validation.py -q` | `39 passed` |
| `python -m pytest tests/unit/test_structured_resource_generation.py -q` | `13 passed` |
| `python -m pytest tests/unit/test_learning_path_prerequisites.py -q` | `15 passed` |
| `python -m pytest tests/unit/test_resource_type_integration.py -q` | `9 passed` |
| `python -m pytest tests/unit -q -k "learning or path"` | `42 passed, 306 deselected` |
| `ruff check common services tests/unit/...`（本次改动文件） | `All checks passed!` |
| `pnpm exec tsc -p tsconfig.app.json --noEmit`（`web-app/`） | 退出码 0（无类型错误） |
| `pnpm exec vite build`（`web-app/`） | `✓ built in 7.40s`，退出码 0 |

新增测试文件：`test_content_validation.py`（39）、`test_structured_resource_generation.py`（13）、
`test_learning_path_prerequisites.py`（15）、`test_resource_type_integration.py`（9），共 76 个新测试。

### 未执行 / 未验证（2026-10-15 当时状态，已被 2026-10-16 章节取代）

> 以下列表如实记录 **2026-10-15 当天**的状态。其中前四项已在
> 「2026-10-16：真实闭环整改（外部服务 / 真实 LLM / 浏览器 E2E）」章节中执行，
> 结论见该章节的验证矩阵；本节保留原文以便追溯。

- **未运行真实 LLM**：新资源生成器只经 stub 验证契约，未用真实模型跑通端到端生成。
- **未运行 PostgreSQL / Neo4j / Chroma 外部服务**，未做跨库迁移演练。
- **未运行浏览器 E2E**：前端只做 `tsc --noEmit` 类型检查与 `vite build` 之外的静态验证，未在浏览器
  中点击验证新资源类型的渲染。
- **未运行上游任何测试**：上游测试本身不可信——LearnMate 67 个测试函数不触及任何 Agent 或 RAG；
  ZhiShu 的 `test_api.py` 断言的是不存在的路由。
- 未复制上游，因此不存在"上游原实现 vs 本次实现"的行为等价性比对；差异均为设计取舍。

### 已知限制

- 确定性校验的判定是启发式规则（占位符正则、截断启发、章节词表），不是语义正确性证明；
  "结构通过"不等于"学术正确"。
- 来源检查只能验证"引用是否指向本次真实检索到的 chunk"，**不能**验证该 chunk 本身是否正确，
  也不能验证未被引用的陈述。
- `confidence` 类字段仍不在本模块中产生；本层只输出可通过/不通过的确定性结论。
- 上游 README 声称的能力中，有多项经核实并不存在（详见差距矩阵 §2.3）；本记录不含任何
  基于这些声称的效果指标。

---

## 2026-10-16：真实闭环整改（外部服务 / 真实 LLM / 浏览器 E2E）

> 目标：把上一节「未执行 / 未验证」的四项，变成**有真实证据**或**明确 blocked** 的结论。
> 本段所有数字都来自实际命令输出，原始证据保存在 `artifacts/upstream-integration/`。
> 未执行 `git reset --hard` / `git clean` / `git checkout --`，未删除任何无关文件，未创建提交。

### 0. 状态词汇（本文件统一使用）

| 标记 | 含义 |
|---|---|
| `implemented` | 代码已经实现 |
| `unit-verified` | 单元测试已验证（不接触外部服务 / 模型） |
| `integration-verified` | 真实外部服务或真实模型已验证 |
| `e2e-verified` | 真实浏览器链路已验证 |
| `blocked` | 环境或凭据限制导致无法验证（**代码与测试保留**） |
| `not-run` | 尚未执行 |

两条必须分开记录的结论：

- **「页面渲染成功」不等于「真实 LLM 生成成功」。** E2E 结果 JSON 中 `generation`（真实模型调用及其
  耗时、审核状态、校验结论）与 `ui`（浏览器断言）是两个独立段落。
- **「测试通过」不等于「端到端验证完成」。** 只有 `integration-verified` / `e2e-verified` 才代表
  真实链路；`unit-verified` 只代表单元逻辑。

### 1. 本次修复的真实缺陷（都只在真实链路下暴露）

| 编号 | 缺陷 | 为什么 stub/静态验证没发现 | 修复 |
|---|---|---|---|
| D1 | 三类结构化资源会被**课件审核规则整表拒绝** | 单测把 `AuditService` 整体替换为 `audit_courseware -> passed`，从不走真实审核 | 新增 `AuditService.audit_structured_resource`：结构化类型按自己的契约审核（非空、无失败文本、主题相关），课件章节表只用于散文类资源 |
| D2 | 三个结构化提示词**根本无法渲染** | 单测直接 stub 掉 `_invoke_structured` | 新增 `_render_prompt_template`：只替换已声明的 `{name}`，JSON 示例里的 `{` `}` 原样保留（原先 `str.format` 抛 `KeyError: '\n  "title"'`） |
| D3 | `alembic upgrade head` 后的 schema **与 ORM 不一致** | `scripts/db_migration_drill.py` 只统计表的数量，不校验列 | 新增迁移 `20261016_0009`，用 inspector 幂等补齐 10 个缺失列（见 §1.3） |
| D4 | 生成响应**不返回资源 id** | 调用方只看 HTTP 200 | `ResourceGenerationResponse` 新增 `id`（生成器本来就把它放在响应 dict 里，只是被响应模型裁掉） |
| D5 | 前端**从未渲染结构化内容与校验状态** | 只做了 `tsc --noEmit`（类型正确 ≠ 渲染正确） | `ResourceView.vue` 新增结构化面板：类型名 / 结构化正文 / 校验状态 / 空态 / 失败态 / 未知类型兜底 |
| D6（测试） | `test_graph_performance` 的缓存断言会**误报** | 需要整套用例的时序才会触发 | 断言从「全局缓存为 0」改为「本次知识点未被缓存」 |

#### 1.1 D1：结构化资源被课件审核拒绝

`_finalize_structured_resource` 原先调用 `AuditService.audit_courseware`。该规则要求内容里出现
`学习目标 / 知识讲解 / 示例 / 小结 / 自测` 中至少 3 个章节——思维导图、代码实操、讲解脚本**天然没有**
这些章节，于是每次真实生成都会被判 `rejected` 并抛 `ResourceGenerationError`。

证据：真实 API 调用在修复前返回
`ResourceGenerationError: ... failed audit: courseware required sections are incomplete`；
修复后同一调用返回 `audit_status=passed / rule_audit_passed`（见 §3 的 E2E `generation` 段与
`pytest-live-llm.log`）。

回归保护：`tests/unit/test_structured_resource_audit.py` 同时锁定「课件规则确实会拒绝导图」这一事实
（说明缺陷真实存在）与「结构化审核接受三种真实渲染结果」。

#### 1.2 D2：结构化提示词无法渲染

`prompts/mind_map_gen.md` / `code_case_gen.md` / `video_script_gen.md` 里各含一段 JSON 结构示例，
例如 `{"title": "导图标题", "nodes": [{"id": ...}]}`。原实现用 `template.format(**variables)` 渲染，
把 JSON 的大括号当成了格式化字段，在**调用模型之前**就抛
`KeyError: '\n  "title"'`。

修复后 `_render_prompt_template` 只替换正则 `\{([A-Za-z_][A-Za-z0-9_]*)\}` 匹配到的、且确实在
`variables` 中声明的名字；未声明的名字仍然报错（保留原有防错语义）。

#### 1.3 D3：迁移后的数据库缺少 ORM 需要的列

在一台**全新的 PostgreSQL** 上执行 `alembic upgrade head` 后，`resources` 表缺少
`title`/`source_url`/`local_path`/`tags`/`crawl_status`/`language`/`summary`，
`user_profiles` 缺少 `profile_analysis`，`answer_records` 缺少 `evaluation_json`/`created_at`。
这些列只存在于 `common/models/learning.py`，过去靠 SQLite 上的 `create_all` 加
`_ensure_legacy_columns()` 补丁维持，真实数据库上第一次写入就会：
`psycopg.errors.UndefinedColumn: column "title" of relation "resources" does not exist`。

新增迁移 `alembic/versions/20261016_0009_reconcile_orm_drift.py`，逐列用 inspector 判断后再
`add_column`（对已经由 `create_all` 建好的库是 no-op，可重复执行），全部可空，无需回填。

#### 1.4 D5：前端结构化展示

`web-app/src/views/student/ResourceView.vue` 的资源详情弹窗新增
`.structured-panel`（`data-testid="structured-resource-panel"`）：

- `mind_map`：按 `parent_id` 还原层级列表（对悬空父节点、环、缺 id 都有兜底，不会死循环或丢内容）；
- `code_case`：语言 / 目标 / 前置知识 / **标注为「静态展示，本系统不执行」的代码块** / 预期输出 / 人工运行步骤 / 常见错误；
- `video_script`：章节、旁白、画面建议、屏幕文字、单章时长与总时长，并显式声明「仅脚本，不产出视频文件」；
- 校验状态：`verdict` + 结构/来源通过情况 + 来源覆盖率 + 失败检查项明细；
  其中 `unsupported` 会区分「引用指向不存在的来源」与「内容未声明可回指的来源」两种真实成因；
- 空数据：`data-testid="structured-empty"`；详情接口失败：`data-testid="structured-detail-error"`（含 HTTP 状态码）；
- 未知类型：`data-testid="unknown-resource-type"`，显示原始类型名而不是空白。

### 2. 新增 / 修改文件

**后端（8 改 + 2 迁移）**

| 文件 | 变更 |
|---|---|
| `common/models/learning.py` | `Resource.structured_json`（可空 Text） |
| `common/db/bootstrap.py` | 本地 SQLite 的 `structured_json` 兼容补列 |
| `common/schemas/agent.py` | `ResourceGenerationResponse.id` |
| `services/agent_service/app/services/audit_service.py` | `audit_structured_resource` + `STRUCTURED_RESOURCE_TYPES` |
| `services/agent_service/app/services/resource_generation.py` | `_render_prompt_template`；结构化类型改用结构化审核；持久化结构化载荷 |
| `services/resource_service/app/schemas/resource.py` | `ResourceItem.content / .structured / .content_validation` |
| `services/resource_service/app/services/resource_manager.py` | 详情接口回填载荷；损坏载荷容错降级（不抛异常） |
| `services/resource_service/app/api/routes/resources.py` | 授权矩阵注释与实现对齐 |
| `alembic/versions/20261016_0008_resource_structured_payload.py` | 新增列 `structured_json` |
| `alembic/versions/20261016_0009_reconcile_orm_drift.py` | 幂等补齐 ORM 需要的 10 列 |

**前端（2 改）**：`web-app/src/api/types.ts`（结构化载荷/校验报告类型、`data-resource-id` 相关字段）、
`web-app/src/views/student/ResourceView.vue`。

**验证资产（新增）**

| 文件 | 作用 |
|---|---|
| `scripts/verify_external_services.py` | PostgreSQL / Neo4j / Chroma 的真实验证器，产出 JSON + 原始日志 |
| `tests/integration/test_live_llm_resources.py` | `RUN_LIVE_LLM=1` 的真实模型全链路测试 |
| `tests/integration/test_external_services.py` | `RUN_EXTERNAL_SERVICES=1` 的外部服务集成测试 |
| `tests/e2e/run-structured-resources.mjs` | 真实浏览器 E2E（Playwright，复用 `tests/e2e` 既有依赖） |
| `tests/unit/test_structured_resource_audit.py` | D1 回归保护（9 项） |
| `tests/unit/test_structured_resource_persistence.py` | 载荷持久化/回读/容错（7 项） |
| `tests/unit/test_structured_resource_generation.py` | 新增提示词渲染契约（+5 项） |
| `tests/unit/test_graph_performance.py` | D6 断言改为按知识点键（测试隔离修复） |
| `pyproject.toml` | 注册 `live_llm` / `external_service` 标记 |
| `tests/e2e/README.md` | 新增第 7 节：结构化资源 E2E 运行方式与产物 |
| `docs/upstream-integration-changelog.md` | 本节：状态分级、缺陷清单、验证矩阵、阻塞与风险 |

**默认不依赖外部条件**：`python -m pytest -q` 不接触 Docker、数据库服务或模型；
两个新集成模块在未设置开关时于收集阶段 skip 并打印 `LIVE_LLM_NOT_CONFIGURED` /
`EXTERNAL_SERVICES_NOT_ENABLED`。

### 3. 验证矩阵

命令均在仓库根目录执行。证据路径相对仓库根。

| 验证项 | 命令 | 结果 | 是否真实 | 证据位置 | 阻塞原因 |
|---|---|---|---|---|---|
| 基线单元测试（改动前） | `python -m pytest -q` | `364 passed, 232 warnings in 143.31s` | 否 | 本次会话输出 | — |
| 单元测试（全部改动后） | `python -m pytest -q` | `385 passed, 2 skipped, 240 warnings in 166.38s` | 否 | `artifacts/upstream-integration/unit/pytest-full.log` | 2 skipped = 两个 opt-in 模块 |
| 结构化审核回归 | `python -m pytest tests/unit/test_structured_resource_audit.py -q` | `9 passed` | 否 | 同上 | — |
| 载荷持久化 | `python -m pytest tests/unit/test_structured_resource_persistence.py -q` | `7 passed` | 否 | 同上 | — |
| 提示词渲染契约 | `python -m pytest tests/unit/test_structured_resource_generation.py -q` | `18 passed` | 否 | 同上 | — |
| PostgreSQL | `python scripts/verify_external_services.py --only postgres` | **PASS**，head = `20261016_0009 (head)` | 是 | `artifacts/upstream-integration/external-services/postgres.json` / `.log` | — |
| Neo4j | `python scripts/verify_external_services.py --only neo4j` | **PASS**（4/4 项） | 是 | `.../neo4j.json` / `.log` | — |
| Chroma（persistent 模式） | `python scripts/verify_external_services.py --only chroma` | 模式一致 ✅、collection 读写查 ✅、来源 chunk ✅、无证据 → `insufficient_evidence` ✅、服务端 v1 REST ✅ | 是 | `.../chroma.json` / `.log` | — |
| Chroma（`CHROMA_MODE=http`） | 同上，HTTP 探测段 | **FAIL**：安装的 `chromadb 1.5.9` 走 `/api/v2`，服务端 `0.5.5` 只有 `/api/v1` | 是 | `.../chroma.json` → `checks.http_mode_client_server_compatible=false` | 本机解释器未遵守 `pyproject.toml` 的 `chromadb>=0.5.5,<1.0` |
| Chroma（按声明约束复验） | 隔离 venv 安装 `chromadb>=0.5.5,<1.0` | **blocked**：`chroma-hnswlib` 无 cp312/win 预编译轮子，需 MSVC | 否 | `artifacts/upstream-integration/external-services/chroma-pinned-venv-BLOCKED.txt` | 缺少 Microsoft C++ Build Tools |
| 外部服务集成测试（opt-in） | `RUN_EXTERNAL_SERVICES=1 python -m pytest tests/integration/test_external_services.py -m external_service -q -s` | `7 passed in 192.47s` | 是 | `artifacts/upstream-integration/integration/pytest-external-services.log` | — |
| 真实 LLM（三次生成全链路） | `RUN_LIVE_LLM=1 python -m pytest tests/integration/test_live_llm_resources.py -m live_llm -q -s` | `8 passed in 64.30s` | 是 | `artifacts/upstream-integration/live-llm/pytest-live-llm.log` | — |
| 浏览器 E2E | `node tests/e2e/run-structured-resources.mjs` | UI `11 passed`；`real_llm=true`，3 个资源 HTTP 200 | 是 | `artifacts/upstream-integration/e2e-structured/results.json`、`run.log`、`screenshots/` | — |
| 前端类型检查 | `pnpm exec tsc -p tsconfig.app.json --noEmit`（`web-app/`） | 退出码 0 | 否 | 本次会话输出 | — |
| 前端构建 | `pnpm exec vite build`（`web-app/`） | `✓ built in 13.56s`，退出码 0 | 否 | 本次会话输出 | — |
| Python 静态检查 | `ruff check <本次改动文件>` | `All checks passed!` | 否 | 本次会话输出 | — |
| Docker Compose 全栈启动 | — | not-run | 否 | — | 未执行；本机服务以多进程方式运行 |

#### 3.1 真实 LLM 验证覆盖的三条链路

`tests/integration/test_live_llm_resources.py`（每次运行都做真实 HTTP 调用）：

| 类型 | 请求 → 真实 LLM → JSON 解析 → Pydantic → content_validation → 审核状态 → 持久化 → 回读 |
|---|---|
| `mind_map` | ✅ 节点/连线非空；回读 `structured`/`content_validation` 均存在 |
| `code_case` | ✅ `run_steps` 非空、无 `executed` 字段；回读一致 |
| `video_script` | ✅ `chapters` 非空、无 `video_path`；总时长 = 各章之和 |

失败语义（同样真实执行）：

| 场景 | 期望 | 实测 |
|---|---|---|
| 服务端不可达（`http://127.0.0.1:9/v1`） | 抛错，不返回资源 | `ResourceGenerationError`，4.1 s 内失败 |
| 模型只回散文（真实调用后要求非 JSON） | 结构错误，不猜 | `ResourceGenerationError: ... did not return a JSON object` |
| 推理预算 1 秒 | 真实超时错误 | `ResourceGenerationError`（底层 `AI_INFERENCE_TIMEOUT`） |
| 无检索结果 | `insufficient_evidence`，不伪造来源 | `verdict=insufficient_evidence`、`citations=[]` |
| 日志卫生 | 不出现 Key / `Authorization` / 完整 Prompt | 断言通过（`caplog` DEBUG 级） |

**如实记录的不稳定现象**：同一套 live 测试在 2026-10-16 当天共运行 3 次——
第 1 次 3 项因 `openai.APIConnectionError` 失败，第 2 次 1 项因 `openai.APITimeoutError`
（45 s 预算）失败，第 3 次 `8 passed`。前两次是**真实网络/推理延迟**导致的真实失败，
不是被吞掉的错误，也未记为通过。

#### 3.2 浏览器 E2E 覆盖

`node tests/e2e/run-structured-resources.mjs` → `UI: {"passed": 11}`：

| 用例 | 断言数 | 证明 |
|---|---|---|
| S1-home-not-blank | 3 | 首页不是空白页 |
| S2-student-register | 2 | 一次性学生账号注册成功 |
| S3-real-llm-generation | 10 | **真实** 调 `POST /resources/generate` 三次（200 / id / 审核非 rejected） |
| S4/S5/S6 三类渲染 | 9 / 9 / 10 | 类型名 + 结构化正文 + 校验状态 + 详情接口回读 |
| S7 空结构态（注入） | 3 | 载荷为空时显示定义好的空态 |
| S8 409 / 422 / 503（注入） | 13 | 三个状态码各自出现可理解错误提示且页面不白屏 |
| S9 列表 503（注入） | 4 | 页面级错误横幅显示后端 detail |
| S10 未知类型（注入） | 4 | 显示原始类型名 + 兜底提示，不空白 |
| S11 刷新持久化 | 5 | `page.reload()` 后结构化内容仍可读 |

`results.json` 中 `injected_states` 明确标注了哪些是注入状态（S7/S8/S9/S10），
与 S3 的真实模型产出分开记录；`generation.resources` 记录每次真实生成的
`http_status / elapsed_ms / resource_id / audit_status / validation_verdict / structure_passed`。

本次运行的三个真实资源（学生账号 `e2es_*`，密码不入库）：

| 类型 | 知识点 | HTTP | 耗时 | 资源 id | 审核 | 校验 |
|---|---|---|---|---|---|---|
| `mind_map` | 二分查找 | 200 | 9.8 s | 204 | `passed` | `insufficient_evidence` / 结构通过 |
| `code_case` | Python 循环结构 | 200 | 7.5 s | 205 | `passed` | `insufficient_evidence` / 结构通过 |
| `video_script` | HTTP 请求与响应 | 200 | 15.8 s | 206 | `passed` | `insufficient_evidence` / 结构通过 |

> `insufficient_evidence` 是**真实结论**：这三个知识点在当前 Chroma 知识库里没有命中可引用的
> chunk，校验层因此拒绝声称来源。这不是"通过"，也不是伪造来源。

#### 3.3 外部服务验证明细

| 服务 | 原始命令 | 健康检查结果 | 失败日志摘要 | 是否影响验收 |
|---|---|---|---|---|
| PostgreSQL | `python scripts/verify_external_services.py --only postgres` | 隔离库 `learning_system_verify_pg`：`alembic upgrade head` 成功，head = `20261016_0009`，核心表存在，`users`/`resources` 写入+回读成功，迁移后 `uvicorn user-service` 起得来并 `/health` 200 | 无 | 否（PASS） |
| Neo4j | `... --only neo4j` | `verify_connectivity` 0.09 s，`RETURN 1` = 1，写入/读取/删除节点成功（残留 0）；指向死端口时不建 driver、断路器打开、预检 0.51 s；静默端点上查询 0.51 s 内超时；Neo4j 下线时 SQL 回退仍返回已存依赖 | 无 | 否（PASS） |
| Chroma | `... --only chroma` | persistent 模式与配置一致；collection upsert→query 返回带 `content` + `metadata.source_id` 的 chunk；无检索时 `insufficient_evidence`；服务端 `/api/v1` 建集合/add/get/query/delete 正常 | `chromadb 1.5.9` 访问 `/api/v2/auth/identity` → `404 {"detail":"Not Found"}` | **是**：`CHROMA_MODE=http` 在本机解释器下不可用（blocked，见 §4） |

Neo4j 降级/超时按隔离进程运行（`NEO4J_URI=bolt://127.0.0.1:7699`、
`NEO4J_CONNECTION_TIMEOUT_SECONDS=0.5`），因此不会污染正在运行的服务；
Chroma 的写入全部落在 `artifacts/.../chroma-scratch/` 与临时集合，
不影响 `./knowledge_base/index` 的生产集合。

### 4. 未完成 / 阻塞 / 未验证

| 项目 | 状态 | 原因与保留物 |
|---|---|---|
| `CHROMA_MODE=http` 在本机解释器下可用 | **blocked** | 本机 `chromadb 1.5.9` 与服务端 `0.5.5` 协议大版本不兼容（`/api/v2` vs `/api/v1`）。`pyproject.toml` 已声明 `chromadb>=0.5.5,<1.0`，但该解释器未遵守；修复方式是对该环境执行 `pip install -e .`（本项目 docker-compose 的 agent-service 正是这样安装的）。验证器与集成测试都保留了对该路径的检查 |
| 按声明约束复验 http 兼容性 | **blocked** | `chroma-hnswlib` 在 CPython 3.12 / win_amd64 上没有预编译轮子，本机无 MSVC 构建工具，隔离 venv 安装失败。失败原文保留在 `chroma-pinned-venv-BLOCKED.txt`；删除该文件即可重试 |
| Docker Compose 全栈启动验证 | **not-run** | 本机服务以多进程方式运行（8001–8007 + 5175），未执行 `docker compose up`。`docker-compose.yml` 的 agent-service 使用 `pip install -e .`，因此其 chromadb 会遵守声明约束，但**本次没有实测** |
| 上游仓库测试 | **not-run** | 结论不变：上游测试不覆盖 Agent/RAG，ZhiShu 的 `test_api.py` 断言不存在的路由 |
| 上游行为等价性比对 | **not-run** | 未复制上游代码，不存在可比对的"原实现" |
| 真实教师/管理员人工验收 | **not-run** | 本次只做自动化验证，未做人工 UAT |

### 5. 风险与已知限制

1. **`GET /resources/{id}` 现在会返回生成内容与校验报告，而该端点仍是匿名可读的**（与列表端点
   一致）。这扩大了此前的暴露面——`owner_user_id` 本来就已经公开。若资源正文被视为个人数据，
   应把该端点改为需要认证；本次为保持既有契约未改授权，仅把注释改为与实现一致。
2. **`unsupported` 的含义偏宽**：当检索到了 chunk、但内容完全没有内联引用标记时，
   校验层输出的也是 `unsupported`（本意是"引用了不存在的来源"）。后端判定语义未改（会破坏
   既有 39 项校验测试的契约），前端改为按 `citations` 是否为空显示两种不同措辞。
3. **确定性校验仍是启发式**，不是语义正确性证明；`code_case` 的语言/可运行性、
   `video_script` 的时长合理性都只做结构检查。
4. **来源覆盖率在结构化资源上恒为 0**：三种结构化类型按设计不内联引用标记，因此只要检索命中，
   `source_passed` 就是 `false`。这是真实信号，不是噪声，但也不代表内容有错。
5. **真实模型延迟不稳定**：当天出现 `APIConnectionError` / `APITimeoutError` 各一次；
   默认 45 s 预算对 `video_script` 这类长结构化输出偏紧。测试如实失败而非重试掩盖。
6. **`_ensure_legacy_columns()` 仍保留**：它是本地 SQLite 的补列路径。新增迁移让真实数据库不再
   依赖它，但两条路径同时存在仍可能在将来引入新的漂移；理想做法是让本地开发也走 Alembic。
7. **图补全的进程级 dispatcher 无法真正退休**（测试用 `_drain_enrichment_queue` 只能丢弃引用）。
   生产是单例、不受影响，但测试隔离依赖「被换下的线程不会恰好醒来」，本次已把相关断言改为
   按知识点键判断，未改动生产线程模型。

