# 下一轮全局审计执行 Prompt（无费用部分收口 + 最终报告）

> 用法：新建会话后，从「==== 开始复制 ====」到「==== 结束复制 ====」整段复制发送。
> 本 Prompt 是 2026-10-19 全局审计的续跑指令，承接 `artifacts/global-audit-20261019-1714/` 下已落盘证据，禁止从头再来。
> 真实 DeepSeek 测试仍按 `docs/testing/deepseek-live-test-prompt.md` 单独执行，未授权前全部 BLOCKED，不要擅自出网。

==== 开始复制 ====

你是高级软件测试架构师、全栈工程师、AI 系统测试专家和数据库审计专家。继续执行「基于大模型的个性化资源生成与学习多智能体系统」的全局功能测试、系统审计与质量评估。本轮是收口轮，只做**无费用、隔离、可真实执行**的剩余工作并产出最终报告。

# 一、接续基线（必须先读，禁止重新盘点）

项目根目录：`C:\Users\wdx\Desktop\基于大模型的个性化资源生成与学习多智能体系统`

先按顺序读取并核对：
1. `docs/testing/current-issues-summary-20261019.md`（当前问题清单，含 DEF-012~016、SEC-01~08、TST-01~03 的既有结论）
2. `artifacts/global-audit-20261019-1714/environment.json`、`README.md`
3. `artifacts/global-audit-20261019-1714/` 下 api-inventory.csv（176 端点）、auth-posture-static.csv（170 鉴权姿态）、function-inventory.csv（45 功能）、frontend-pages.csv（30 页面）
4. `evidence/` 下已有 pytest xml、migration-drill.log、ruff.txt、bandit.txt、pip-audit.json、vuln-allowlist-check.txt、webbuild.log
5. `docs/testing/deepseek-live-test-plan.md`（仅了解，30 案本轮继续 BLOCKED）

纪律：
- 上述清单的结论是**待复核/待动态确认的输入**，不是 PASS 证据；但也不要重复造轮子（静态盘点已完成，禁止全仓重扫）。
- 结论必须区分：源码事实 / 历史报告 / 本轮执行结果 / 未验证推断。
- 构建成功、Mock 成功、健康检查、pytest skipped、历史报告一律不得记 PASS。
- 禁止 reset、clean、覆盖式 checkout、整仓格式化；禁止对共享 learning_system.db 做 upgrade/stamp；禁止停已有服务、禁止真实出网调用模型/搜索。

# 二、执行环境恢复（先做，失败就修）

1. 读 `%TEMP%\ext_ai_runroot.txt` 取得 RunRoot；其下 `venv\Scripts\python.exe` 应为 Python 3.12.6 隔离 venv。
2. 验证 venv 存活：`python -c "import fastapi, sqlalchemy, alembic, pytest"`；若 TEMP 被清理，按下述方式重建：
   - 基础解释器：`C:\Users\wdx\AppData\Local\Programs\Python\Python312\python.exe`
   - `python -m venv <RunRoot>\venv`；用 `pip install --no-deps -e .` 装项目本体，再手工装核心依赖（fastapi、uvicorn、sqlalchemy、alembic、pydantic、pydantic-settings、jose、passlib、langchain、langchain-openai、langchain-community、httpx、pytest、pytest-asyncio、ruff、bandit、pip-audit、openpyxl、python-docx、defusedxml 等）；**不要硬装 chromadb/neo4j/redis/minio/pika/elasticsearch/pytesseract**（chroma-hnswlib 需 MSVC，会失败；这些模块均为函数内懒加载，不影响主链路）。
3. Node 以 `web-app` 构建可用为准（v22 + Vite 8 已验证）。
4. 标准隔离环境变量（每个测试进程/服务统一）：
   - `DATABASE_URL=sqlite+pysqlite:///<RunRoot>/runtimeN.sqlite`（每轮新文件）
   - `JWT_SECRET_KEY=test-isolated-secret-0123456789abcdef`、`ENVIRONMENT=test`、`DEBUG=false`
   - `DEFAULT_ADMIN_USERNAME/PASSWORD/EMAIL` 置空、`DEEPSEEK_API_KEY`/`QWEN_API_KEY`/`OPENAI_API_KEY` 置空
   - `LLM_PREWARM_ENABLED=false`、`NEO4J_ENABLED=false`
   - 跑普通 pytest **不要**设置 `ASSISTANT_TASK_EXECUTION_MODE`（设置后会有 9 个 background 模式用例失败）
5. 证据追加写入 `artifacts/global-audit-20261019-1714/evidence/`，命令日志追加 `command-log.jsonl`（真实命令、cwd、开始/结束时间、退出码、输出路径）。
6. 先执行 `git status --short --branch` 与 `git rev-parse HEAD` 记录（基线 HEAD 为 05ee287，工作树 dirty 是预期）。

# 三、本轮任务（按顺序，全部为无费用隔离测试）

## 任务 A：Knowledge Worker 与全部 integration（收口 #12）
- 执行：`python -m pytest tests/integration -q`，以及 `tests/unit` 中 knowledge_*、test_knowledge_lock、test_knowledge_budget 等。
- 对 `tests/integration/test_knowledge_worker_recovery.py`：单独跑并留存 junit xml，重点确认真实进程终止/租约接管/迟到写入围栏（task_id+worker_id+execution_attempt+租约）。
- 对 50+ 知识点分页场景（跨轮游标、上限、防重复派发）、父子任务预算继承、超限停止：若没有现成用例，新增隔离测试；不写只复述实现的测试。
- 输出：evidence/kw-recovery.xml、kw-unit.xml；每个用例 PASS/FAIL/BLOCKED 记入 test-matrix.csv。

## 任务 B：隔离六服务 + 权限矩阵动态实测（收口 #13，本轮最重）
- 用独立 DB、独立 JWT、独立端口（避开 8001-8006 线索端口，可用 18001-18006）启动六个服务，全部指向同一隔离库；启动命令、PID、端口、启动时间写入 evidence/services/。
- 建立六身份：匿名、学生 A、学生 B、教师 A（带本人班级）、教师 B、管理员；各自注册并持久化到隔离库。
- 对 api-inventory.csv 中**全部 176 个 operation** 自动探测：
  - 匿名→期望 401/403 的端点逐一断言；
  - 学生 A 访问学生 B 的会话/任务/附件/记忆/资源/练习/成绩/报告，断言 403/404；
  - 请求体或 query 中篡改 user_id 的越权尝试；
  - 教师 A 不得读教师 B 班级学生数据；学生不得访问教师/管理端点；
  - 教师/学生可用动作差异（如候选审核、发布仅教师/管理员）。
- 接口唯一身份用「服务 + HTTP 方法 + 规范化路径」，同名 /resources 不合并。
- 从**真实前端来源**（Origin 用 Vite dev origin 与任意伪造 Origin 各一）验证 CORS 与 OPTIONS：允许的来源、凭据头、非法 Origin 是否被拒；直接 API 登录成功不能证明浏览器链路通过。
- 重点动态确认（已在静态清单中，不要重新找）：
  - SEC-01：匿名 POST /graph/visualization 对未知知识点是否真的入队 LLM 补全（在无 key 环境下观察队列/线程行为与日志，以及 401 缺失）；
  - SEC-02：匿名 GET /graph/dependencies（先准备 ≥80 字符已存课件的知识点，再观察是否同步触发 LLM 路径与耗时）；
  - TST-02：构造 PENDING 候选、未审核草稿、未发布版本，断言匿名 /knowledge-base 系列读不到；
  - TST-03：成绩单分享 token 的熵、错误 token 404、撤销后失效。
- 输出：evidence/api-authz/（请求/响应/截图式日志）、api-matrix-result.csv，统计接口执行覆盖率与通过覆盖率。

## 任务 C：安全专项动态用例（收口 #14）
- 认证/JWT：alg=none、空签名、错误算法、过期 token、伪造 alg 混淆（已有 test_jwt_algorithm_hardening / test_auth_fallback_verifier，跑通并记录）；python-jose 固定仅 HMAC 生效。
- XSS/Markdown：向问答、记忆、笔记、讨论、资源正文提交 `<script>`、`javascript:`、事件属性、恶意 HTML，检查 API 存储与前端渲染（前端渲染点列出，标记需浏览器复核的项）。
- SQL 注入：对登录、列表过滤、搜索、知识查询参数注入 `' OR 1=1--`、`;drop table`、`%`，断言参数化、无 500、数据不泄露。
- SSRF：deepseek_search 公网校验逻辑，构造 `http://127.0.0.1`、`http://localhost`、`169.254.169.254`、`10.x/192.168.x`、`[::1]`、DNS 重绑定特征域名，断言拒绝；无 key 时验证其在出网前就被拦截。
- 上传/路径穿越：助手附件上传非法扩展名、双扩展名（x.txt/.exe）、伪造 Content-Type、损坏文件、超大文件、`../../etc/passwd` 文件名、zip 路径（若有）；核对大小/格式/引用数量限制的真实值；上传后执行前删除附件的行为；无 OCR 环境时把"图片 OCR"标 BLOCKED，不得记为支持。
- SEC-03：向 transcript_parser 喂 XXE payload（外部实体、参数实体、十亿笑/实体炸弹），验证当前 xml.etree 行为与是否可达；defusedxml 改造前不得宣称已修复。
- 敏感信息泄露：系统配置/健康检查/错误响应/日志中是否出现密钥、Token、连接串、PII；导出接口字段最小化。
- 每条用例记录：请求、期望、实际、证据路径、P 级判定。

## 任务 D：无费用性能基线（收口 #15）
- 先读 `tests/global/probe_perf.py`、`build_perf_baseline.py` 的参数与数据隔离，确认无真实模型调用再运行；若其默认会出网，改为显式禁用/桩。
- 采集：六服务冷启动、非模型 API（登录、列表、知识读取、公开端点）延迟、图谱缓存命中/未命中、本地检索；任务排队到 Worker 完成的端到端（Mock 模型，标注证据层级）。
- 样本数、并发、预热、硬件环境如实记录；样本不足只给均值/中位数/最大，**不写 P95/P99 高可信结论**。
- 隔离复现 DEF-012 的两个失败（1.0s 预算实测 1.12s、8 并发补全计数为 0），多次运行给出分布，定性是 SLO 不合理、性能回归还是用例问题；给出是否调整阈值的建议（调阈值必须改文档）。
- 输出：evidence/perf/、perf-baseline.json。

## 任务 E：浏览器受控 e2e（能做多少做多少，Mock 模型，禁止真实 key）
- 先检查 Playwright 浏览器是否安装（tests/e2e/node_modules 是 junction）；未安装则标记 BLOCKED，不要联网下载。
- 优先复用/修补现有脚本（注意 run-assistant-retry.mjs 未处理新确认对话框、硬编码 .env 管理员）：登录→画像设置→工作台；问答→会话刷新读回；附件→课件→练习→DOCX；练习评分重放/冲突→错题/收藏；路径草案→确认→重复确认；任务取消（含 request-cancel）与重试；两名用户并发隔离。
- 失败留截图、console、network 证据。真实模型链路全部 BLOCKED，不得把 Mock 浏览器结果记为真实模型通过。

## 任务 F：最终交付物（收口 #16）
在 `artifacts/global-audit-20261019-1714/` 补齐：
1. `source-manifest.json`：本轮涉及源码文件 SHA256、HEAD、工作树差异文件清单。
2. `test-matrix.csv`：用例 ID、模块、功能/API、依据、优先级、证据层级、前置、隔离环境、命令、预期、实际、状态（PASS/FAIL/BLOCKED/NOT_RUN）、证据路径、缺陷 ID。
3. `command-log.jsonl`：真实执行的命令全量（计划的不得写成已执行）。
4. `defect-register.md`：把 DEF-012~016、SEC-01~08、TST-01~03 的最终状态（确认/排除/降级/升级）写实；新发现顺延编号；每个缺陷含复现步骤、影响、证据、根因确定性、修复建议、P0-P3。
5. `reports/` 七份分项报告：架构与数据流、前端与 e2e、API 与权限、AI 与两类 Worker、知识建设/维护/版本/索引、数据库迁移/安全/供应链、性能稳定性与优化路线。同 ID 引用，不重复堆砌。
6. `GLOBAL_TEST_SUMMARY.md`：含统计口径（见下）、闭环清单、阻塞清单、Top 10 实际问题（不足不凑）、阶段意见。
7. 回填 `function-inventory.csv` 的 implementation_status / verification_status 两列。

统计口径（严格执行，分母为零写"不适用"）：
- 已执行用例数 = PASS + FAIL；执行通过率 = PASS / (PASS + FAIL)
- 执行完成率 = (PASS + FAIL) / 纳入计划用例数
- 接口执行覆盖率 = 本轮实际检查的唯一接口数 / 已发现接口数（176）
- 接口通过覆盖率 = 本轮通过检查的唯一接口数 / 176
- pytest 跨批次（45 / 115 / 503）必须按节点 ID 去重后再统计，不能累加历史数
- coverage 若运行则单独报告；未运行标未运行

最终结论必须分别给出，不能用"可以继续开发"代替"可以部署"：
- 继续开发：Go / Conditional Go / No-Go / 证据不足
- 进入集成测试：同上（Conditional Go 写明适用范围、限制、解除条件）
- 生产部署：同上
- 下一阶段必须先解决的问题清单（P1 全部进清单）

# 四、已知问题快速复核清单（动态确认即可，禁止重新翻代码找一遍）

- DEF-012 图谱性能两项失败（隔离复现定性）
- DEF-013 迁移降级链断裂（0009 downgrade 与 0002 重复 drop created_at/evaluation_json，两引擎都会失败；修复建议已在问题清单，本轮不授权改代码，只补复现与确认）
- SEC-01 匿名 /graph/visualization 后台 LLM 入队（默认开启、无预算预留）
- SEC-02 匿名 /graph/dependencies 同步 LLM 路径（allow_llm 默认 True，需 ≥80 字课件触发）
- SEC-03 成绩单 xml.etree XXE 面
- SEC-08 python-jose PYSEC-2026-4298 别名未入 allowlist，门禁 FAIL（实际攻击前提已被 HMAC-only 关闭）
- TST-01 新取消流程浏览器零覆盖
- TST-02/TST-03 公开语料范围、分享 token 生命周期
- DEF-014/015/016 ruff B904、F402、E702（静态已定性，报告中给出整改建议即可，不授权批量改代码）

# 五、边界与授权

- 本轮**无费用**：禁止任何真实模型/Search/Fetch/抓取调用；无密钥、无预算、无授权的 DeepSeek 30 案保持 BLOCKED。
- Chroma persistent/HTTP、Neo4j、Redis、RabbitMQ、Elasticsearch、MinIO、PostgreSQL、docker 迁移演练：无实例即 BLOCKED，写明解锁条件，不得伪造结果。
- 允许新增隔离测试脚本/夹具/报告；不得修改业务规则、不得升级共享库、不得重启既有服务、不得发布到共享索引。
- 每完成一个任务就更新 test-matrix 与 evidence；环境再次卡死时，先清理本会话自己启动的挂起进程（核实 PID 后再杀），禁止杀用户其他进程。

最后用中文向用户汇报：本轮实际验证了哪些闭环、失败/部分/阻塞项、各模块证据层级、Top 问题、三个阶段意见、下阶段必做项；并交付 `GLOBAL_TEST_SUMMARY.md` 与全部 reports/。

==== 结束复制 ====
