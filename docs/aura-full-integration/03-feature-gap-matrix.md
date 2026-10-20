# 功能差异矩阵（首轮检查点，24 个能力组）

## 当前增量覆盖（以12验收报告为准）

2026-10-20接续：第8组已补导图编辑/缩放/CAS保存/历史，第9组真实SVG步骤动画，第11组本机WAV生成存储播放，第12组真实PPTX下载重读，第14组补导图版本快照，第20/21组补LIVE/TEST逐调用台账、预算、独立空闲Worker心跳和执行尝试。上述子链已在browser-final隔离验收；全量unit为592 passed。另有本轮授权4次真实Chat、输出3432的课件/三题/上下文QA/评分证据。具体限制、逐文件与逐包状态见[12验收报告](12-operations-media-acceptance.md)。P1-07、视频URL、外部图文、笔记历史与完整闪卡画像、18项全场景仍未齐。下方首轮矩阵及11检查点描述保留为历史，不再作为这些新增子能力的当前结论。

## P1状态覆盖说明（2026-10-20）

下方首轮矩阵保留历史。本次第3/4/7/14/15/19/20/21/23组已有增量：正式发布/Chroma计划准入、持久学习上下文、三栏文本/练习闭环、笔记来源版本、图谱只读安全、管理员持久任务统计。对应代码及P1-01～P1-10逐包状态以[11检查点](11-p1-learning-context-checkpoint.md)为当前准据。第4组从未实现更新为“文本/习题子链隔离验收，完整多模态未完成”；第19组核心权限/费用边界已隔离验收，历史关系来源及Neo4j仍待补；第20/21组只补真实任务运营读取，完整Token台账/独立Worker心跳仍未实现。第23组文档专项已复用真实Worker/Chroma/浏览器验收。所有能力组的原子功能尚未穷尽，总体PARTIAL。

状态采用：未实现 / 只有 UI / 只有后端 / 部分实现 / 已实现但未联动 / 已完成并验收。验收均限定本轮隔离环境；没有覆盖的模块不因为既有文档声称通过而改为验收完成。路径简写：V=上游 Vue-frontend/src，P=上游 Python-backend/app，J=上游 Java-backend/src/main/java/com/learning；本地服务路径均位于 services。

| # / 能力 | 参考位置 | 当前源码位置 | 真实状态 | 缺失功能 / 待改文件 | 接口 | 模型 | 测试 / 完成状态 |
|---|---|---|---|---|---|---|---|
| 1 首页 | V/views/DashboardView.vue | DashboardView、LearningOverviewPanel、learning_analytics.py | 部分实现 | 周目标、上次资源续学、跨页画像同源仍需补 | /evaluation/overview/me | 复用路径/作答/资源/复习 | 本轮首页子闭环浏览器 PASS |
| 2 有效时长 | J/service/StatsService.java | useStudyActivity、study_activity.py | 已完成并验收 | 仅隔离验收；部署、历史时长不回填；音视频无操作期间不计时 | /evaluation/activity/heartbeat | StudySession/StudyActivity | CAS并发/重放/空闲/午夜/失败事务/浏览器 PASS |
| 3 创建计划 | V/views/PlanCreateView.vue、P/api/v1/endpoints/plan_generator.py | LearningPathView、learning_path.py | 部分实现 | 开始结束日期、考试目标、知识缺口阻断与补充闭环；相关 schema/Coordinator | /paths/generate | LearningPath JSON | 既有计划测试本轮回归；真实模型 NOT_RUN |
| 4 三栏工作区 | V/views/PlanDetailView.vue、V/components/plan/ | 路径页、CoursewareView、AssistantPet | 未实现 | 统一 plan/module/resource/kp context 与三栏选择器 | /paths、/assistant/*、/resources | 需适配路径资源关联 | 独立页面不算三栏验收 |
| 5 动态调整 | J/controller/LearningPlanController.java | path_adaptation.py、PlanAdaptationPanel | 部分实现 | 已补作答证据+时间约束预览确认；目标变化、落后/掌握提前跳过未补 | /paths/adaptation/* | LearningPath JSON提案/revision | 本轮确认、重放、并发过期、首页读回 PASS |
| 6 图文 | P/agents/resource_generator.py | resource_generation.py、CoursewareView、document_export.py | 部分实现 | 完整质量标准及导出回归 | /resources/generate、/resources/{id} | Resource | 本轮未生成真实图文，既有能力复用 |
| 7 习题 | V/components/resource/QuizPlayer.vue | ExerciseView、report_service.py | 部分实现 | 全题型/主观评分置信度/安全编程执行、自动画像联动复验 | /exercises/*、/evaluation/practice/submit | Exercise/AnswerRecord | 相关回归PASS；全场景A/E未验收 |
| 8 思维导图 | V/components/resource/MindmapPlayer.vue | Resource.structured_json、ResourceView | 部分实现 | 编辑、缩放、关联、版本、图片导出组件与保存API | /resources/* | Resource | 全交互 NOT_RUN |
| 9 动画 | V/components/resource/AnimationPlayer.vue | 现有video_script不等于动画 | 未实现 | 受限模板、分镜、Worker渲染、真实文件与播放器 | 待接原任务API | Resource/AssistantTask适配 | NOT_RUN；不显示假视频 |
| 10 视频发现 | P/agents/video_search_agent.py | deepseek_search.py、知识采集 | 未实现 | 专用视频条件/来源验证/去重收藏/安全嵌入 | 待接原任务/资源API | Resource/Interaction | Search/Fetch本轮未调用 |
| 11 播客 | P/agents/resource_type_generator.py | 无完整TTS产物链 | 未实现 | 真实TTS适配、任务状态、音频文件/播放历史 | 待接原Worker | Resource/AssistantTask | NOT_RUN；未配置/授权TTS |
| 12 PPT | V/components/resource/PptxViewer.vue | DOCX导出非PPT | 未实现 | PPTX生成、私有预览、下载、源稿校验 | 待扩展资源导出 | Resource | NOT_RUN |
| 13 代码/总结 | P/agents/resource_type_generator.py | structured code_case、resource_generation.py | 部分实现 | 独立交互/安全执行与类型验证复验 | /resources/generate | Resource | 本轮未覆盖全部类型 |
| 14 资源版本 | J/service/资源相关Service | Resource状态与知识版本关联 | 未实现 | plan/module/task/version稳定关联、历史资源不覆盖 | /resources/* | Resource需增量适配 | NOT_RUN |
| 15 笔记 | V/views/NoteListView/NoteDetailView | StudyToolsView、study_tools.py | 部分实现 | 标签、学科、知识点、摘录定位与搜索 | /study/notes | StudyNote | 既有CRUD复用；扩展NOT_RUN |
| 16 闪卡 | V/components/flashcard/FlashcardPlayer.vue、P/api/v1/endpoints/flashcard.py | study_tools.py、StudyToolsView | 部分实现 | 课件/错题来源、知识点调度、影响掌握估计 | /study/cards | ReviewCard/CardReviewEvent | 到期数量真实读取PASS；全部复习未验收 |
| 17 分析 | V/views/AnalyticsDashboard.vue | learning_analytics.py、ReportView | 部分实现 | 题型/难度/效率趋势、完整热力图和跨页口径 | /evaluation/analytics/{id} | 复用真实事件/作答/活动 | 本轮基础统计及进度修复PASS |
| 18 画像 | V/views/ProfileView.vue | learning_content_profile.py、profile_analysis.py | 部分实现 | 复习证据置信度/趋势/推荐闭环统一 | /users/{id}/profile/* | UserProfile | 画像dashboard相关回归PASS；完整联动未验收 |
| 19 图谱 | V/views/KnowledgeGraphView.vue、P/api/v1/endpoints/knowledge_graph.py | graph.py、neo4j_connector.py | 部分实现 | 匿名/私有资源边界、模型费用、公共关系审核、个人状态叠加 | /graph/* | KnowledgePoint/Relation+UserProfile | 本轮仅定位风险，未修复/验收 |
| 20 统一任务/Token | P/graph/learning_graph.py、resource_chat.py | assistant_tasks/execution/worker、knowledge_worker | 部分实现 | 新增资源任务类型、统一结果协议、完整Token持久账本 | /assistant/*、knowledge tasks | AssistantTask/KnowledgeBuildTask | 助手相关回归PASS；新任务类型未接入 |
| 21 管理导航/用户 | V/views/admin/、J/controller/Admin* | adminNavigation、views/admin/、system_persistence | 部分实现 | 模型成功率、Worker监控缺独立真实入口 | /system/* | User/AuditLog等 | 本轮未重跑管理员浏览器验收 |
| 22 学科/知识点 | P/api/v1/endpoints/knowledge_tree.py | knowledge_construction.py、admin/construction | 部分实现 | 覆盖率、课程停用、来源详情逐项核对 | /knowledge-base/construction/* | SystemSubject/KnowledgePoint | 本轮未执行场景C |
| 23 文档/来源 | J/controller/KnowledgeBaseController.java | knowledge_documents相关工作区新增代码 | 部分实现 | 独立0027变更未由本轮审完；需核对原文件预览/解析/索引 | 需接续实际路由 | KnowledgeDocument/Point（独立变更） | 不计入本轮验收 |
| 24 建设/审核/维护 | P知识库相关Service | knowledge_candidates/versions/tasks/maintenance | 部分实现 | 失效来源、崩溃恢复、无人值守预算与发布全链 | /knowledge-base/* | Candidate/Version/BuildTask/MaintenancePlan | 本轮未跑真实Chroma/模型，D未验收 |

本轮已验收的四个子闭环为：首页真实汇总、活动区间采集、计划进度同源、学情提案确认。它们不等同于24组全部融合或18条强制标准通过。
