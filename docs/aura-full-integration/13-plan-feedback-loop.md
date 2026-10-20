# 学习计划智能反馈、动态调整与闭环修复 — 交付报告（2026-10-20）

## 1. 原有问题

用户截图暴露三张页面问题：

| 现象 | 判定 |
| --- | --- |
| 学习进程显示“学习概览接口尚未部署” | `GET /evaluation/overview/me` 返回 404，前端据此误判“未部署” |
| 学习工作区显示 `Not Found` | `GET /learning/contexts/catalog` 与 `GET /learning/contexts/{id}` 返回 404 |
| 生成英文数据结构计划、只有“去学习/去练习/完成”、无反馈入口 | 计划制定缺少自然语言反馈 → 调整 → 差异预览 → 确认闭环 |

## 2. 根因（以真实 HTTP 断言与源码核对为准，非凭页面文案）

两个 404 不是“未部署”，而是**运行中的后端进程加载的是旧代码 + 共享库缺迁移表**：

1. **进程陈旧**：`8002 agent_service`(PID 38944)、`8004 evaluation_service`(PID 20872) 均启动于 2026-10-19 23:43，早于 `learning_contexts.py` 与 `reports.py:/overview/me` 的提交时间。对运行进程 `/openapi.json` 探测：均无 `learning/contexts/*`、无 `overview/me` 路径，且 `GET` 返回 404。
2. **共享库缺表**：`learning_system.db`（`.env` 的 `DATABASE_URL=sqlite:///./learning_system.db`）无 `alembic_version` 版本记录，缺 `learning_contexts`、`study_sessions`、`study_activities`、`learning_knowledge_gaps`、`context_exercises` 等 0026/0028/0029 迁移表。

源码中两条路由均存在（`services/agent_service/app/api/routes/learning_contexts.py`、`services/evaluation_service/app/api/routes/reports.py`），单测/E2E 均曾通过。因此这是**部署/迁移问题**，不是代码缺失。

## 3. 修改文件

新增：
- `services/agent_service/app/services/plan_feedback.py` — `PlanFeedbackService` + 纯函数 `compute_plan_diff`
- `services/agent_service/app/services/task_feedback.py` — `TaskFeedbackService`（8 类任务级执行反馈，确定性改稿，无需 LLM）
- `tests/unit/test_plan_feedback.py` — 7 项单元测试
- `tests/unit/test_task_feedback.py` — 7 项单元测试
- `web-app/src/components/PlanFeedbackPanel.vue` — 计划级反馈 + 差异预览 + 确认 UI
- `web-app/src/components/TaskFeedbackButton.vue` — 每任务“反馈”弹层 + 差异确认 UI

修改：
- `services/agent_service/app/api/routes/learning.py` — 新增 `POST /paths/feedback/preview`、`POST /paths/feedback/{proposal_id}/confirm`、`POST /paths/task-feedback/preview`
- `web-app/src/views/student/LearningPathView.vue` — 接入 `PlanFeedbackPanel` 与 `TaskFeedbackButton`

## 4. API 修复情况（隔离环境真实 HTTP 验证）

在“最新代码 + `alembic upgrade head` 全量迁移（head=0031）”的隔离库上启动 `agent_service:8102`、`evaluation_service:8104`（`--lifespan off`），实测：

| 断言 | 运行共享进程(8002/8004) | 隔离最新代码+迁移 |
| --- | --- | --- |
| `/learning/contexts/catalog`（无 token） | 404 | **401**（路由已注册，认证拦截） |
| `/evaluation/overview/me`（无 token） | 404 | **401** |
| openapi 含 `learning/contexts/*` | 否 | 是（6 条路径） |
| openapi 含 `overview/me` | 否 | 是 |
| openapi 含 `paths/feedback/*` | — | 是（2 条） |

结论：修复 = 用最新代码重启 8002/8004 + 补齐运行库缺失表。真实数据读回（计划/练习/活动统计）由既有单测与 E2E（`tests/e2e/run-study-overview.mjs`、`run-learning-workspace.mjs`）在隔离环境证明。

**当前共享环境实测状态（2026-10-20 20:22 复核，两个 API 错误均已解除）**：
- `8002 agent_service`：已以 `runtime.sqlite + --lifespan off` 重启，openapi 含 `learning/contexts/*`、`paths/feedback/*`、`paths/task-feedback/*`，`/learning/contexts/catalog`（无 token）404 → **401**。学习工作区 `Not Found` **已解除**。
- `8004 evaluation_service`：本轮以同一 `runtime.sqlite`（已补齐 `study_sessions/study_activities` 等表）+ 最新代码 + `--lifespan off` 重启（PID 81484）。`/evaluation/overview/me`（无 token）404 → **401**，openapi 含该路由。
- **真实数据端到端断言**：注册 `api-verify-1020202302` → 登录取 token → `GET /evaluation/overview/me`（Bearer）返回 **HTTP 200**，`data` 含 `analytics/active_plans/due_cards/weak_points/suggestions/recent_resources/evidence`，新账号 `active_plans=[]`、`due_cards=0`、`study_seconds=0`。证明接口真实返回成功、非屏蔽错误。

**共享库上线说明**：`learning_system.db` 无可信 Alembic 基线（`alembic_version` 为空），直接 `upgrade head` 有重复建表/降级风险（历史 0009 降级曾误删 0002 列）。运行态实际使用 `artifacts/local-start-20261019/runtime.sqlite`（副本），同期会话已用幂等 `Base.metadata.create_all` 补齐缺失表并留备份 `runtime-before-tables-20261020-200640.sqlite`；共享 `learning_system.db` 本身仍未迁移（保持只读审计态）。

## 5. 计划制定反馈实现情况（本次核心新增）

复用现有 `LearningPath` JSON、`path_revision` CAS、`commit_path_update`、提案/确认幂等（`applied_feedback`）机制，实现：

- `POST /paths/feedback/preview`：读取本人 active 计划 → 将自然语言反馈交给配置模型生成修订版 → `compute_plan_diff` 生成结构化差异（新增/删除/重排任务、时长/难度变化、阶段变化、概述变化、对总任务数/预计天数/每日分钟的影响）→ 以 `feedback_proposal`（含 `after_payload`、`diff`、`base_revision`）持久化，**不落地改动**。
- `POST /paths/feedback/{proposal_id}/confirm`：校验 `path_revision == base_revision`（过期 409）、`applied_feedback` 幂等（重复确认返回 `already_applied`）、应用修订版；**保留已完成任务**的 `completed/status`，被删除的已完成任务记入 `removed_completed_history`；跨用户越权 404。
- 无模型凭据时返回明确 503（“尚未配置模型凭据，无法处理计划反馈”），**不做“已收到反馈”的假 no-op**；真正“无变化”才返回 `no_change`。

前端 `PlanFeedbackPanel.vue`：意见输入 → `查看反馈方案` → 差异对比弹窗（当前/确认后表格 + 新增/删除/顺序/时长/难度/概述分组）→ `确认修改` 或 `保留原计划`。

## 6. 计划执行反馈实现情况（本次新增）

执行阶段任务级反馈已完成并接入统一提案模型：

- `POST /paths/task-feedback/preview`：接受 `{ task_id, feedback_type, note }`，8 类确定性反馈（`too_hard/too_easy/not_understood/not_enough_time/already_mastered/more_practice/more_video/more_illustration`）各映射到明确的计划改稿（降/升难度、加前置讲解/预备任务、时长减半+延天数、标记完成、追加练习/视频/图文任务），**无需 LLM、不推断掌握度**。
- 确认复用 `POST /paths/feedback/{proposal_id}/confirm`（同一 `feedback_proposal` 模型、同一 CAS/幂等），前端 `TaskFeedbackButton.vue` 每个任务“反馈”弹层 → 差异预览 → 确认/保留。

学情驱动链路（`POST /paths/adaptation/preview` + `/confirm`，近30天同知识点≥3次判分正确率<60% 补强）保持不变，本次未重写。

## 7. 学习任务跳转情况

`去学习/去练习` 现跳转 `CoursewareView`/`ExerciseView`，三栏工作区已打通真实资源引用问答、作答评分、版本笔记、课件/练习持久任务。本次未改动该链路，未重复开发。

## 8. 进度和画像联动情况

进度口径（`LearningPath` JSON 阶段/任务 vs `LearningTask`）此前已修复不一致。本次反馈确认沿用同一 `path_data_json` 与 revision，不会引入第二套口径；`/evaluation/overview/me` 读回真实计划/练习/复习/活动统计。已完成历史不因计划修改丢失（§5）。

## 9. 测试证据

- `tests/unit/test_plan_feedback.py`：**7 passed**（diff 全覆盖、preview 不落改动、confirm 应用+幂等、完成历史保留、完成导致 409、路由鉴权/校验/越权、无凭据 503）。
- `tests/unit/test_task_feedback.py`：**7 passed**（8 类确定性改稿、任务不存在 404、非法类型 422、确认复用）。
- `test_plan_feedback` + `test_task_feedback` + `test_path_adaptation`：**19 passed**（含既有学情链路回归）。
- 新增/改动 Python 文件 `ruff check`：**All checks passed**。
- 前端 `npm run build`：**退出 0**（2.75s，仅既有第三方 INVALID_ANNOTATION/分块提示）。
- 隔离 HTTP：上文 §4 表；共享环境 `8002` openapi 实测含全部反馈路由（§4 复核）。真实付费 DeepSeek 调用 **0**（无 LLM 凭据路径与 monkeypatch 桩验证，未触发真实模型）。

## 10. 尚未完成的问题（如实）

1. **两个 API 错误已解除**（8002 + 8004 均已最新代码 + 补齐 runtime.sqlite 重启，真实 200 断言见 §4）。共享 `learning_system.db` 本身仍只读审计、未迁移（运行态用 runtime.sqlite 副本）。
2. **计划制定反馈的真实 LLM 效果**：修订模型链已接 `LLMFactory`，但无付费授权，未跑真实 DeepSeek 修订；中文/时长/顺序等反馈语义的模型输出质量待授权后验收。
3. **任务级反馈前端浏览器验收**：`TaskFeedbackButton` 已接入并通过 build/单测，但未跑真实浏览器点选→差异→确认链路（E2E 待补）。
4. **进度与画像联动全链**：补强任务追加/计划修改后的进度口径、画像更新仍在同源数据上，未做全站 A–E 场景验收。
5. 其余历史缺口（Neo4j、真实 Chroma 全站、OCR/PDF/PPTX 原生、A–E 全局原子验收）不变。

> 说明：本会话读取时发现 `read` 工具对部分文件返回了陈旧缓存（如 `exercise_generation.py` 一度显示已删除的 `@lru_cache`，实盘已改 `prompt_registry.load_prompt_template`），已用 `git diff`/`pwsh`/pytest 实盘核对；工作树另含 P1-07 未提交改动（prompt_admin/prompt_registry/resource_editor 等），非本任务产物，未触碰。
