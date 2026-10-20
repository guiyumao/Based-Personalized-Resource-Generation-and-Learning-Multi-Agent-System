# 当前开发状态

## 最新 学生端自主学科建设 P0-1 / P0-2：建设式门禁 + 个人学科草稿（2026-10-20）

按新任务（学生端自主学科建设/知识补全/计划全链路）落地 P0-1、P0-2：`SUBJECT_MISSING` 不再终止学生请求，缺失时自动构建**个人学科草稿**并据此生成计划。

- **P0-1 门禁**：新增 `plan_knowledge.assess_plan_knowledge`（返回 `mode`：public / personal_draft，缺失时不抛 409 但记录缺口）；`coordinator._execute_agents`、`generate_path`、`/paths/preflight`、`/paths/generate` 全部改为建设式；前端 `LearningPathView.checkKnowledge()` 对 personal_draft 继续生成（info 提示）。
- **P0-2 个人草稿**：新增 `knowledge_bootstrap.build_personal_draft`——按 `actor_user_id + subject` 在 `KnowledgeBuildTask(operation_type="PERSONAL_SUBJECT_DRAFT")` 中持久化 `SubjectOutline` + 检索 chunks；**不写公共 SystemSubject/KnowledgePoint**、不建平行库；同一学生复用（不重复生成）、跨学生隔离。LLM 出大纲走 `plan_subject`（schema 校验）且受 `RUN_LIVE_LLM=1 && DEEPSEEK_LIVE_PAID_ACK=1` 双闸门，未授权时用确定性草稿（标 `source=deterministic_fallback`）。
- **自动续接（P0-5 部分）**：`generate_path` 在 personal_draft 时先建/复用草稿，把草稿 chunks 作为 `retrieval_context` 喂给计划模型，同一请求内续接出稿；计划标 `knowledge_scope="personal_draft"`、`knowledge_draft`、`knowledge_draft_task_id`，**不冒充公共正式知识**。
- 证据：`test_plan_knowledge_p1.py` 10 passed（未知学科→personal_draft、不建公共学科、缺口=1）；新增 `test_knowledge_bootstrap.py` **3 passed**（个人且可复用、跨学生隔离、generate_path 用个人草稿 chunks 接地且无 subject_id/versions）；相关回归合计 **48 passed**；改动文件 Ruff 通过；前端 build 退出 0。
- **P0-4 个人草稿向量可检索**：`knowledge_bootstrap._index_personal_chunks` 把草稿 chunks upsert 到 Chroma（best-effort，metadata 带 `owner_user_id`/`scope=personal_draft`）；`rag._normalize_filters` 允许 `owner_user_id/scope`；新增 `ChromaRetriever.retrieve_personal(user_id, …)` 仅按 owner+scope 检索；`knowledge_publication.visible_chunks` **fail-closed 丢弃 `scope=personal_draft`**，公共检索永不泄露个人草稿。
- 证据：`test_knowledge_bootstrap.py` 5 passed（+visible_chunks 丢弃个人草稿、retrieve_personal 只按 owner+scope）；knowledge/rag/publication 相关 89 passed；改动文件 Ruff 通过。
- **P0-3 搜索抓取与候选（已真实跑通）**：`_search_and_fetch_personal`——受双闸门（`RUN_LIVE_LLM=1 && DEEPSEEK_LIVE_PAID_ACK=1`）控制，用 `search_sources(query, need_content=True)` 取回真实来源正文（**发现 `/v1/tools/fetch` 在 DeepSeek 公开 API 上 404 不存在，改用 search 内联 `content` 替代**），落 `KnowledgeCandidate(status=DRAFT, subject=personal_<hash>)`；`deepseek_search` 新增 `DEEPSEEK_SEARCH_ALLOW_FAKE_IP=1` 显式放宽 SSRF（本机 fake-IP DNS）。真实证据：搜到清华《数据结构》第3章，正文 6528 字，候选 #1 DRAFT，草稿 37 chunks（含 1 条真实正文）。
- 证据：`test_knowledge_bootstrap.py` **9 passed**（+SSRF 开关、未授权不调用、授权时用内联正文建候选）；相关回归 **106 passed**；改动文件 Ruff 通过；前端 build 退出 0。
- **P0-1/P0-2/P0-3/P0-4（核心）已完成并验证**；剩余：P0-7 前端真实进度面板（当前同步生成）、P0-8 A–G 全链 E2E。真实 Search 调用需设 `RUN_LIVE_LLM=1`+`DEEPSEEK_LIVE_PAID_ACK=1`+`DEEPSEEK_SEARCH_ALLOW_FAKE_IP=1` 并重启 8002；默认不调用。运行中 8002 仍是 21:12 构建（P0-3 需再重启加载）。不冒充场景 A 已全链通过。

## 最新 AI 内容编排真实可用性修复（2026-10-20；提示词/Provider/改写接口已 LIVE_VERIFIED）

本轮定位并修复管理员端截图中的"提示词列表获取失败 / Provider 状态失败 / AI 改写失败 / 章节配图只有读取入口"：

- **根因**：agent_service 8002 仍跑 P1-07 之前的旧代码，前端 5175 已热加载新导航但后端 `/admin/prompts`、`/admin/image-provider`、`/admin/resources/{id}/rewrite|sections|illustrations` 全部 404。已按 `artifacts/local-start-20261019/start.ps1` 同款 runtime.sqlite + env 重启 8002（`--lifespan off`），openapi 现含全部 admin 路由；真实 HTTP 验证 prompts=200/11 模板、image-provider=blocked、sections=9 节、rewrite=blocked(未授权)、illustrations=blocked(未配置)。
- **提示词统一加载**：`resource_generation/exercise_generation/feedback_synthesis` 三处 `_load_prompt_template` 的 lru_cache 改为 `prompt_registry.load_prompt_template`（按文件 mtime 失效），管理员编辑后新生成无需重启即生效。
- **提示词版本生命周期**：`prompt_registry` 新增 `.history/` 文件式快照 + `list_prompt_versions/read_prompt_version/restore_prompt`；新增路由 `/admin/prompts/{name}/versions[/{version}][/restore]` + 前端 prompts.vue 版本列表/恢复 UI；`.history/` 已加入 .gitignore。
- **图片 Provider 状态细分**：`image_provider_status` 增加 `enabled/health` 与 `blocked/invalid/disabled/configured` 四态；`PUT /admin/image-provider` 支持 `enabled`；前端类型/展示同步。
- **AI 改写付费闸门**：`rewrite_resource` 增加 `RUN_LIVE_LLM=1` 且 `DEEPSEEK_LIVE_PAID_ACK=1` 双闸门，未授权返回 blocked"需要授权"，杜绝后台误触发付费调用（此前会因 runtime.sqlite 缺 `model_calls` 表在 begin_call 处崩溃）。

验证：相关单测 53 passed（test_prompt_admin/test_resource_editor/test_learning_prompt_templates/test_plan_feedback/test_resource_generation/test_structured_resource_generation）；改动 Python 文件 Ruff 通过；前端 `npm run build` 退出 0。真实付费调用 0。未提交、未迁移共享库、未重启 8001/8003–8007/5175。

下一步/阻塞：runtime.sqlite 缺 P1-06 台账表（`model_calls` 等 0030/0031 五表），授权后改写与真实生成需先补齐（共享 SQLite 无可信 Alembic 基线，须先基线审计再定向补表，禁止空库迁移）；孤儿模板 coordinator/knowledge_graph/learner_profile/path_planning/qa 无生成消费方，需接线或移出白名单；图片生成后端接入仍属 P1-08。详见 ADMIN_FUNCTION_FUSION_MATRIX.md 本轮注记。

### 续：补齐台账表 + 打通真实改写调用（用户授权后）

- **补齐 12 张缺失表**：runtime.sqlite 经 ORM 对照缺 0026–0031 的 `model_calls/worker_instances/task_attempts/resource_revisions/resource_artifacts/study_sessions/study_activities/learning_contexts/context_exercises/learning_knowledge_gaps/knowledge_documents/knowledge_document_points` 共 12 表。已用 `Base.metadata.create_all`（幂等，只建缺失表）补齐，改前用 sqlite3 backup API 备份至 `artifacts/local-start-20261019/runtime-before-tables-20261020-200640.sqlite`。
- **打通真实 AI 改写**：8002 以 `RUN_LIVE_LLM=1`+`DEEPSEEK_LIVE_PAID_ACK=1` 重启后，`POST /admin/resources/220/rewrite` 真实调用 deepseek-chat 返回 `status=generated`（改写 2810 字符），台账 `model_calls` 记录 LIVE/SUCCEEDED/KNOWN，input 1597 / output 1535 tokens。`PUT /admin/resources/{id}/content` 应用改写成功，`resource_revisions` 写入旧版本快照（resource 220 已用快照回滚还原，无残留）。用户已授权本轮真实调用预算。
- **剩余真实调用缺口**：章节配图/图片生成后端未接入（无图片 Provider 凭据），需用户提供 `IMAGE_PROVIDER_API_KEY/BASE_URL/MODEL` 才能接真实图片生成；否则保持 blocked 安全态。授权环境变量需在重启 8002 时一并注入，否则改写回到 blocked。

### 续2：清理 5 个孤儿提示词模板

`coordinator/knowledge_graph/learner_profile/path_planning/qa` 五个模板无任何加载方（coordinator/qa_service 仍硬编码 inline prompt；PPT slide10 的「加载 prompts/*.md」是设计稿而非实现），已从 `prompt_registry.ALLOWED_PROMPTS` 移除，管理端「提示词模板维护」现只显示 6 个真实被生成链消费的模板（resource_gen/exercise_gen/evaluation_feedback/mind_map_gen/code_case_gen/video_script_gen）。文件保留在 `prompts/` 未删除；接线统一（把 inline prompt 迁到模板加载）是 61KB coordinator 的独立重构，记为后续任务而非隐藏。单测 25 passed、Ruff 通过；8002 已重启加载新白名单，`GET /admin/prompts` 现返回 6 条。

## 最新 学习计划反馈闭环 + 两个 API 错误修复（2026-10-20；总体仍PARTIAL）

本轮完成“计划生成→预览→自然语言反馈→AI调整→差异预览→确认”的计划制定反馈闭环，并定位两个 API 错误根因。

- 两个 API 错误根因：运行中 8002 agent/8004 evaluation 是旧进程（10-19 23:43 启动，早于路由提交），且共享 `learning_system.db` 无 Alembic 基线、缺 0026/0028/0029 表。源码路由均在，隔离“最新代码+`upgrade head`(0031)”验证 `learning/contexts/*`、`overview/me` 由 404→401 且 openapi 可见。**未迁移共享库/未重启共享进程**（无基线，禁止直接 upgrade）；上线需一次性基线审计+备份+定向补表（沿用 runtime.sqlite 副本补列模式）。
- 新增 `plan_feedback.py`（PlanFeedbackService + compute_plan_diff）、`task_feedback.py`（TaskFeedbackService，8 类任务级执行反馈，确定性改稿无需 LLM）；路由 `POST /paths/feedback/preview`、`POST /paths/feedback/{id}/confirm`、`POST /paths/task-feedback/preview`；复用 path_revision CAS + applied_feedback 幂等，确认保留已完成任务、删除已完成任务记入 removed_completed_history，无凭据 503、真无变化 no_change。
- 前端 `PlanFeedbackPanel.vue`（计划级）+ `TaskFeedbackButton.vue`（每任务反馈弹层）接入 `LearningPathView.vue`。
- 证据：test_plan_feedback.py 7 + test_task_feedback.py 7 + test_path_adaptation 5 = **19 passed**、Ruff 通过、前端 build 退出0。真实付费 DeepSeek 0。报告 `docs/aura-full-integration/13-plan-feedback-loop.md`。
- 共享环境现状（20:22 复核，**两个 API 错误均已解除**）：8002 由同期 P1-07 会话重启、8004 evaluation 由本会话重启（均 runtime.sqlite+`--lifespan off`），`learning/contexts/*` 与 `/evaluation/overview/me` openapi 可见、均 404→401；端到端真实断言注册 api-verify 用户 → `/evaluation/overview/me` Bearer 返回 HTTP 200 真实数据（active_plans=[]/due_cards=0/study_seconds=0）。剩余：真实 LLM 修订验收、任务级反馈浏览器 E2E、进度/画像全链 A–E。工作树另含 P1-07 未提交改动（非本任务）。

## 最新P1-07 管理员Prompt优化/改写/图文编排（2026-10-20；总体仍PARTIAL）

本轮实现 P1-07 管理员专用 AI 内容编排子链：
- 管理员 Prompt 优化：新增 `prompt_registry.py`（白名单 list/read/update + 占位符保留校验，路径永不出白名单）与 `/admin/prompts` 路由；前端 `prompts.vue` 提示词编辑页 + `adminNavigation` 新增“提示词与图文配置”入口。
- 改写：`POST /admin/resources/{id}/rewrite` 调用已配置文本模型（无凭据返回 `blocked`，不伪造改写；真实调用走 P1-06 台账）；`PUT /admin/resources/{id}/content` 应用改写并保留 ResourceRevision 快照 + 审计日志；资源管理页新增改写/应用 UI。
- 图文编排/图片 Provider：`GET/PUT /admin/image-provider` 读取/保存非敏感 provider 名称+模型；`GET /admin/resources/{id}/sections` 列章节；`POST /admin/resources/{id}/illustrations` 在无图片凭据时返回明确 `blocked`（凭据由部署环境 `IMAGE_PROVIDER_API_KEY` 管理，管理界面不回显）。`common/config.py` 新增 `image_provider_api_key/base_url/model`，`.env.example` 记录。

验证：`tests/unit/test_prompt_admin.py` + `test_resource_editor.py` 共 15 passed；新增/改动 Python 文件 Ruff 通过；前端 `npm run build` 退出 0（tsc+vite 6.68s，仅保留既有第三方 INVALID_ANNOTATION/分块提示）。未做真实 LLM 改写（无付费授权，blocked 路径用桩 LLMFactory 验证）；未接入真实图片生成后端；未重启 8001–8007/5175、未迁移共享库、未自动提交、真实付费调用 0。

恢复入口：改写真实模型链待新一轮付费授权后验收；图片生成后端接入属 P1-08 外部图片适配；P1-07 剩余（草稿审核编排完整闭环）与 P1-08/P1-09/P1-10 继续。以下为更早检查点。

## 最新运营/多模态接续（2026-10-20；总体仍PARTIAL）

本次在原多服务完成ModelCall真实逐调用持久台账/调用与输出预留预算、WorkerInstance独立空闲心跳、TaskAttempt执行尝试；管理员可读LIVE/TEST分离用量、分布、明细、心跳和历史尝试。新增0030→0031五表；LearningContext绑定的PPTX下载重读、SVG动画实际播放、本机Windows Speech WAV存储播放、导图CAS编辑与前后版本历史已接入原AssistantTask/Worker。修复画像聊天/新知识点习题在模型调用期间持有SQLite写锁导致台账互锁。完整文件表与剩余范围先读 docs/aura-full-integration/12-operations-media-acceptance.md。

证据 artifacts/aura-ops-20261020：global-unit-v2为592 passed /2133 warnings；build-final.log退出0、2.89秒；browser-final九组通过/pageErrors空，真实PPTX/SVG/WAV/导图/权限/管理员，生成问答受控桩；独立Worker空闲心跳推进+强制退出后超时；migration-final空库至0031、0031→0028→0027→0031保留原用户笔记，migration-v1另验证0029↔0031；12个新增Python业务/迁移/只读审计文件Ruff通过。

本轮用户明确授权Chat≤6、输出≤6000；实际4 Chat HTTP200、输入5177/输出3432，输出预留6000已用满，停止付费调用。第2次习题截断记失败，重试第3次真实三题无fallback；课件/上下文QA/服务端评分与画像隔离入库通过；供应商金额UNKNOWN，Search/Fetch/外部图片/外部TTS均0。真实模型证据 live-authorized-v2/v3 属同一累计授权，不重置计数。QA测试依赖覆盖导致该条台账用户归属为空，正常JWT归属另测，未扩大为完整付费Worker复合链。

共享库已只读审计：无Alembic版本记录，缺13表及9张旧表字段，详情 shared-schema-readonly.json；不能直接stamp或假设0029基线。遵守任务原限制，未升级共享SQLite、重启8001–8007/5175或自动提交。P1-07管理员Prompt优化/改写/图文编排、P1-08真实视频URL验证/外部图片适配、P1-09笔记历史/闪卡知识点画像、P1-10全部18项及A–E全局验收仍需继续；不要再把台账/空闲心跳/PPTX/SVG/WAV/导图误记为未实现。以下为较早检查点历史。

## 最新AURA P1接续（2026-10-20；总体PARTIAL）

本轮在原多服务中完成图谱核心权限/公私内容/读取零模型修复；新增LearningContext、ContextExercise、LearningKnowledgeGap及0028/0029；三栏文本/习题工作区打通真实资源引用问答、版本笔记、持久助手任务、作答/画像/任务证据同事务回写。计划生成校验正式学科/知识点/有效发布文件和当前Chroma片段，生成后及确认草案时复核；知识缺口进入管理员原建设队列。复用0027文档专项，实际再次跑通独立Worker/Chroma HTTP/浏览器发布修订回滚撤回及硬退出恢复，新增计划准入READY实证。管理员增加真实持久任务统计/执行阶段/预算预留面板；实际Token台账与空闲Worker在线状态仍UNKNOWN。

交接先读 docs/aura-full-integration/11-p1-learning-context-checkpoint.md、09及根目录GRAPH_SECURITY_FIX_REPORT.md。证据 artifacts/aura-p1-20261020：regression-final为167 passed /1432 warnings；planning-final 62 passed、graph-final-v2 40 passed为有重叠定向证据；migration-v1空库head0029及0029→0028→0027→0029保留旧用户/笔记；documents-real-v1真实文档发布和Chroma/Worker子链通过。browser-v6七组检查通过且pageErrors为空，真实DB读回1笔记/3绑定题/1作答/1成功任务；build-final.log退出0，3.94秒。截图已实际查看；生成与QA受控桩清楚标识，付费调用0。新增16个Python文件Ruff通过，未声明整仓lint通过。

下一步P1-06：common/performance.py的record_model_response及llm_factory.py→逐调用持久账本，区分真实/未知/估算/测试；补Worker独立心跳/完整尝试事件和统一脱敏日志。随后P1-07原Coordinator/AssistantTask+Resource草稿审核编排；P1-08多模态产物/播放器/版本历史；P1-09笔记编辑历史/分类、闪卡知识点画像；P1-10全局原子验收。历史图谱逐边来源/真实Neo4j、PG、公网均未完成。没有升级共享SQLite、修改共享Alembic版本、重启8001–8007/5175或自动提交；其他任务的0027文档和同期改动完整保留。

更新：2026-10-20（Asia/Shanghai）。main，最近核对 HEAD 05ee287。工作树含大量既有及其他任务改动，禁止重置、清理或整体覆盖。

## 当前目标与进度

AURA-MAS全功能融合首批P0检查点（2026-10-20）：重新克隆并核验上游5923cf6；新增首页真实overview、服务端CAS活动区间/北京时间日周汇总，修正LearningPath JSON与LearningTask及阶段/任务完成率口径不一致。新增学情驱动提案预览→本人确认→追加后续补强任务，JSON revision拒绝过期写，确认ID重放不重复。新增0026的StudySession/StudyActivity两表；同期独立0027知识文档变更保留、未计本轮成果。相关后端91 passed，最终build退出0；隔离Chromium10项业务、真实约15秒活动入库、0026↔0025再至当时head0027通过。证据 `artifacts/aura-full-integration-20261020/{unit-v4,browser-v4,migration-v3}`，报告 `docs/aura-full-integration/01-09`。**全功能尚未完成**；全仓库原子审计、三栏上下文、知识覆盖门禁、导图编辑/视频/动画/TTS/PPT、完整画像推荐、管理监控及A–E全链仍待开发验收。图谱匿名/私有资源/成本边界已定位但未修。下一步见04/07；勿重复全审。共享运行库/8001–8007未迁移重启，新接口在旧进程未激活，付费调用0；先核对当前Git和同期文档改动再推进。

管理员导航本轮完成：6 分组 / 11 实际页面，原 `/admin` 保留统计看板。统一 `adminNavigation.ts` 关联菜单、路由、搜索和标题；原 AdminView 业务移到 `useAdminWorkspace.ts` 与 `views/admin/`，按模块加载。包含分组展开、折叠、路由恢复、移动抽屉、键盘焦点。管理员路由通过 `/users/me` 复核；新增管理员资源目录并修复管理员私有资源预览，敏感配置 PUT 拒绝回显。详见 `docs/admin-navigation-refactor.md`；未添加没有真实后台的模型配置/Worker监控/角色权限编辑入口。

沿用真实 FastAPI 多服务 + Vue 3/Vite，继续小智学习闭环；不按提示词假设改建 Spring Boot。统一头像、SSE、会话、记忆、持久任务、Worker、资源正文/DOCX、练习和计划确认已接入原服务。

附件可用于问答、课件和练习；执行时校验归属，删除后的排队附件明确失败。复合任务仅生成所请求的成果。默认禁用历史画像，明确请求本人学情或设置启用才读取；禁用时跳过画像服务，评分返回 null。

评价提交补认证、题目归属及服务端答案权威；教师读报告限定本人班级。练习请求标识随进度持久化，原 AnswerRecord JSON 保存回执；同键重放不重复计分、更新画像或发事件，改答案返回 409，新标识允许重练。未新增幂等表。

## 最近验证

- 管理员导航（2026-10-20）：最终 `npm run build` 退出0（Vite 5.89秒）；隔离相关后端80 passed / 221 warnings；Chromium真实路由+SQLite 11菜单、44页面宽度检查、40角色接口断言、21流程通过，正常 pageErrors/apiErrors均空；503故障注入安全拒绝通过。含用户搜索分页启停、角色分配、学科/知识点保存、资源发布归档、候选送审批准、维护暂停、任务取消及用量。证据 `artifacts/admin-navigation-20261020/{unit-verified,browser-verified,activation}`，五类截图已实际查看。未重跑真实模型、真实Chroma发布回滚或全站回归；未执行真实业务数据写测试。

- DeepSeek V3 安全完善及用户后续真实授权（2026-10-19）：新增默认pytest隔离/专用无费用运行器，禁dotenv及第三方dotenv、真实凭证继承、非声明本机HTTP/Socket与缺guard子进程；新增Provider故障、预算网关、浏览器工具。最终相关回归169 passed，Ruff定向检查通过。六服务+Worker+Chromium本地模拟QA/课件/DOCX/成绩单闭环通过。随后用户明确授权Chat≤30、Search/Fetch≤6、输出≤60000：实际5 Chat+1 Search全HTTP200，输出3506 Token；真实课件3619字符、3题无fallback、Worker持久化/重放、DOCX、浏览器QA刷新读回及课件列表通过。请求deepseek-chat、响应deepseek-flash，经本地受控记录网关；金额未知。Fetch安全校验阻断、无出站；INC-01账单未关闭。证据 `reports/global-testing/deepseek-phase-v3-20261019/DEEPSEEK_V3_GLOBAL_SUMMARY.md` 及 `artifacts/deepseek-authorized-20261019-v1/`。生产图谱权限/成本、历史迁移及fallback语义仍按附件限制仅准备补丁，未修改共享库或既有服务。

- 无费用全局审计续跑（2026-10-19）：证据 `artifacts/global-audit-resume-20261019/GLOBAL_TEST_SUMMARY.md`。隔离 pytest 184 次通过（去重178节点，含风险复现探针），六服务9接口×8身份72项真实HTTP断言通过；Knowledge Worker真实进程终止/接管在12项组合内通过，原图谱23项测试本轮均通过。动态证实匿名依赖/可视化触发模型边界、匿名关联资源暴露个人草稿标题；0009降级错误删除0002列为全量回滚根因。四份待审补丁仅保存在产物目录，迁移副本head→base→head及6项定向补丁断言通过，未修改业务源码或共享库。进程网络审计钩子阻断非loopback连接，真实模型调用0。原执行卡死原因未确认，旧pip-audit结果已找到且白名单检查失败。公网部署No-Go；PG/真实Chroma/浏览器全站/全接口权限等仍有缺口。

- DeepSeek 无费用核对（2026-10-19）：修正 live 计划/Prompt 中不存在的全局超时/重试配置名、1 秒超时误判、强制模型输出非 JSON、取消“远端停止/必须捕获 CANCEL_REQUESTED”等错误口径；新增本地 HTTP 桩失败语义、计数代理、文档契约测试。无费用回归 33+50+77 passed。**发生 INC-01 未授权真实调用**：为验证闸门执行 live 套件时 PowerShell 空赋值删除了密钥变量，`.env` 真实密钥被加载，至少 4 次结构化生成成功；usage/金额未知，需核对账单/必要时轮换密钥。已加 `DEEPSEEK_LIVE_PAID_ACK` 第二道闸门。Search/Fetch 仍 BLOCKED（无授权；本机 DNS 为 198.18.x fake-IP，Fetch 过不了 SSRF 公网校验）。证据 `artifacts/deepseek-live-20261019-173354/`，源码核对 `docs/testing/deepseek-live-source-audit.md`。练习模型失败会走 `deterministic_fallback` 且仍报 audit passed，live 验收必须排除。
- V8.3 本轮：学科规划/确认、单点和批量建设、统一知识上下文、维护策略/预算、版本差异/恢复/影响及 Vue 管理入口已接入。隔离组合回归 141 passed；追加来源提示/51点分页回归 17 passed（有重叠）；前端 build 4.56秒通过。真实 DeepSeek 规划与综合草稿、Chroma HTTP 浏览器发布/回滚各检索命中1条、一次性维护和学生课件+3题持久任务通过。唯一 head 0025，空库升级和0025↔0024已验证；未迁移共享SQLite。证据见 docs/knowledge-v8-progress.md 与 artifacts/knowledge-v83-20261019-082220/report.json。
- 小智任务可靠性本轮：隔离库组合回归 113 passed；最终执行权补丁后任务单元+独立进程回归 45 passed（43+2），覆盖真实终止 Worker 恢复、过期续租拒绝、无轮询超时、题组 flush 冲突和模型返回时取消。前端 build 退出码 0；空库到0017、0017↔0016、先 bootstrap 后迁移均通过。共享 fixture 首次并行建表冲突后改用独立 DATABASE_URL；未修改共享 Alembic 版本，未重跑真实 DeepSeek 浏览器链路。详见 `docs/assistant-task-reliability.md`。
- 相关后端回归 116 passed / 479 warnings；前端 build 退出码 0。
- 隔离库真实 DeepSeek + 独立 Worker 浏览器任务 22：附件→课件/3题/计划草案→正文及 DOCX→评分重放/冲突→1条作答及画像读回→确认计划，退出码 0。DOCX 可解析为65段、2846字符。证据及命令见 docs/xiaozhi-assistant-upgrade.md。
- 首次重跑因测试评价服务漏配 CORS 失败；补5185来源、验证 OPTIONS 200 后完整重跑通过。本轮隔离端口8008/8009/8010/8011/5185及Worker已关闭；原8001/8002保留。

## 下一步与风险

本地增量更新（2026-10-20）：仅刷新8003 resource=52928、8006 system=94792；原运行SQLite保持，使用 `--lifespan off` 避免此次重启触发schema bootstrap。两服务health、六服务健康、管理资源路由OpenAPI/匿名401及5175 CORS通过；其余服务/Worker未停止，前端5175热加载新导航。最新PID证据 `artifacts/admin-navigation-20261020/activation/processes.json`，旧 `local-start-20261019/processes.json` 两项PID已过期。以后正常重启仍遵守既有数据库基线策略。

本地运行（2026-10-19 23:44）：前端5175、六服务8001–8006、QA兼容8007及合并Assistant/Knowledge Worker已启动，健康检查通过。旧进程已由本轮启动替换，当前接口含V8建设与request-cancel。运行数据库为`artifacts/local-start-20261019/runtime.sqlite`：从原库安全备份复制并在副本补齐26个ORM缺列，保留原账户/数据，未执行共享库Alembic迁移；本次运行产生的新数据写该副本。原库备份、PID、日志与启动脚本同目录。后台图谱自动模型补全在本轮进程关闭，显式学习任务正常使用现有模型配置。

V8.3 当前可在隔离环境运行知识建设闭环，原8002 PID81168未重启，隔离8012–8016/5186已关闭。下一步：共享库基线审计与上线、远端来源更新监测、跨DB/Chroma提交间崩溃恢复演练、多点模型压力与QA/路径浏览器验收。过时检测当前按保存时间；自动发布仅授权来源的纯格式变化，未实测无人值守分支；费用未配置费率，金额未知。完整边界以V8进度文档为准。

INC-01 后需核对 DeepSeek 账单并决定是否轮换测试密钥；后续真实调用必须同时满足 `RUN_LIVE_LLM=1` 与 `DEEPSEEK_LIVE_PAID_ACK=1`，且 PowerShell 不要用空赋值清空密钥（会删除变量并使 `.env` 生效）。

小智运行中取消改为 `/request-cancel` 协作式停止；原 `/cancel` 的 RUNNING 409 语义保留。课件与练习以原任务 ID 和阶段为稳定键并加唯一约束；心跳自行检查期限，执行代次和租约限制写入/最终结果，只读任务限次退避恢复，生成类超时不自动重放。同步请求不能强行中止；卡死线程收回执行权后需另一 Worker 或重启承接安全任务。详见 `docs/assistant-task-reliability.md`。仍需全站回归和真实模型/浏览器复验；图片OCR、PDF/PPTX、Word原生排版、Neo4j联调未完成。旧题所有者未回填；评价事件无持久Outbox。共享SQLite无可信Alembic基线，禁止直接执行空库迁移。保留临时测试库，勿尝试绕过先前自动安全审查的删除拒绝。

## AURA全局融合本轮中断交接（2026-10-20）
已建立根目录 ADMIN_FUNCTION_FUSION_MATRIX.md；核验 artifacts/aura-full-integration-20261020/reference 上游5923cf6。新增 KnowledgeDocument/KnowledgeDocumentPoint、迁移0027，knowledge_documents服务与admin路由（目录、全文、上传PDF/DOCX/MD/TXT、原件、Chunk、批量分类、学科preflight/coverage、转原候选审核、未送审上传归档）。前端 KnowledgeDocumentManager接入knowledge.vue，subjects.vue新增检查和显式关联。上传原件位于独立originals，未审核不进入corpus；沿用现有候选/版本发布。
本次隔离回归55 passed/197 warnings，证据 artifacts/aura-full-integration-20261020/documents-unit-v3/command.log；空库head0027及0027→0026→0027回滚、账户保留通过，documents-migration-v1/migration-result.json。新增Python文件Ruff通过；第一次前端build通过，但随后subjects.vue及审核路由修正后尚未重构建。首次测试失败是Windows原件CRLF与测试LF比较，已改为原件字节对比通过，失败日志保留。
用户中断；尚未浏览器验收/真实Chroma检索验证；未重启共享服务、未迁移共享库或产生付费调用。下一步先复查改动、最终build及隔离浏览器，再完善上传审核发布索引跨链路（重点校验version corpus_path去前缀/去重、覆盖率），然后AI补充资源/全量Token账本/预算/日志Worker统一监控。全局融合仍PARTIAL；15份最终报告尚未生成，不得宣称全量完成。原8002进程未加载新路由，新前端访问共享服务的文档功能需要隔离运行或后续审计上线。

## AURA文档发布专项续接验收（2026-10-20）
文档核心链已TESTED_ISOLATED：上传PDF/解析/分类/知识点关联/审核/独立Worker发布/真实Chroma学生检索；修订替换、并发同键、回滚、原件字节与角色权限、记录/上传归档通过。新增knowledge_publication读取门禁与对账，PUBLISH_CANDIDATE/RECONCILE_PUBLICATIONS复用原Worker；硬退出后孤立片段不可读、attempt2恢复仅1版本；撤回立即拦截缓存，后台清理。课件真实知识上下文及版本引用持久化通过，生成仅LOCAL_STUB_ONLY。关联RAG单篇详情、重用上下文和知识覆盖扫描也过滤未生效candidate。SQL flush/提交及执行权丢失补偿有回归。
最终相关106 passed/396 warnings（resume-final-unit-v2），完整Vue build退出0；documents-browser-v9两个result均true；migration-resume-v2空库至当前head0029，0009→0008保留0002列、0027→0026往返/账号保留通过。定向新文件Ruff及关联模块F级检查通过。全部证据artifacts/aura-full-integration-20261020；汇总docs/aura-full-integration/10-knowledge-publication-acceptance.md，04/07/08/09与根矩阵已追加更新。
保留同期0028/0029及图谱/学习上下文改动；图谱当前安全/性能测试纳入本次回归，真实Neo4j与历史来源清理未验收。共享8001–8007/5175未重启/迁移；隔离18207/18208/15188已关闭，无付费调用。总体PARTIAL：下一步继续AI补充资源编辑/优化/多模态、统一真实Token账本/后端预算/全Worker监控及学生余项；preflight实时Chroma匹配、大文件异步解析/OCR/原生DOCX预览/已发布资料批量归档/永久安全删除仍未完成。先读10和现有07，不重新全仓扫描；激活共享库前需基线/备份及同期迁移审计。
