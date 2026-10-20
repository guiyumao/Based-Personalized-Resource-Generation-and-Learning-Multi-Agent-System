# V8.3 知识建设系统：实现与验收记录

更新：2026-10-19（Asia/Shanghai）。本记录替代此前仅到 0019 的进度；测试使用隔离环境，原业务数据库和原 8002 进程未升级。

## 当前真实架构

沿用 FastAPI 多服务、Vue 3/Vite、SQLAlchemy/Alembic、Chroma、现有 Coordinator 和持久 Worker。学科、知识点、候选、版本、资源、练习继续保存到原有模型体系。正式语料仍为 `knowledge_base/corpus`；`KNOWLEDGE_RUNTIME_ROOT` 可将验证语料、索引和锁一起隔离。

## 已实现模块

| 模块 | 本轮实现 | 当前验证级别 |
| --- | --- | --- |
| M1 任务可靠性 | 原子领取、执行代次、45 秒租约、5 秒心跳、1000 秒执行期限、协作取消、写入围栏、限次退避恢复、阶段复用 | 单元测试及真实 Worker 进程终止/重新领取测试 |
| M1 发布与索引 | 保留候选审核门禁；OS 跨进程锁；正式文件、旧版本归档、增量删除、检索验证及失败恢复 | 真实 API、Chroma HTTP、管理员浏览器发布/回滚 |
| M2 学科建设 | DeepSeek JSON 大纲、管理员编辑确认、别名归一、手工学科/知识点、章节/目标/先修关系 | 真实规划 API；确认和权限单元测试 |
| M2 知识建设 | 建设/补充/修订、最多 10 个知识点一批、Search/Fetch 阶段复用、来源综合草稿、模型证据 URL 校验 | 真实单知识点 Search/Fetch/DeepSeek 综合；批量接口单元测试 |
| M3 统一知识上下文 | 六类覆盖状态、目录/别名识别、语料和检索证据、资源/练习/问答/路径共享上下文、可选公开资料补充 | 资源+3题真实组合任务；问答/路径及隐私单元测试 |
| M4 维护 | 一次性/周期计划、章节/知识点范围、巡检或补充待审、每轮 50 点游标、调用/Token/可配置金额预算、历史报告 | 真实到期派发及复用候选；51 点跨轮扫描单元测试 |
| M5 版本 | 不可变版本、草稿差异、版本对比、恢复历史版本、有效版本指针、关联课件/练习待复核 | 真实发布及恢复检索；版本与影响逻辑单元测试 |
| M6 界面 | 原 AdminView 中的大纲、建设、编辑/授权/审核/发布、版本恢复/关联成果、维护报告、用量和重试；学生公开补充开关/来源提示 | 管理员发布与回滚浏览器流程；其余界面构建及相关服务测试 |

### Worker 与重复执行边界

- 任务领取、心跳、最终写入均校验任务 ID、worker_id、execution_attempt 和有效租约；取消在最终状态更新中原子处理。
- Search/Fetch 公共结果缓存 24 小时，跨管理员复用，Fetch 也按真实 URL+学科复用。创建候选和建设阶段使用稳定子任务标识。重试保留阶段与预算记录。
- 运行中取消是协作停止。已经发出的远程调用可能继续计费，不能作为退款或回滚承诺。
- 读操作与可恢复建设任务限次恢复；写索引的结果不明确时失败，禁止盲目自动重放。管理员显式重试仍受安全类型与三次上限约束。
- 文件锁改用操作系统 advisory lock；文件可常驻，进程死亡由内核释放。Windows 锁字节位于元数据之外，索引子进程可验证继承令牌。

### 知识可信与学生隔离

- AI 只生成候选；学科结构确认后仍为 PLANNED，不等于完整教材。综合草稿只能引用实际抓取的证据 URL，仍须人工判断内容和许可。
- 正式发布必须 APPROVED，并记录来源许可名称、许可证据链接与允许发布标记；修改已批准内容会使审核失效。
- 学生端仅在明确选择课程知识点时接入动态上下文，公开联网另行开启；发送的查询来自公共课程目录，不带画像、成绩或上传附件。
- 补充公开资料带 PENDING 标记，学生能查看来源和待审提示。既有默认自由问答、历史画像关闭语义保留。
- 覆盖状态区分 COMPLETE/PARTIAL/MISSING/STALE/UNCERTAIN/RETRIEVAL_FAILURE；检索故障不直接认定为知识不存在。覆盖完整度使用规则证据，不是专家质量认证。
- 更新版本标记引用旧版本的课件、练习待复核，不自动删除或重新生成学生成果。

## API 变化

### 新增与修改文件

- 公共层：`common/knowledge_paths.py`、`common/knowledge_lock.py`、`common/models/learning.py`、`common/schemas/agent.py`、`.env.example`。
- 知识服务：`services/agent_service/app/services/knowledge_{tasks,construction,acquisition,budget,maintenance,candidates,versions,base_admin}.py`，及原 `deepseek_search.py`、`knowledge_worker.py`。
- 管理与学生路由：`services/agent_service/app/api/routes/knowledge_*.py`、`assistant.py`，在原 `main.py` 注册。
- 学生调用链：`agents/coordinator.py`、`services/assistant_tasks.py`、`resource_generation.py`、`exercise_generation.py`、`qa_service.py`、`learning_path.py` 及相关请求模型，均在原 Agent 服务内修改。
- 语料/索引：`scripts/crawl_resources.py`、`scripts/index_resources.py`；迁移位于 `alembic/versions/20261019_0020_*` 至 `0025_*`。
- Vue：`web-app/src/views/AdminView.vue`、`components/AssistantPet.vue`、`views/student/QaView.vue`、`views/student/LearningPathView.vue`、`api/assistant.ts`。
- 验证：`scripts/verify_knowledge_v83.py`、`tests/e2e/run-knowledge-v83.mjs`、`tests/integration/test_knowledge_worker_recovery.py`、相关 `tests/unit/test_knowledge_*.py` 和 DeepSeek/助手/QA/路径测试。
- 交接：本文件及根目录 `DEV_STATE.md`。仓库另有大量既有改动，此表不将它们归为本轮新增。

所有下列管理接口均要求 admin；`/knowledge-base/context` 要求登录。

| 路径（均以 /knowledge-base 开头） | 能力 |
| --- | --- |
| POST/GET /tasks，GET /tasks/{id} | 任务创建、列表、状态 |
| POST /tasks/{id}/request-cancel、/retry；GET /tasks/{id}/usage | 协作取消、安全重试、调用及预算预留 |
| /construction/subject-plans，/subject-plans/{id}/confirm | AI 大纲及确认 |
| GET/POST /construction/subjects；GET/POST /construction/subjects/{id}/points | 复用学科、知识点目录及手工建设 |
| POST /construction/points/build | CREATE_POINT / COMPLETE_POINT / REVISE_POINT 批任务 |
| POST /context | 统一覆盖分析及 retrieval_context |
| /candidates 原接口，新增 /{id}/revision、/{id}/diff | 保留审核发布，增加修订草稿与差异 |
| GET /versions、/{id}/compare/{other_id}、/{id}/impact；POST /versions/{id}/rollback | 版本历史、差异、关联成果、恢复 |
| /maintenance-plans 原接口，GET /{id}/reports | 维护策略和历史报告 |

助手持久任务新增知识学科及公开补充偏好，幂等比较包含这些字段。QA 的知识库选项默认关闭，路径/资源/练习复用已有上下文结构。

## 数据库迁移

当前唯一 head：`20261019_0025`。

- 0020：知识任务 Worker 租约、心跳、代次、取消、退避。
- 0021：学科代码/别名/大纲，知识点章节/目标/先修/建设状态。
- 0022：维护策略与原子预算计数。
- 0023：有效版本、资源引用版本及待复核状态。
- 0024：来源许可和发布授权。
- 0025：父子任务预算关联及预留费用。

隔离空库到 0025、0025→0024→0025 均已执行通过。共享 SQLite 无可信 Alembic 基线，未执行升级；不得直接把这组空库迁移套用到共享库。先备份并审计历史基线，再单独安排上线。

## 真实执行证据

证据目录：`artifacts/knowledge-v83-20261019-082220/`。

- `report.json`：完整 API/Worker/模型/维护/学生证据；最后复跑 passed=true。
- `browser-report.json`：真实用户服务登录、候选编辑→送审→批准→Chroma 发布→恢复原版本，mocked=false，pageErrors=[]。本次发布版本 3 检索命中 1 条，恢复版本 1 检索命中 1 条；页面截图为 `browser-versions.png`。
- 实际 DeepSeek Search 获取 IETF BBR 来源，Fetch 保存 50,000 字符截断正文；正式原版有 108 个向量片段。重复验证复用已完成任务；API report 中 publication.retrieval_matches=0 是幂等重放，不作为新增检索证据，新增/恢复命中见 browser-report。
- 实际 DeepSeek 学科规划：输入 594、输出 303、合计 897 Token；确认 machine_learning 结构，状态 PLANNED。
- 实际单点综合草稿：抓取 scikit-learn 文档，DeepSeek 输入 5657、输出 515、合计 6172 Token，候选 2 待审核。先前部分搜索来源返回 404，保留失败任务；指定可信来源后成功，未伪造成无失败流程。
- 真实一次性维护任务 12 COMPLETED：扫描 1 点、复用候选 2、待审 1、发布 0，本次新增 Search/Fetch/模型调用均为 0。重复验收复用该历史任务，不代表最新分页字段执行过真实定时任务。
- 学生真实组合任务 1 SUCCEEDED：课件 resource_id=1、练习 1/2/3，公共知识上下文 ID 一致，learning_context_used=false。最终复跑复用该持久任务；新增来源提示另有单元测试，未重新付费生成同一任务。
- Worker 恢复集成测试实际终止独立进程、使租约失效、拒绝旧执行权、由新进程以 attempt=2 完成。

真实验收命令（会发起模型调用，已完成阶段优先复用）：

```powershell
python scripts/verify_knowledge_v83.py --live --port 8012 --plan --rollback --browser --build-point --maintenance --student --runtime artifacts/knowledge-v83-20261019-082220
```

原 8002（PID 81168）持续保留；验收使用 Agent 8012、用户 8013、资源 8014、系统 8015、Chroma 8016、Vite 5186。结束后上述隔离监听全部关闭。

## 自动化与构建

- `artifacts/v83-delivery-tests.log`：知识、助手、隐私、资源、Coordinator、QA、路径和真实 Worker 恢复组合回归 **141 passed / 1098 warnings**。
- 新增学生来源提示、维护 51 点分页后，`artifacts/v83-delivery-tail-tests.log`：**17 passed / 84 warnings**。与前组有重叠，不累加为总用例数。
- `web-app/build-v83-delivery.log`：`npm --prefix web-app run build` 成功（4.56 秒），包含 TypeScript 检查。
- `git diff --check` 无错误，仅既有 LF/CRLF 提示。
- 以上不是全站全部用例回归；PostgreSQL、Neo4j、生产部署未据此验收。

## 费用与维护注意事项

Search/Fetch/模型每次实际请求前原子预留 task/day/month 调用和 Token，子任务递归计入父维护预算。模型返回的 usage 单独保留，预留 Token 是上界，不是实际消耗。可配置每次调用及 Token 的微货币费率和金额上限；本环境未配置费率，cost.amount=null / PRICING_NOT_CONFIGURED，不能将计数 0 或预留金额 0 当作免费账单。

Worker 和定时索引修复需 Chroma HTTP 模式；嵌入式管理员重建在同一进程调用索引器，避免独立进程交替打开同一持久库。隔离实验出现 HNSW reader 错误后，改为独立 Chroma HTTP + ASCII 持久路径，多次重启与发布恢复通过。旧实验目录保留用于诊断，不能据此断言已排除所有存储故障。

重试前查看错误、已完成阶段、来源和预算；不要复制任务键绕过幂等。修改模型、费率、数据库、索引或运行目录后，应重启同一配置下的 API 与 Worker。

## 尚未完成或未验证

1. 来源“过时”目前按保存时间/配置阈值识别，并经补充抓取生成候选；尚无独立 ETag/Last-Modified 远端变更监控，不能声称已感知网页所有更新。
2. 自动发布仅允许明确授权域名/许可且与旧版去除空白后完全相同的格式调整；新增事实仍须人工审核。该自动发布分支未执行真实无人值守浏览器验收。
3. 文件/索引失败恢复与数据库版本更新有保护，但尚无跨 DB/Chroma 原子提交日志；进程在索引成功与 DB 提交之间崩溃仍需对账恢复演练。
4. 多知识点大批量的真实模型压力、QA/路径新增分支的真实模型浏览器流程、远端超时/预算耗尽的完整浏览器体验，尚未逐一实测；批量与权限逻辑已有自动化覆盖。
5. 当前来源综合和覆盖分析仍依赖规则与模型，未建立学科专家标注的质量评测集；保持人工审核。线上来源许可必须由业务管理员真实核验，测试授权不能沿用到共享生产库。
6. 共享数据库迁移、原服务进程加载新代码和正式发布未执行；此次交付为源码与隔离运行证据。
