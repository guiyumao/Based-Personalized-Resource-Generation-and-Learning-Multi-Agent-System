# P1 学习上下文与管理员任务接续检查点

2026-10-20。总体 **PARTIAL，未部署共享环境**。继续使用上游固定本地副本5923cf6cd766a58b112f24f02371bb87da1fa904，不重复克隆或切换。以下只说明实际源码及隔离验证，不把24个能力组当作原子功能总数。

## 工作包状态

| 包 | 实际交付 | 当前状态与剩余事项 |
|---|---|---|
| P1-01 | 图谱认证、公私数据分离、版本缓存、读取零模型、管理员受控建设 | 核心边界TESTED_ISOLATED；历史关系逐边来源、Neo4j与个人掌握度仍待补，详见根目录GRAPH_SECURITY_FIX_REPORT.md |
| P1-02 | 持久LearningContext + ContextExercise；计划/模块/任务/知识点/资源版本校验；QA会话隔离、Worker写屏障、笔记来源、评分同事务回写 | TESTED_ISOLATED子闭环；尚无覆盖所有资源类型的统一版本历史 |
| P1-03 | 三栏工作区、真实任务目录、资源选择/刷新恢复、资源问答、来源笔记、持久任务生成练习、评分证据读回、窄屏折叠 | TESTED_ISOLATED文本/习题子闭环；导图仅展示已有节点，视频/动画/TTS/PPT专用播放器和交互未完成 |
| P1-04 | 学科/知识点/正式发布文件/当前Chroma版本准入；缺口持久化；管理员转原建设队列；生成后与确认时重新核验版本 | 正式发布→真实Chroma→准入READY已验；计划生成/练习模型为受控桩，真实Provider未授权；完整多知识点规划与全部调整策略待补 |
| P1-05 | 复用0027及文档专项，未重建文档存储 | 本轮再次跑通真实文档/Worker/Chroma/浏览器及计划准入；既有专项边界见10；扫描件OCR、Word原生排版及更多格式仍未完成 |
| P1-06 | 管理员持久任务汇总、状态/日分布、执行代次、任务租约心跳、已存智能体阶段、知识预算预留 | PARTIAL；逐调用真实Token台账、模型/用户用量趋势、完整重试事件、空闲Worker心跳注册及统一日志检索未完成；UNKNOWN不计0 |
| P1-07 | 未新增AI补充资源编排 | NOT_IMPLEMENTED，本轮不能计入验收 |
| P1-08 | 文本课件/习题可绑定上下文，其他类型显示当前预览限制 | PARTIAL；多模态生成→播放→持久化完整链未完成 |
| P1-09 | 笔记资源版本/上下文/定位字段；真实评分更新画像并写任务证据 | PARTIAL；笔记版本历史、分类筛选、闪卡知识点掌握度与统一画像仍待补 |
| P1-10 | 定向回归、迁移、两套隔离浏览器及真实Chroma子链 | PARTIAL；全站/全部原子功能/真实模型/PG/公网未验收 |

## 代码文件与职责

| 文件（仓库内） | 本轮作用 |
|---|---|
| common/models/learning.py | 新LearningContext、ContextExercise、LearningKnowledgeGap；StudyNote来源字段；保留同期模型修改 |
| common/resource_version.py | 课件内容/结构/归属/审核发布状态的稳定版本摘要 |
| common/learning_context.py | 权威绑定校验、持久快照、候选筛选、生成题归属绑定、作答证据CAS |
| common/schemas/agent.py | 图谱有界请求、私有资源版本字段 |
| alembic/versions/20261020_0028_learning_context.py | 上下文/题绑定及笔记字段的增量迁移 |
| alembic/versions/20261020_0029_learning_gaps.py | 学习覆盖缺口独立表，依赖0028；0028依赖原0027 |
| services/agent_service/app/api/routes/graph.py | 认证读取、个人快照及管理员建设入口 |
| services/agent_service/app/connectors/neo4j_connector.py | 公共来源过滤、公共摘要缓存、取消隐式模型、隔离未分类历史节点 |
| services/agent_service/app/services/graph_access.py | 本人/管理员显式私有资源快照 |
| services/agent_service/app/api/routes/learning_contexts.py | 创建、本人目录及读取上下文 |
| services/agent_service/app/api/routes/learning_gaps.py | 管理员缺口列表及转建设队列 |
| services/agent_service/app/services/plan_knowledge.py | 正式知识与当前片段准入、缺口记录及解决状态 |
| services/agent_service/app/api/routes/learning.py | 前置检查及计划生成门禁 |
| services/agent_service/app/agents/coordinator.py | 计划执行前准入；未显式学科时从唯一正式知识点解析 |
| services/agent_service/app/services/learning_path.py | 可信片段进入Prompt、任务知识点ID/版本引用、生成后及草案确认时复核 |
| services/agent_service/app/api/routes/assistant.py | 服务端资源引用、会话隔离、上下文任务参数、确认冲突409 |
| services/agent_service/app/services/assistant_tasks.py | 持久任务携带绑定、生成课件子上下文、生成题组关系；不让弱项替换当前主题 |
| services/agent_service/app/services/assistant_execution.py | 模型返回后写入前同事务复核上下文及执行权 |
| services/agent_service/app/services/chat_service.py | 同步/流式问答执行前与最终落库前复核绑定 |
| services/user_service/app/api/routes/study_tools.py | 笔记来源/version/locator保存；修改历史笔记不改来源 |
| services/evaluation_service/app/schemas/report.py | 可选learning_context_id，保持旧请求兼容 |
| services/evaluation_service/app/services/report_service.py | 题绑定校验，回执/作答/画像/任务证据同事务保存 |
| services/evaluation_service/app/api/routes/reports.py | 保留上下文HTTP错误状态 |
| services/agent_service/app/api/routes/operations.py | 管理员任务汇总/阶段/预算读取，排除Prompt及任意异常文本 |
| services/agent_service/app/main.py | 注册新增路由 |
| web-app/src/views/student/LearningWorkspaceView.vue | 真实三栏工作区、URL持久绑定、资源/任务选择、QA/笔记/作答 |
| web-app/src/views/student/LearningPathView.vue | 工作区入口、生成前覆盖检查与缺口提示 |
| web-app/src/router.ts | 工作区可恢复上下文路由 |
| web-app/src/config/navigation.ts | 学生学习工作区导航 |
| web-app/src/composables/useStudyActivity.ts | 工作区复用原学习路径有效活动类型 |
| web-app/src/components/admin/LearningGapManager.vue | 读取实际缺口并显式创建原建设任务 |
| web-app/src/components/admin/TaskOperationsPanel.vue | 真实任务统计、详情与UNKNOWN口径 |
| web-app/src/views/admin/knowledge.vue | 复用文档管理并接入学习缺口 |
| web-app/src/views/admin/overview.vue、tasks.vue | 任务运营数据入口 |
| tests/unit/test_learning_context_p1.py | 上下文/QA/笔记/归属/版本/写屏障/评分/调整恢复 |
| tests/unit/test_plan_knowledge_p1.py | 正式版本准入、缺口与管理员队列、生成中撤回 |
| tests/unit/test_graph_security_p1.py | 图谱权限/来源/缓存/预算取消边界 |
| tests/unit/test_admin_operations_p1.py | 管理员任务统计、脱敏及UNKNOWN语义 |
| tests/unit/test_graph_performance.py | 新只读语义和认证下的原性能回归 |
| tests/unit/test_coordinator.py、test_transcript_learning_path.py、test_assistant_tasks.py | 在原编排/取消/成绩单单元测试中显式隔离新增知识准入；真实准入由新测试验证，未在生产加FakeDb绕过 |
| tests/e2e/learning_context_migration.py | 0029→0028→0027→0029及旧用户/笔记保留 |
| tests/e2e/learning_workspace_runtime.py、run-learning-workspace.mjs | 真实路由+SQLite+Chromium工作区/管理员；生成边界为受控桩 |
| tests/e2e/plan_knowledge_real_runtime.py | 复用文档专项真实运行器，追加真实发布→Chroma→计划准入检查 |

## 跨模块一致性

使用原FastAPI多服务和同一套SQLAlchemy表；没有平行栈。LearningContext记录用户、计划ID、stage_id、task_id、知识点、资源ID及SHA版本；客户端不能任意指定知识点ID覆盖服务端绑定。更换资源创建新绑定，原标签页保留原绑定；资源修改/归档或任务删除/计划停用使旧绑定失败。追加补强任务且保留原任务ID时原上下文仍可恢复。

QA的Conversation绑定ctx标记，执行前与回答落库前复核；流式内容在来源变化前可能已发送部分片段，最终写入仍阻断。生成任务沿用AssistantTask和执行租约，模型结果写入前校验上下文；课件生成创建子上下文，题组显式记录ContextExercise。评分使用数据库标准答案，回执、AnswerRecord、UserProfile与任务learning_evidence同事务提交；重放不重复加分。证据回写不自动把学习任务标为完成，完成仍遵守原先的用户确认和先修约束。

准入使用SystemSubject/KnowledgePoint及有效KnowledgeVersion；只接受corpus受控路径、当前文件哈希及实际Chroma片段，不以manifest或空资源对象代替检索存在。PDF正文不含知识点字面词时，读取已明确绑定的正式版本片段验证可用性。未准备好的请求保存LearningKnowledgeGap，管理员显式排AI_SUBJECT_PLAN或BUILD_POINT；没有自动发布。预算预留仍使用原KnowledgeBudgetCounter，界面不把它计为实际Token。

## 验证、失败与恢复

证据根 `artifacts/aura-p1-20261020/`。完整命令、退出码、无dotenv/真实凭证配置在各目录command.json。详见08更新；最终结果以原始日志为准。

- regression-final：167 passed /1432 warnings，当前最终组合全部通过；此前regression-v4为164 passed /1394 warnings，随后planning-final为62 passed /901 warnings。各批次有重叠，最终167已包含新增生成中撤回及图谱零预算/取消测试。
- graph-final-v2：40 passed /156 warnings，覆盖新增零预算/取消前Provider阻断。各批次有重叠，不相加冒充去重总数。
- browser-v6：七组真实业务检查，pageErrors为空；桌面/平板/手机布局与折叠、管理员任务详情有截图且已实际查看。1笔记、3绑定题、1作答、1成功助手任务有DB读回。生成/问答为受控桩，未声称真实模型通过。v5截图复核发现弹窗受面板裁切，append-to-body修正后v6通过。
- documents-real-v1：复用文档专项，真实SQLite、Chroma HTTP、独立Worker和Chromium；上传PDF/审核/发布/学生检索/修订替换/回滚/撤回/硬退出恢复通过。计划准入额外结果为READY且有真实version_id。课件生成Provider仍为LOCAL_STUB_ONLY。路由切换ERR_ABORTED保留，pageErrors/apiErrors为空。
- migration-v1：空库head0029，0029→0028→0027→0029，旧账户与笔记保留；未接触共享库。
- build-final.log：vue-tsc + Vite退出0，构建3.94秒；保留原第三方与动态/静态导入提示。
- 初次graph-v1夹具缺必填描述；context-v1/v2旧单元测试没有正式知识夹具、一个新测试路径错误及Windows文本换行哈希差异；regression-v2/v3剩余旧单元隔离问题。修正测试边界，生产不放宽知识门禁。browser-v1点击Element Plus输入被覆盖，v2暴露真实的路由重挂载丢失计划选择；已修并v3–v5通过。日志全部保留。

## 后续已推进说明

下列下一步为本检查点历史。逐调用台账、独立Worker心跳、执行尝试、本地PPTX/SVG/WAV、导图编辑历史现已实现，当前证据和剩余入口见[12验收报告](12-operations-media-acceptance.md)，避免重复开发或继续引用旧UNKNOWN结论。

## 下一步具体入口（历史）

1. P1-06：从 `common/performance.py:PerformanceTrace.record_model_response`、`services/agent_service/app/services/llm_factory.py` 开始设计Provider逐调用持久账本，未知/估算/真实和测试模式分开；为Assistant/Knowledge Worker建立独立心跳与完整尝试事件。现有operations只提供有证据的局部读取，不当作完整Token/Worker验收。
2. P1-07：复用 `assistant_tasks._coordinated_result`、Resource草稿/审核及原Coordinator，补文本改写/Prompt优化/图文编排与真实未配置阻断；不要新建平行任务引擎。
3. P1-08/09：以LearningContext为统一绑定，补资源历史版本与多模态产物、笔记编辑历史/分类、闪卡知识点证据。仅现有Mindmap节点列表不能计作编辑器验收。
4. P1-10：继续按03原子拆分，覆盖全站与性能；共享上线前审计schema基线并备份，不能把隔离迁移成功当作共享库升级授权。当前旧后端尚未加载这些新API。
