# 文档知识库持续开发验收（2026-10-20）

总体仍为 **PARTIAL**。本页补充01–09的首轮检查点，不覆盖其学生端成果。交付是源码及隔离验收，**未激活共享8001–8007/5175，未迁移共享SQLite**。

## 实现与边界

- `knowledge_documents.py`（Service/API）、KnowledgeDocument/KnowledgeDocumentPoint、0027：单一目录适配原corpus及上传原件；PDF/DOCX/MD/TXT解析、原件字节下载、正文、实时Chunk、学科/知识点/来源筛选、批量分类、来源任务、版本与审核记录、未送审上传归档。原件不进入公开corpus；Word原生排版仍通过下载查看，提取上限2万字/5MB/PDF30页，扫描件无OCR。
- `knowledge_candidates.py`、`knowledge_versions.py`：上传进入原候选审核/版本发布；修改、送审、审核、发布、修订、撤回均保留操作标识。发布重放重新检索验证；修订替换旧索引，版本恢复校验检索。
- `knowledge_tasks.py`：沿用Knowledge Worker，增加 `PUBLISH_CANDIDATE`、`RECONCILE_PUBLICATIONS`，复用任务键、并发去重、心跳、租约、执行代次、取消、失败重试。发布任务绑定候选内容哈希；审核撤回或草稿变化阻止后续发布。
- `knowledge_publication.py`：有效SQL版本是candidate文件的读取授权。每次检索（含缓存命中）、单篇索引详情、生成上下文重用均重新过滤；未提交/已撤回片段不能因为Chroma仍存在而返回。检索验证仅在内部ContextVar中允许当前待发布路径，客户端不能设置。
- 对账按SQL有效版本恢复缺失文件、退役孤立candidate文件并增量索引。保持跨进程知识锁，不清空集合。SQL提交/flush失败回滚并补偿；硬退出后的孤立向量先被读取门禁隔离，再由持久任务重跑恢复。不是跨SQL/Chroma原子事务，也不承诺任意外部副作用exactly-once。
- `KnowledgeDocumentManager.vue`、`knowledge.vue`、`subjects.vue`、`useAdminWorkspace.ts`：真实目录/分类/来源/正文/原件/Chunk/记录/归档/撤回入口，发布进入Worker队列；查看任务结果沿用任务页。学科候选匹配需明确确认，不自动合并。
- 图谱鉴权、公共资源过滤及禁止读取触发模型的待审修复已核对；工作区同期另有图谱私有上下文与学习门禁开发，本轮保留并对当前 `test_graph_security_p1.py` / `test_graph_performance.py` 回归，不将其全部改动归为本页独立实现。真实Neo4j及历史数据来源清理尚未验证。
- 0009 downgrade保留0002创建的answer_records.created_at/evaluation_json，避免跨版本错误删除。没有修改共享Alembic版本。当前迁移head已由同期开发推进至0029。

## 新增或增强接口

均沿用原agent服务身份校验；`/knowledge-base/admin/*`及候选/版本写操作仅管理员。

| 接口 | 行为 |
|---|---|
| GET `/knowledge-base/admin/documents` | 分页、标题/学科/格式/状态/来源过滤，分清文件/记录/规则/URL |
| POST `.../documents/upload` | 有界解析并保存原始字节，草稿不进公开索引 |
| GET `.../documents/{id}`、`/original`、`/chunks`、`/history` | 正文、管理员原件、实时片段、版本/来源任务/操作记录 |
| POST `.../documents/classify`、`/{id}/candidate`、`/{id}/archive` | 原子批量分类、转原审核链、未送审上传归档 |
| GET `.../subjects/preflight`、`/{id}/coverage` | 显式关联建议、有依据的知识点覆盖 |
| POST `/knowledge-base/candidates/{id}/publish-task` | 202持久发布任务，接收client_request_id |
| POST `/knowledge-base/candidates/{id}/withdraw` | SQL立即撤回公开访问，原队列异步对账清理 |
| POST `/knowledge-base/admin/reconcile` | 可重跑的版本/文件/索引对账任务 |

原同步publish接口兼容保留；管理员页面使用持久publish-task。原件缺失但正文存在时仍可预览正文。Chroma不可用返回503，不把空Chunk当成功。

## 真实执行证据

证据根：`artifacts/aura-full-integration-20261020/`。

- `build-resume-final.log`：最新完整 `npm run build` 退出0，保留第三方vis-network注释等构建提示。
- `resume-final-unit-v1/command.log`：105 passed / 389 warnings；其后补充SQL flush补偿回归，最终 `resume-final-unit-v2/command.log` 为 **106 passed / 396 warnings**，退出0。
- `migration-resume-v2/migration-result.json`：空库升级head0029；0009→0008保留0002列；0027→0026→head；隔离账号保留，shared_db_touched=false。
- `documents-browser-v8/`：真实SQLite、真实Chroma HTTP（本机chromadb 1.5.9）、独立Worker进程、Vue和Chromium。上传PDF→原件保存→真实解析→分类/知识点关联→刷新读回→送审→批准→持久任务发布→学生实际检索。修订替换、重复任务键、回滚检索；上下文进入原课件生成并保存版本引用。**课件模型输出为本地桩，generation_provider=LOCAL_STUB_ONLY，不能标为真实Provider验收**。
- `documents-browser-v9/`：在上条基础上追加浏览器读取版本/来源/审核记录、未送审上传归档、并发同键发布测试；runtime-result.json及browser-result.json均passed=true，执行87.765秒，退出0。
- 实际Worker硬退出测试：真实索引成功后测试专用子进程os._exit(79)，SQL无版本、任务RUNNING；读取门禁拒绝孤立片段；测试时推进隔离租约过期、重启Worker，execution_attempt=2、COMPLETED且只一条版本。撤回后缓存片段立即被拦截，再执行清理任务。
- 原件按字节比对；匿名401、学生403，草稿没有学生检索命中；目录发布后不重复计数，Chunk关联正确，有效知识点覆盖为1。
- 截图 `document-parsed-and-classified.png`、`review-published.png`、`document-live-chunks.png`、`document-mobile.png` 已实际查看；390宽度无横向溢出。浏览器pageErrors/apiErrors为空；路由切换造成少量ERR_ABORTED请求保留于requestFailures，未隐藏。
- 依赖故障和失败证据保留：browser-v1缺少可选telemetry依赖，v2监听竞争，v3隔离CORS，v4 Element Select内部input指针拦截，v5查询回显断言，v6消息框定位。依赖仅安装到 `chroma-test-deps/`，没有更改共享Python安装或pyproject版本约束；测试增加端口占用/子进程退出检查。v7首次完整基础闭环通过。

测试入口均经 `scripts/run_no_cost_tests.py --run-root <独立目录>`。浏览器运行声明允许端口18207/18208/15188，`APP_LOAD_DOTENV=false`，真实凭证不继承；浏览器仅允许两个隔离origin。真实Chat/Search/Fetch调用为0，不沿用历史付费授权。

## 剩余事项及恢复顺序

1. 本轮只完成文档及其发布可靠性验收子集，尚不具备全管理员端/全学习端验收条件。
2. preflight目前使用主数据/别名/目录标题和建设任务；实时Chroma metadata匹配明确NOT_QUERIED。覆盖率依据明确关联+活动审核版本+当前索引清单，单独的实时检索仍为必要证据。跨学科已发布资料不直接换学科，需要新资料或明确的新版本关联设计。
3. 已送审/已发布内容的批量归档、永久安全删除、复杂知识点版本关联快照、更大文档全文处理/异步解析、OCR、原生DOCX预览、来源自动变更监测仍未完成。
4. AI补充资源专用编辑/重新生成/Prompt优化/图片Provider、完整Token持久账本/预算/Worker全量监控仍PARTIAL或MISSING；不能把本次知识任务usage预留或本地生成桩当全模型真实用量。
5. 全站浏览器、PostgreSQL、真实Neo4j、长时间故障/并发压力、真实付费Provider均未验收。真实共享运行激活需先审计现有数据库基线/备份/同期0028和0029变更。
6. 接续先复核Git与同期改动、07/08/09及本页；复用现有测试入口，按后续功能改动选择必要回归，不重新全仓库扫描。
