# 全局审计·当前问题清单（截至 2026-10-19）

> 适用项目：基于大模型的个性化资源生成与学习多智能体系统（FastAPI 六服务 + SQLAlchemy/Alembic + SQLite + Vue3/Vite + 两类 Worker + DeepSeek + Chroma/Neo4j 可选）
> 证据目录：`artifacts/global-audit-20261019-1714/`
> 证据层级：**静态**=源码/配置核对；**隔离实测**=本轮在隔离 venv/隔离库中真实执行；**待动态确认**=静态证据充分但尚未在运行服务中复现；**BLOCKED**=缺环境/密钥/授权。
> 重要区分：以下均为 2026-10-19 本轮审计的结论；历史报告（local-audit-verification、V8.3 交接等）仅用于定位，不计入本轮 PASS。

---

## 一、总体判断（先给结论）

- **代码与测试骨架完整度高**：176 个后端 operation、42 张表、30 个前端路由、45 项业务功能；170 个端点中 159 个显式声明了认证/角色依赖；前向迁移链 25 步可在空库完整重放；核心任务链 499 个测试节点通过（含 2 个真实子进程 kill/恢复）。
- **但"可用"不等于"可验收"**：权限矩阵未做六身份动态实测、浏览器 e2e 零覆盖新取消流程、知识 V8.3 全链路在本机无 Chroma/外部服务时无法真实走通、DeepSeek 真实模型 30 案全部 BLOCKED。
- **当前阶段意见（开发/部署分开）**：
  - **继续开发：Go**（骨架与测试基础足以支撑下一阶段）。
  - **进入集成测试：Conditional Go**（须先修 P1 中的迁移降级断裂与匿名 LLM 触发，并完成权限矩阵实测）。
  - **生产部署：证据不足，暂不具备验收依据**（真实模型、Chroma、权限隔离、安全专项、性能基线均未完成）。

---

## 二、已确认缺陷（按 P0–P3）

### P1（影响数据安全/回滚可靠性/成本，必须在集成测试前处理）

| ID | 缺陷 | 证据层级 | 证据 | 影响 | 最小修复建议 |
|---|---|---|---|---|---|
| **DEF-013** | **Alembic 全量降级链断裂，且两种数据库引擎都会失败** | 隔离实测 | `evidence/migration-drill.log`：隔离 SQLite 空库 upgrade head 成功；`downgrade base` 回退到 0002→0001 时 `ALTER TABLE answer_records DROP COLUMN created_at` 报 `no such column: created_at`，exit=1 | 根因：0009 对账迁移（reconcile_orm_drift）的 downgrade 无条件 drop `answer_records.created_at/evaluation_json`，而这两列归 0002 所有，0002 的 downgrade 会再 drop 一次；`DROP COLUMN` 无 IF EXISTS，PostgreSQL 同样失败。且 DDL 非事务式，失败后留下半降级 schema（本次停在 0002）。**应急回滚能力实际不可用** | 0009 downgrade 移除 answer_records 两列（归 0002 所有），或在 0002 downgrade 用 inspector 守卫；补一条"head→base→head"的 CI 演练（SQLite + PostgreSQL 各一） |
| **SEC-01** | **匿名 POST /graph/visualization 可触发后台 LLM 补全** | 静态（链路已逐行核实，待动态确认） | `graph.py` POST `/visualization` 无任何 auth 依赖；`neo4j_connector.get_visualization_graph`→`_schedule_enrichment`；`GRAPH_LLM_ENRICH_ENABLED` 默认 True（config.py:193）、4 worker、启动延迟 20s；缓存 only；`_run_enrichment`→`_enrich_visualization_graph` 调 LLM，**未见 knowledge_budget.reserve_usage** | 未认证用户可通过构造任意知识点名入队模型调用（每 cache key 一次、但 key 可无限枚举），形成成本消耗与线程池占用；与知识建设路径的预算体系脱节 | 该端点加 `get_current_user` 或显式公开白名单；补全调用纳入 knowledge_budget 预留；对未知知识点增加速率限制；`GRAPH_LLM_ENRICH_ENABLED` 默认值改为与生产部署一致的保守项 |
| **SEC-02** | **匿名 GET /graph/dependencies 存在同步 LLM 调用路径** | 静态（链路已逐行核实，待动态确认） | `graph.py` GET `/dependencies` 无鉴权；`find_dependency_path`→`_build_dependency_paths_from_content`→`_derive_prerequisites(kp, article)`，该方法签名 `allow_llm: bool = True`（neo4j_connector.py:855），且 LLM 优先于正则；触发条件：该知识点存在已存课件文本且 ≥80 字符（`_extract_kp_labels_via_llm` 772 行） | 与 graph.py 模块 docstring"请求路径不得阻塞 LLM、保持响应无模型依赖"直接矛盾（可视化端点已按此修，依赖端点漏修）；匿名请求可能被长耗时模型调用阻塞（有超时上限）并产生成本 | `_build_dependency_paths_from_content` 调用处显式传 `allow_llm=False`；请求路径同步 LLM 全部改为后台补全；并对该端点补鉴权 |
| **DEF-012** | **知识图谱性能/并发两个测试用例失败，可复现** | 隔离实测 | `evidence/expanded.log`、`graph.log`：`test_graph_performance.py` 两项失败——预算 1.0s 实测 1.12s（SLO 超 12%）；8 并发补全计数为 0 | 图谱相关端点可能不满足自身延迟 SLO；并发补全/去重逻辑在并发下不产生预期成果，与 SEC-01 的后台补全机制同一代码区域 | 修复后重新跑性能用例并记录环境；若 SLO 已不现实应正式调整阈值并在文档中说明，不能让测试长期红着 |

### P2（影响安全面或交付可信度，应在集成测试阶段处理）

| ID | 缺陷 | 证据层级 | 证据 | 影响 | 最小修复建议 |
|---|---|---|---|---|---|
| **SEC-08** | **依赖漏洞策略门禁当前 FAIL：python-jose 通告以 PYSEC ID 出现，allowlist 只收了 CVE 别名** | 隔离实测 | `evidence/pip-audit.json` + `evidence/vuln-allowlist-check.txt`：pip-audit 2.10.1 报 3 个无修复版本漏洞——ecdsa 0.19.2 PYSEC-2026-1325（=CVE-2024-23342 Minerva 计时攻击，2 条均在 allowlist 内、2027-01-15 到期）；python-jose 3.5.0 **PYSEC-2026-4298（别名 CVE-2026-85394）不在 allowlist**，checker 按"通告 ID+包名"精确匹配且不解析别名，输出 UNKNOWN / RESULT: FAIL | 同一漏洞已有 CVE 条目（HS256 算法伪造，前提是未限制算法且攻击者持有公钥）；本项目配置仅允许 HS256/384/512、拒绝非对称算法（test_jwt_algorithm_hardening.py 已覆盖），攻击前提被关闭，实际残余风险低；但**按项目自己的 CI 门禁规则当前就是红的**，且未来迁移 JWT 库前都处于"未正式接受"状态 | 在 `.github/vulnerability-allowlist.json` 增加 id=PYSEC-2026-4298 条目（复用同一 impact/mitigation/review_by），或让 checker 按 aliases 匹配；迁移到受维护 JWT 库的跟踪项保留 |
| **SEC-03** | 成绩单解析裸用 `xml.etree.ElementTree`，defusedxml 已在依赖却未使用 | 静态（bandit B405） | `bandit.txt`；`services/evaluation_service/app/services/transcript_parser.py:11` 解析上传 XLSX 内嵌 XML | 若解析路径接受用户上传文件，存在 XXE/实体炸弹风险（具体可达性待动态验证） | 解析入口前调用 `defusedxml.defuse_stdlib()` 或改用 defusedxml 的 ElementTree；补恶意 XML 测试 |
| **TST-01** | 新取消流程（request-cancel / CANCEL_REQUESTED / TIMED_OUT）浏览器端零覆盖 | 静态 | `tests/e2e/`：run-assistant-retry.mjs 未处理新确认对话框、用 .env 默认管理员；无 request-cancel UI 用例 | 后端重点安全语义在浏览器链路无回归保护；全局 Prompt §7.1/§9 的关键流程无证据 | 新建/修订 e2e harness：运行中取消、排队取消、重试确认对话框、重复确认幂等 |
| **TST-02** | 公开知识读取端点匿名可访问，内容范围未验证 | 静态（待动态确认） | `learning.py` GET `/knowledge-base`、`/subjects`、`/search`、`/{article_id}` 均无鉴权，以 user_id=0 调知识代理 | 设计意图是"公开已发布语料"，但需证明 PENDING/draft/未审核材料、来源元数据不会被匿名读到 | 动态用非 APPROVED 候选与草稿做负向断言；仅 PUBLISHED/APPROVED 对匿名可读 |
| **TST-03** | 分享链接 token 公开读取 | 静态（部分正面） | `transcripts.py` GET `/transcripts/shared/{token}` 无鉴权；0007 迁移注明"revocable opaque share tokens" | 设计为公开分享；仍需验证 token 熵、撤销/失效、分享内容不含未授权字段 | 动态验证：未授权 token 404、撤销后失效、仅暴露报告所需字段 |
| **DEF-014** | `knowledge_tasks.py:197` 在 except 内 raise 未带 from | 静态（ruff B904） | `ruff.txt` | 异常链丢失，故障注入排查困难 | 改为 `raise ... from err` |
| **DEF-015** | `report_service.py:1518` 循环变量 `update` 遮蔽 SQLAlchemy `update` import（F402） | 静态（已人工核实无运行时 bug） | ruff.txt；该函数内只用循环变量对象，未用 SQLAlchemy update | 当前无害，但后续在该函数内误用即静默出错 | 循环变量改名 `profile_update` |
| **DEF-016** | 知识模块与脚本中 56 处分号多语句（E702，60 项可自动修复） | 静态 | ruff.txt；集中在 knowledge_* 与 verify_knowledge_v83.py | 风格一致性差，审计/审查脚本可读性低 | 一次性 `ruff --fix` 后单独提交，避免与业务改动混杂 |

### P3（低风险/运维与可维护性）

| ID | 项 | 证据 |
|---|---|---|
| SEC-04 | 生产代码中 5 处 `assert`（profile_scoring.py:161、qa_service.py:298、knowledge_tasks.py:320 等），-O 下会被移除 | bandit B101 |
| SEC-05 | 7 处 try/except: pass（neo4j_connector、exercise_generation、tag_analysis、profile_builder），错误被静默吞掉 | bandit B110 |
| SEC-06 | 运维脚本中 subprocess 均 shell=False（无注入），urlopen 固定 127.0.0.1、B608 为参数化 SQL 嵌入脚本报误报——**两条中危为可接受误报**，但应加注释或 allowlist 说明 | bandit 2 中危，均已人工定性 |
| SEC-07 | `crawl_resources.py:31` E402 模块级 import 位置 | ruff |

---

## 三、静态鉴权姿态（170 个端点）

- 92 AUTH（登录用户）、65 ROLE（角色限制）、11 NONE（无鉴权）、2 OPTIONAL。
- 11 个无鉴权端点分类：
  - **设计公开**：POST /users/register、POST /users/login、GET /subjects（admin.py 注释 public）、GET /transcripts/shared/{token}（见 TST-03）。
  - **公开语料读（待验证内容范围）**：GET /knowledge-base 系列 4 个（见 TST-02）。
  - **图数据 3 个（有问题）**：POST /graph/visualization（SEC-01）、GET /graph/dependencies（SEC-02）、GET /graph/related-resources/{kp}（仅确定性读取，暂未发现 LLM/写入，但匿名可读图数据本身需确认是否符合预期）。
- **重要事实**：所有 APIRouter 均无路由级鉴权，鉴权完全依赖逐端点声明——任何新增端点漏写 Depends 即默认公开，这是 SEC-01/02 出现的机制性原因。

---

## 四、本轮已验证可用的能力（真实执行，非推断）

| 能力 | 证据 | 结果 |
|---|---|---|
| 核心任务链（45 案，含 4 个 Agent 边界 + 3 个期限参数） | evidence/task-chain.xml | 45 passed |
| 组合回归（10 文件） | evidence/combined.xml | 115 passed |
| 扩展回归全量（去重前 503 节点） | evidence/expanded.xml | 499 passed / 2 failed / 2 skipped（2 skipped 为 live_llm/external_service 闸门） |
| Assistant Worker 真实子进程 kill、租约过期、接管恢复 | integration/test_assistant_worker_process.py | 通过（含真实进程终止，非 mock） |
| 隔离空库前向迁移 25 步 + 失败后重放 | evidence/migration-drill.log | 升级 PASS、重放 PASS、单一 head |
| 前端生产构建 | evidence/webbuild.log（tsc + vite） | 通过，dist 88 文件 3.97MB |
| 静态安全扫描 | evidence/bandit.txt | 0 高危 |
| 静态质量扫描 | evidence/ruff.txt | 119 项风格/可维护性问题 |

---

## 五、BLOCKED / 未验证项（下一轮处理）

| 项 | 阻塞原因 | 解锁条件 |
|---|---|---|
| DeepSeek 真实模型 30 案（DS-01~30） | 无测试密钥/预算/授权 | 提供专用测试密钥（交互注入）、Chat/Search-Fetch 授权、调用/Token/时长上限、费率或确认"金额未知" |
| 六身份 × 176 端点权限矩阵（含 CORS/OPTIONS 真实前端来源） | 未启动隔离六服务 | 下一轮无费用可做（不依赖外部服务） |
| Knowledge Worker 恢复与全部 integration | 未单独执行 | 下一轮无费用可做 |
| XSS/SQL 注入/SSRF/路径穿越/上传限制/JWT 动态专项 | 未做 | 下一轮无费用可做（SSRF 校验代码已有公网校验逻辑，需构造用例） |
| 性能基线（probe_perf/build_perf_baseline） | 未做 | 下一轮无费用可做，注明样本数，不下高可信 P95/P99 |
| 真实浏览器 e2e（§9 全部流程） | 未跑 | 下一轮可做 Mock 模型受控集成；真实模型链路另计 |
| Chroma persistent/HTTP、Neo4j、Redis、RabbitMQ、ES、MinIO、PostgreSQL | 本机无实例/依赖编译失败（chroma-hnswlib 需 MSVC） | 提供实例或授权在本机安装相应服务 |
| 依赖漏洞扫描 | **已完成**：pip-audit 2.10.1，3 个无修复版本漏洞（ecdsa 2 条已接受、python-jose 1 条门禁 FAIL，见 SEC-08）；证据 pip-audit.json / vuln-allowlist-check.txt |
| AI 内容质量人工评审（DS-30） | 无人工评审 | 组织人工评审 |

---

## 六、本轮实测统计口径

- pytest 已执行节点（扩展回归，未与前两批去重）：**503 = 499 passed / 2 failed / 2 skipped**；前两批 45、115 与扩展批存在重叠，**下一轮须用节点 ID 去重后给最终数**。
- 迁移演练：7 步中 5 PASS / 1 FAIL（降级）/ 1 半状态；前向链 100%。
- 前端构建：1 PASS。
- 静态：ruff 119（60 可自动修复）；bandit 50（0 高 / 2 中 / 48 低，2 中危已定性为误报）；pip-audit 3 个无修复版本漏洞（2 已接受、1 门禁 FAIL，见 SEC-08）。
- 不计入 PASS：pytest skipped、构建成功、Mock 成功、健康检查成功、历史报告结论。

---

## 七、证据索引

- 清单：`api-inventory.csv`（176）、`auth-posture-static.csv`（170）、`function-inventory.csv`（45）、`frontend-pages.csv`（30）
- 日志：`evidence/task-chain.xml`、`combined.xml`、`expanded.xml`、`graph.log`、`migration-drill.log`、`ruff.txt`、`bandit.txt`、`pip-audit.json`、`vuln-allowlist-check.txt`、`webbuild.log`
- 下一轮续跑：`docs/testing/next-round-audit-prompt.md`（可直接复制整段开新会话执行）
- 环境：`environment.json`（含 venv、HEAD、head、隔离变量、结果）
- 前两阶段文档：`docs/testing/local-audit-verification-20261019.md`、`docs/testing/deepseek-live-test-plan.md`、`docs/testing/deepseek-live-test-prompt.md`
