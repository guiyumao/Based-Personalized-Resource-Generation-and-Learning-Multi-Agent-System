# 学生端自主学科建设 / 知识补全 / 学习计划全链路 — P0-1 交付文档

> 日期：2026-10-20 ｜ 分支：main ｜ 范围：仅 P0-1（知识覆盖门禁由阻断式改为建设式）
> 结论先行：**P0-1 已编码并通过隔离单测；P0-2~P0-8 未实现；场景 A 全链尚未验收，不宣称已完成。**

## 1. 发现的原始业务逻辑错误

学生请求「从零学习数据结构、六周完成」时，系统返回：

```
学科尚未建立，已记录管理员待处理请求。请管理员在知识库中处理后重试。
```

根因不是缺数据那么简单，而是**计划生成被三处硬门禁串联阻断**，把「公共知识库是否已人工审核发布」错误地当成「学生能否创建个人学习计划」的强制前置条件，与三层知识协同架构（公共库 / 候选库 / 学生个人知识空间）的原始设计不一致。

阻断点（按调用顺序）：

| # | 位置 | 行为 |
|---|---|---|
| 1 | `web-app/src/views/student/LearningPathView.vue` `checkKnowledge()` | `ready=false` 直接 `return`，不再调用生成 |
| 2 | `services/agent_service/app/agents/coordinator.py` `_execute_agents` | `require_plan_knowledge` 抛 409，整个协同流程终止 |
| 3 | `services/agent_service/app/services/learning_path.py` `generate_path` | `require_plan_knowledge` 抛 409，即使到达也不出稿 |

`plan_preflight` 只做「检查 + 记录缺口 + 返回 not ready」，不触发任何知识建设，因此学生被永久卡住。

## 2. 已修改的代码（P0-1）

| 文件 | 改动 |
|---|---|
| `services/agent_service/app/services/plan_knowledge.py` | 新增 `assess_plan_knowledge()`：返回 `mode ∈ {public, personal_draft}`；缺失时不抛 409，仍记录缺口（`LearningKnowledgeGap`，request_key 幂等去重），提示改为「将为你生成个人学习知识草稿」 |
| `services/agent_service/app/agents/coordinator.py` | `path_planning_agent` 前置覆盖检查由 `require_plan_knowledge`（抛 409）改为 `assess_plan_knowledge`；写入 `context["knowledge_scope"]` / `context["knowledge_gap"]`，不再终止 |
| `services/agent_service/app/services/learning_path.py` | `generate_path` 改为 `try: require_plan_knowledge → except HTTPException: assess_plan_knowledge`；personal_draft 模式：空检索上下文、不写 `subject_id`、标 `knowledge_scope="personal_draft"`、记录 `knowledge_gap_reason/gap_id` |
| `services/agent_service/app/api/routes/learning.py` | `/paths/preflight`、`/paths/generate` 改用 `assess_plan_knowledge` |
| `web-app/src/views/student/LearningPathView.vue` | `checkKnowledge()` 对 `personal_draft` **继续生成**（info 提示），不再直接 return；告警按 mode 区分类型 |

## 3. 复用的已有模块（未另起平行系统）

- `plan_preflight` / `LearningKnowledgeGap` 缺口记录：完全复用。
- `CoordinatorWorkflow` / `LearningPathService` / `LearningPath`(JSON) / `path_revision` CAS：完全复用。
- 学习计划反馈闭环（上一轮）：`plan_feedback.py` + `PlanFeedbackPanel.vue`；任务级反馈 `task_feedback.py` + `TaskFeedbackButton.vue`。
- 未新增表、未新增平行学科系统、未改迁移。

## 4. 门禁语义：public vs personal_draft

| 情形 | 旧行为 | P0-1 新行为 |
|---|---|---|
| 学科存在 + 已发布 + 索引有效 | 生成计划（公共检索上下文） | 不变（public） |
| 学科缺失 / 无知识点 / 无发布 / 索引不可用 | **409 终止 + 等管理员** | **personal_draft**：仍记录缺口，生成个人 AI 草稿计划，标记 `knowledge_scope="personal_draft"`，**不冒充公共正式知识** |

personal_draft 计划在 `path_data_json` 中携带 `knowledge_scope`、`knowledge_gap_reason`、`knowledge_gap_id`，可追溯；不写 `subject_id`，不写 `knowledge_versions`，不会被检索层当作公共知识。

## 5. 测试证据（本轮实跑）

- `tests/unit/test_plan_knowledge_p1.py`：**10 passed**。新增/更新断言：
  - 未知学科 → `/paths/preflight` 返回 `reason=SUBJECT_MISSING`、`mode=personal_draft`、`gap_id` 去重为 1；
  - 协调器**不再 409**，持久化 `LearningPath.path_data_json["knowledge_scope"]=="personal_draft"`、`knowledge_gap_reason=="SUBJECT_MISSING"`、`subject_id is None`；
  - **不创建公共 `SystemSubject`**（未知学科不会被提升为公共学科）。
- 受影响回归：`test_coordinator` / `test_agent_routes_use_coordinator` / `test_learning_path_adjustment` / `test_transcript_learning_path` / `test_assistant_tasks` / `test_path_adaptation` / `test_plan_feedback` / `test_task_feedback` 合计 **89 passed**。
- Ruff：改动文件全部通过（`coordinator.py` 两处 `I001` 为改动前既有导入排序问题，非本次引入）。
- 前端 `npm run build`：退出 0（2.26s）。

## 6. 明确未完成（P0-2 ~ P0-8）

1. **P0-2**：学科缺失时**自动触发** `KnowledgeBuildTask(AI_SUBJECT_PLAN)` 生成大纲、建知识点、保存为个人草稿，并回填到计划生成。当前 personal_draft 仅靠模型自带知识出稿，**不会自动建设公共/个人知识**。
2. **P0-3**：搜索/抓取/来源整理/候选保存的真实接入（Search/Fetch 当前受配置与安全闸门限制）。
3. **P0-4**：个人学习知识空间的**持久化 + 可检索**（复用现有结构，未建新表）。
4. **P0-5**：知识建设完成后**自动续接原计划请求**（当前需用户再次点击生成）。
5. **P0-6**：计划预览→自然语言反馈→调整→确认（反馈机制已在上一轮实现，但未与自动建设串起来）。
6. **P0-7**：学生端**真实任务进度**、刷新恢复、错误处理（当前仍是同步生成，无进度面板）。
7. **P0-8**：隔离环境端到端验收（场景 A~G）。

**场景 A 全链未通过**，本文档不宣称通过。

## 7. 运行与部署说明

- 运行中 `8002 agent_service` 仍是 2026-10-20 20:07 的构建，**需重启才加载 P0-1 改动**；按既有约束本轮未重启共享进程。
- 运行库为 `artifacts/local-start-20261019/runtime.sqlite`（已由同期任务用 `Base.metadata.create_all` 补齐缺失表）；共享 `learning_system.db` 仍只读审计、未迁移。
- 真实付费模型调用：0。personal_draft 出稿需要已配置的 LLM，凭据缺失时显式失败、不伪造。

## 8. 下一步建议

先做 P0-2：在 `assess_plan_knowledge` 返回 `personal_draft` 时，创建 `KnowledgeBuildTask(AI_SUBJECT_PLAN)`，生成 `SubjectOutline` 并落个人草稿（复用 `KnowledgeCandidate`/`LearningPath` JSON，不新建平行库），再把草稿大纲作为 `retrieval_context` 回填 `generate_path`；随后 P0-3 接入 Search/Fetch，P0-5 自动续接，P0-7 前端真实进度，P0-8 E2E 验收。
