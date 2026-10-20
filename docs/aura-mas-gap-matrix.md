# AURA-MAS 功能差异与交付边界

核验日期：2026-10-17。上游固定提交 [`5923cf6cd766a58b112f24f02371bb87da1fa904`](https://github.com/cdz-hy/aura-mas/tree/5923cf6cd766a58b112f24f02371bb87da1fa904)，许可证 MIT。下表依据该提交中对应的 Controller、Service、Agent、Graph 和 Vue 文件及本仓库实际代码；不声称两个仓库的全部文件均逐行审计。

现有主联调链路是 Vue 3 `web-app` 与 FastAPI 8001–8006。`java-services` 是 Spring Boot 迁移骨架。新增能力接入现有账户、数据库和业务 API，不部署上游第二套 Java/Python/Vue 平台。

| 能力 | 当前项目源码证据 | AURA-MAS 源码证据 | 处理与本轮状态 |
| --- | --- | --- | --- |
| 学习分析 | `evaluation_service/reports.py` 阶段/月报；`AnswerRecord`、`ResourceInteraction`、`ChatMessage`、`LearningTask` 行为表 | `StatsController`、`StatsService`、`AnalyticsDashboard.vue` | 新增真实行为汇总、知识点作答正确率、进行中路径完成率及报告页活动图；学习时长、时段效率缺采集证据，未实施 |
| 学习画像 | `user_service/users.py` 对话画像、七维画像、深度分析 | `ProfileView.vue`、`profile_maintainer.py` | 保留现有画像；成绩单科目级诊断进入深度分析并参与缓存失效；成绩驱动知识点掌握仍待实现 |
| 管理员概览 | `system_service/admin.py`、`AdminView.vue`、现有业务表 | `AdminDashboardController`、`AdminDashboard.vue` | 新增真实用户、路径、资源、近七天答题统计 |
| 管理员用户 | 原有角色分配与 `users.is_active` | `AdminUserController`、`UserManagement.vue` | 新增搜索分页、管理员创建、停启用；公开注册仅学生，停用令牌失效 |
| 管理员知识库 | `agent_service/learning.py` 已有状态、来源、重建 API | `KnowledgeBaseController`、`KBManagement.vue` | 后台接入索引状态、来源列表和增量重建；上传/解析进度未移植 |
| 管理员资源 | `resource_service/resources.py` 已有审核与发布状态 | `AdminResourceController`、`ResourceManagement.vue` | 后台接入目录、详情预览、发布/归档；版本管理未实施 |
| Token 管理 | 无覆盖全部模型调用的持久 Token 账本 | `AdminTokenController`、`TokenAnalysis.vue` | 未实施；后台明确不显示估算值 |
| 管理员日志 | 现有 `AuditLog` 与 `/system/logs` | `LogManagement.vue` | 保留，账号状态操作新写审计日志 |
| 学习计划 | `agent_service/learning.py` 生成、查询、调整路径；学生路径页 | `LearningPlanController`、计划页面 | 个人成绩单可一键进入现有计划生成页，所选科目的真实均分进入原有 LLM 路径生成并持久化来源 ID；自动重排、章节拆分和提醒未实现 |
| 知识树/图谱 | `agent_service/graph.py`、知识图谱页、`KnowledgePoint` | 知识树/图谱 Controller、`knowledge_updater_graph.py` | 保留主数据；资源自动抽图与关系管理未移植 |
| 笔记/闪卡 | 原先无私有笔记与到期复习表 | `NoteController/Service`、`FlashcardService`、笔记与闪卡页 | 新增私有笔记、资源关联、AI 整理建议、到期复习及最近 50 次复习历史 |
| 多模态资源 | 现有结构化思维导图、代码案例、视频脚本 | `resource_type_generator.py`、PPTX/视频检索 Agent | 原能力保留；真实音频、动画、PPTX 移植未实施，视频脚本不标为视频 |
| 多智能体 | 现有 `coordinator.py`、RAG、审核、异步助手任务 | `learning_graph.py` 主控、分解、RAG、审查、人工确认 | 保留现有任务体系；LangGraph 节点与持久检查点未移植 |
| 智能问答 | `qa.py`、`qa_service.py`、学生问答页 | `resource_chat.py`、`ChatView.vue` | 原功能保留；本轮未做专项优化 |
| 成绩单解析 | `evaluation_service/transcripts.py` 预览纠错、分析、历史、导出 | 上游画像与统计链可供联动参考 | 个人分析已校验对象选择、隔离账号缓存并回写画像分析 ID；到路径/图谱的自动闭环未完成 |
| 课件/习题 | 当前 agent/resource/evaluation 服务有生成、校验、批改 | `pptx_template_engine.py`、`quiz_generator.py`、`quiz_grader.py` | 原功能保留；上游模板与策略未移植 |

## API 和数据口径

- `GET /evaluation/analytics/{user_id}?days=30`：本人或管理员；窗口 7–90 天，按北京时间归日。准确率分母为已判分作答。`question_seconds` 仅是记录的答题用时，活跃天数仅表示发生过作答、资源交互或用户提问。
- `knowledge_accuracy` 由该用户在窗口内的作答经 `exercises` 关联知识点计算，只能解释近期练习正确率；`path_progress` 来自最新进行中路径的真实任务完成标记。无进行中路径时返回 `null`。
- `GET /system/dashboard`、`GET /system/users`、`PATCH /system/users/{id}/status`：仅管理员。`POST /users` 现在仅管理员可创建账号；公开 `/users/register` 仅创建学生。停用后原 JWT 立即失效；管理员不能停用自身或移除自身管理员角色。
- `/study/notes` 与 `/study/cards`：笔记 CRUD、AI 整理建议、闪卡新增/删除/复习均绑定现有 `users.id`；`GET /study/cards/{id}/reviews` 返回本人最近 50 次复习。AI 建议需学生审阅后保存，不覆盖原笔记。资源页可带入资源 ID 开始记录笔记。
- `POST /evaluation/transcripts/analyze`：个人分析涉及多学生时须选定身份；缓存按当前账号区分。成绩单诊断保存在画像的 `transcript` 证据中，已有学习风格偏好保持原值；深度画像分析会读取科目均分和薄弱科目并在分析 ID 变化时刷新；画像的知识点掌握图只采纳有数值 `score` 的知识点记录。
- 成绩单页面的“根据成绩生成可跟踪计划”进入现有学习路径页，预填最低均分科目，用户检查主题后调用原多智能体路径流程。`LearningPathService` 根据 `transcript_analysis_id` 再次核对本人、个人分析状态和科目，覆盖浏览器提交的成绩证据，写入 `source_transcript_analysis_id`；同来源、学科和主题的活动路径重复请求直接返回已有路径。模型不可用时保留现有失败提示，不声称生成成功。
- 管理页资源操作复用 `/resources` 的目录、详情与状态接口；发布仍要求现有内容审核通过。管理页不显示无法审计的 Token 估算。
- 本轮新表为 `study_notes`、`review_cards`（迁移 `20261017_0012_study_notes_cards.py`）与 `card_review_events`（迁移 `20261017_0014_card_review_events.py`）；外键关联原 `users`、`resources`。仓库中另一项并行工作已占用 `20261017_0013_assistant_memories.py`，本轮迁移排在其后。

## 迁移与回滚

1. 停止写入并备份目标业务库，核查 `python -m alembic current`、`python -m alembic heads` 与目标表是否存在。
2. 空库或完整迁移链：设置目标 `DATABASE_URL` 后运行 `python -m alembic upgrade head`。本轮隔离空 SQLite 已成功升级至 `20261017_0014`。
3. 本机历史 `learning_system.db` 的 `alembic_version` 无版本行，且服务/测试引导的 `Base.metadata.create_all` 已建本轮表。不可在该库盲目执行全链 `upgrade head` 或 `stamp head`；须先核对历史 schema 与每个迁移确定基线。本轮 SQLite 在线备份位于 `artifacts/aura-integration/learning_system-backup-20261017-010531.db`，未对历史库执行迁移。
4. 回滚优先恢复备份。在已正确版本化且备份新数据后，`alembic downgrade 20261017_0013` 仅删除复习事件表；进一步降级会触及并行的助手记忆迁移和笔记表，必须单独审核。

## 本轮验证与下一步

- 相关后端测试：`python -m pytest -q tests/unit/test_aura_account_security.py tests/unit/test_aura_analytics_admin.py tests/unit/test_study_tools.py tests/unit/test_resource_authz.py` → 31 passed。
- 隔离 SQLite 全量 Python 单测：随机临时库下 `python -m pytest tests/unit -q --disable-warnings` → 最新 419 passed。新增成绩单路径测试验证所属账号、学科、可信分数覆盖、持久化与重复请求。首轮有 9 个失败，其中旧路由单测直接调用鉴权端点却未传用户；修复测试调用方式后全集通过。
- 仓库根目录 `mvn -q test`：通过（现有 Spring Boot 骨架模块）。
- `web-app` 的 `npm run build` 成功；`vis-network` 的 `INVALID_ANNOTATION` 为依赖警告。
- 隔离空库全链 Alembic 升级成功；本机历史库仍待基线确认。
- 本机 8002 智能体服务健康检查返回 200，未登录访问路径返回 401；尚未进行真实模型计划生成、全系统 E2E、浏览器人工验收与长时间并发恢复。后续优先补齐学习会话采集、成绩驱动的计划动态调整和图谱更新，然后建设 Token 账本及依赖外部服务的多模态能力。
