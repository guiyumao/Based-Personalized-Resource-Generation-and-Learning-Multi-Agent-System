# 当前系统源码核对（2026-10-20）

## P1接续更新（2026-10-20）

已在原FastAPI/Vue/SQLAlchemy/Assistant和Knowledge Worker中增量接入LearningContext、ContextExercise、LearningKnowledgeGap；没有重建架构或覆盖0027文档能力。当前源码head0029，隔离迁移往返通过；共享库/旧服务未激活。已补图谱读取鉴权、公私来源和模型费用边界、三栏文本/练习工作区、正式知识准入及管理员任务局部监控。完整文件与剩余边界见[11检查点](11-p1-learning-context-checkpoint.md)，文档发布专项见10；下文首轮结论保留作历史，不代表当前全部能力状态。

本次为持续开发的首个检查点，**不是全仓库审计已完成的证明**。实际根目录为本仓库，Git main / HEAD 05ee287，存在大量既有未提交改动。保留原 Vue 3/Vite、FastAPI、SQLAlchemy/Alembic、Chroma、Coordinator 与 Assistant Worker。没有启动上游 Java/Python 第二套服务。

## 已沿调用链核对的核心领域

| 领域 | 前端 / API / 持久化 | 发现及处理 |
|---|---|---|
| 首页 | `web-app/src/views/student/DashboardView.vue`；用户画像、评价报告与资源推荐 API | 原首页缺少计划、复习、活动时长汇总。本轮新增 `LearningOverviewPanel.vue` 与 `/evaluation/overview/me`，复用已有业务表；保留原画像面板 |
| 学习路径 | `LearningPathView.vue` → `services/agent_service/app/api/routes/learning.py` → `services/agent_service/app/services/learning_path.py` → `LearningPath.path_data_json` | 当前写入和完成操作更新 JSON stages/tasks。原分析读 LearningTask 表，页面又按完成阶段计算进度。已统一任务完成口径；没有改写历史计划 |
| 学情调整 | 原 `/paths/adjust` 仅修改单任务状态 | 本轮新增 `path_adaptation.py`：真实作答聚合 → 服务端保存提案 → 确认 → 增补后续练习。计划 JSON revision 防过期覆盖；保留原任务和依赖 |
| 行为分析 | `services/evaluation_service/app/services/learning_analytics.py` → AnswerRecord、ResourceInteraction、ChatMessage、CardReviewEvent | 原统计有真实事件但无有效活动时长。新增 StudySession / StudyActivity，按北京时间切分区间；不把答题 time_spent 当总学习时长 |
| 练习 | `ExerciseView.vue`、`ReportService`、AnswerRecord | 已有真实评分与历史；本轮补强入口可以带 topic 进入现有练习表单，不自动付费生成。完整题型、安全编程题及画像传播仍需逐项验收 |
| 笔记闪卡 | `StudyToolsView.vue`、`services/user_service/app/api/routes/study_tools.py`、StudyNote/ReviewCard/CardReviewEvent | 已有本人 CRUD、来源资源/笔记、间隔调度、复习历史。标签/学科/知识点来源结构和复习影响掌握估计尚未补全 |
| 资源 | `ResourceView.vue`、resource_service/routes/resources.py、ResourceManager、Resource | 已有生成归属、发布审核、structured_json、DOCX 与交互。没有统一证明 plan/module/task/version 全关联；不能把 video_script 当视频成品 |
| 多智能体 | assistant_tasks.py / assistant_execution.py / assistant_worker.py | 现有路由动作以 qa/courseware/exercise/plan/combined/profile/search/recommend 为主。不得把已有 Worker 覆盖误报成所有新资源任务已经接通 |
| 图谱 | graph.py → KnowledgeGraphRepository | 存在匿名图谱路由、共享图谱从资源正文取材和潜在模型补全边界；本轮未修改，列为后续安全优先项。公共关系、个人掌握度仍需独立验收 |
| 管理端 | adminNavigation.ts、useAdminWorkspace.ts、views/admin/ | 已有六分组十一页面，本轮不重建导航。工作区出现独立的 KnowledgeDocument/Point 与 0027 迁移；尚未在本轮审完或验收，不计入交付 |

## 本轮验证边界

91 项相关 Python 回归通过；真实 SQLite/API/Chromium 的首页、活动、确认调整流程通过。测试账号、计划、错误作答、120 秒初始活动均是明确的隔离 fixture，未写到真实用户库。浏览器随后实际操作产生约 15 秒服务端持久区间。

全用户页面、全管理员页面、全部路由的逐项审计及 A–E 场景没有完成。运行服务 8001–8007/5175 未由本轮重启；源码修改和隔离验证不能证明共享运行实例已更新。
