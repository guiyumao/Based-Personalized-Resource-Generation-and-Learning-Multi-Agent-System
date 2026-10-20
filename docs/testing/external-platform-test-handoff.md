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

