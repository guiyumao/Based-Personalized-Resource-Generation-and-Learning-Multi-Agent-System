# 三方差距矩阵：当前项目 × LearnMate × ZhiShu

> 审计日期：2026-10-15。本文档只记录**源码可核实**的事实。
> 两个上游仓库均**未发现任何许可证文件**，因此本次融合不复制其代码、提示词、页面或数据，
> 只把可核实的**设计事实与算法思想**在当前技术栈内重新实现。

## 0. 上游身份与复用条件

| 项目 | 默认分支 | 核实 commit | commit 日期 | 提交数 | 许可证 | 复用结论 |
|---|---|---|---|---|---|---|
| LearnMate<br>`Zengxing-hub/2026-A3LearnMake` | `master` | `c601e5e0849dd442e8593cc868ae21eb8e5bb39b` | 2026-06-24 | 1 | **无 LICENSE** | 全部权利保留，不可复用代码 |
| ZhiShu<br>`AbandonS-ED/ZhiShu` | `main` | `936a34a905725a58d586501a7b162883f3d59db0` | 2026-07-20 | 244 | **无 LICENSE** | 全部权利保留，不可复用代码 |

许可证判定依据（两者相同）：git 索引与工作区内 `licen*`/`copying`/`notice`/SPDX 全部零命中；
上游页面未标注 SPDX。ZhiShu 的 `README.md` 有一个 `## 许可证` 标题，正文只有
「本项目为第十五届中国软件杯参赛作品。」——这是参赛声明，**不构成授权**。

**这两条结论直接决定融合方式**：本次改动全部为在当前项目内重新实现，没有引入任何上游文件、
依赖、`.env`、数据库或生成数据。

### 0.1 上游自身的安全问题（作为反面依据，不做任何复制）

- ZhiShu：根目录 `.env` 与 `release/后端/.env` **被提交进公开仓库**，包含 `JWT_SECRET` 和多个厂商
  `*_API_KEY`；`.gitignore` 未覆盖这两个路径。本次不读取、不复制其值。
- LearnMate：`core/auth.py:7` 在 `JWT_SECRET` 为空时回退到硬编码签名密钥
  `"learnmate-secret-key-change-in-production"`。
- LearnMate：`/api/knowledge/*`（上传/重建/详情/删除）与 `GET /api/resources/detail/{id}`、
  `PUT /api/path/{id}/progress` **没有任何鉴权依赖**。

当前项目已有 JWT 算法加固、资源授权与配置鉴权测试（`tests/unit/test_jwt_algorithm_hardening.py`、
`test_resource_authz.py`、`test_system_configs_authz.py`），无需向上游学习这一点。

## 1. 逐能力差距矩阵

决策限定为：保留 / 增强 / 合并 / 新增 / 暂缓 / 不采用。

| 能力 | 当前项目证据 | LearnMate 证据 | ZhiShu 证据 | 各方优点与限制 | 决策 | 改动范围 | 验收证据 |
|---|---|---|---|---|---|---|---|
| **A 多智能体编排** | `coordinator.py` 1045 行；`CoordinatorState` 已含 task/session/intent/profile/plan/handoff/citations/validation；LangGraph `StateGraph` + `_run_isolated` 进程内异常隔离；白名单拒绝未知 Agent（`AGENT_NOT_ALLOWED`） | `orchestrator.py`：**单轮意图 switch**，注册 7 个 Agent；1 次 LLM 意图调用 + JSON 降级；**无依赖图、无 handoff、无重试、无超时**；仅路径规划内部用 `asyncio.gather` | `master_agent.py`：真实 LangGraph `StateGraph` **9 个节点**（README 称 10）+ `MemorySaver` checkpointer；`task_plan` + `current_task_index`；`_fail_task` 跳过失败继续；`TASK_TEMPLATES` 模板化任务计划 | 当前：服务边界、权限、错误码更完整；ZhiShu：状态字段与「失败跳过」语义清晰，checkpointer 可参考；LearnMate：无可用编排价值 | **增强** | 修复 `_execute_agents` 覆盖 `task_state` 的缺陷；补齐 `_build_task_state` 全字段（user_id/learner_profile/learning_evidence/intermediate_results/citations/validation_results） | `tests/unit/test_coordinator.py`、`test_coordinator_sync_agents.py`；新增 task_state 完整性断言 |
| **B 画像维度** | `common/profile_scoring.py`：7 维 + `algorithm_version=zhishu-scoring-v3` + 每维 `score/confidence/source/sample_size/evidence_ids/evidence_window/next_evidence` | `models.py:22-27` **六维**（knowledge_base/cognitive_style/learning_preference/error_patterns/learning_goal/time_rhythm）；三处定义一致；每维仅 `str`，**无 confidence/source/provenance**；`missing_dims` 返回但从不持久化 | `profile_dimensions.py` 7 维；每维 `{score, confidence}`，**无来源、无时间窗**；规则路径 `conf+0.05` / LLM 路径 `conf+0.02` 双写；per-student `asyncio.Lock` 防并发覆盖 | 当前：证据溯源、样本量、时间衰减、算法版本最完整；ZhiShu：双路径置信度增量与 per-student 锁值得吸收；LearnMate：六维**裸字符串**，弱于当前 | **保留 + 增强（并发）** | 不新建画像表；评估把 ZhiShu 的 per-student 写锁语义用于画像更新并发保护（见 §2 待办） | `tests/unit/test_zhishu_profile_mapping.py`；冷启动/低样本/重复作答 |
| **C 多类型资源生成** | 4 类：`courseware`/`exercise`/`notes`/`exam`（`common/schemas/agent.py:36`、`resource.py:15`）；持久化到 `Resource`（`type` 为 `String(30)`，可容纳新类型，**无需迁移**）；有 `generation_status`/`audit_status`/`publish_status`/`audit_reason` | **4/5 真实**：doc/code 为流式 Markdown，quiz/video 为 `chat_json` JSON，mindmap 为 **Mermaid 文本**（非结构化节点/边）；**无沙箱**（无 subprocess/exec/docker）；video 只产出 JSON 分镜脚本；无版本、无审核、无评价 | 4 类：document/exercise/mindmap/tutor/audio 等；`anti_hallucination` 类存在 | LearnMate：三类新资源形态（思维导图/代码实操/视频脚本）有**真实产出但被 README 夸大**；当前：结构校验与生命周期字段更完整 | **新增**（按当前模型可表达的类型接入） | `common/schemas/agent.py` 扩展 `resource_type` 联合类型；新增三类结构化 Schema、提示词与确定性校验；`web-app/src/api/types.ts` 同步 | 新 Schema 单测 + 结构校验单测 + 持久化/读取测试 |
| **D RAG 与引用** | `rag.py` 707 行：Chroma 持久/HTTP、版本化 `knowledge_base_version`、元数据过滤、词法快速路径、缓存、`source_ids`；`rerank` 有真实实现 | `rag_service.py`：Chroma **真实使用**（295 条真实 embedding）；但 **无 chunking 策略、无 upload 端点** | **声明与实现不符**：`document_parser`/`text_chunker`/`TextChunk` **均不存在**；`add_chunks` 从未被调用且引用未定义类型；**零上传端点** ⇒ `document_chunks` 永远为空；pgvector 路径对 JSONB 列用 `<=>`；reranker 是 **LLM 打分**且有 `len<=top_k` 短路 | 当前：真有一套完整可用的索引与检索；两家上游的「流水线」均不可用 | **保留 + 增强（来源校验）** | 不建第二套 RAG；新增确定性「来源检查」层：引用必须回指本次真实检索到的 chunk，未检索到证据时返回 `insufficient_evidence` | 新增 `content_validation.py` 来源检查 + 引用回指测试 |
| **E 内容审核 / 防幻觉** | `audit_service.py`：规则审核 + 可选 LLM 语义审核；`passed/rejected/unavailable`；生成链路含重试与上限 | `content_filter.py` 112 行：仅 `filter_content`（正则脱敏）被接入；`check_hallucination`、`validate_with_knowledge_base`、`validate_academic_content` **只被测试引用，生产代码从不调用**；`min_overlap` 默认 `0.0` ⇒ `validated` 恒为 True；**无重试、无超时** | `anti_hallucination.py` 三层类真实存在，但**只有 4 个 Agent** 真正调用（README 称 6）；LLM 层异常时 `passed=True` **失败开放**；`_generate_safe_version` 出错返回原文 | 三家都有审核概念；当前是唯一「审核失败不影响真实结论」且区分 `unavailable` 的实现 | **增强** | 新增确定性**结构检查**层（JSON/必填字段/题型规则/占位符/重复/截断）；与既有 LLM 审核分层，语义审核仍可返回 `unavailable` | 结构错误/占位符/截断/重复测试；拒绝与重试耗尽测试 |
| **F 学习路径与解锁** | `learning_path.py`：LLM 生成（已移除硬编码兜底）、`generation_source="llm"`、持久化；`LearningTask` 有 `status` | **无后端解锁校验**：`complete_node` 只按位置解锁，不检查分数；60 分阈值**只在前端**（`quiz/[nodeId]/page.tsx:173`），可直接调 API 绕过 | 后端 `complete_node` **只按位置解锁**，无分数校验；60 分阈值**只在前端**；`prerequisites` **存储并渲染但从不强制**；`mastery = min(100, correct_count*20)` 确定性、DB 约束 0–100 | 上游暴露了真实缺陷：**解锁门禁不能只放前端**；ZhiShu 的确定性掌握度公式值得保留为参考 | **增强** | 在现有路径服务内加入后端校验（前置节点 + 测验条件）+ 依赖环检测 + 阈值配置化；保留历史与已完成状态 | 环路/缺依赖/未通过不解锁/阈值配置/重规划保留历史测试 |
| **G 习题与错题** | `exercise_generation.py` 1996 行；`ExerciseItem` 含 `options/answer/analysis`；`AuditService.audit_exercises` 校验必填与选项数 | `quiz_agent.py` JSON 契约含 `options/answer/explanation`；`QuizRecord.is_correct` 是唯一反馈信号 | 5 类错因 `calculation/concept/reading/carelessness/unknown`；`STRATEGY_MAP` 每类对应一个策略；掌握度确定性更新 | 当前习题生成更完整；ZhiShu 错因分类可作**可选标签**，但分类由 LLM 判定、无过程证据 | **增强** | 新增**答案—选项一致性**与重复题、占位符、空答案确定性校验；错因分类本轮不引入（缺过程证据） | 答案不在选项内/重复题干/字母与序号答案键测试 |
| **H 智能辅导问答** | `qa_service.py` 1334 行；会话持久化、用户范围、检索依据、结构化分析 | `tutor_agent` 用 history/context/profile；`profile_agent` **20 字符切片伪造打字机效果** | `tutor_agent` + SSE | 当前多轮上下文与权限更完整 | **保留** | 不改 QA 主链路 | 既有 `test_qa_service.py` |
| **I 推荐排序** | `resource_manager.py`：User/Item-CF + 画像/薄弱点/热度混合；`ResourceInteraction` 持久化 | README 声称资源中心，未作为源码复用依据 | 资源中心页面 | 当前已有持久化交互与教师范围 | **保留** | 本轮不改推荐器 | 既有 `test_resource_manager.py` |
| **J 报告与统计** | `report_service.py` 从真实作答/错题/路径确定性汇总；LLM 仅解释 | `evaluation_agent`，LLM 报告 | LLM 报告 + Celery（**beat 未启动 ⇒ 定时任务永不触发**） | 当前事实来源与权限更强 | **保留** | 不改 | 既有 `test_evaluation_reports.py` |
| **K 前端体验** | Vue 3 + Element Plus；`ResourceView.vue` 有 `typeLabel` 映射；资源/路径/QA/报告页面齐全 | React + Vite；`ResourcesPage.jsx` **只分支 mindmap/quiz**，`type="video"` 资源渲染为裸 JSON（bug） | Next.js；60 分阈值硬编码在页面 | 当前无需迁移前端；LearnMate 的 video 渲染 bug 提示新资源类型必须补齐**每一种**类型的渲染分支 | **增强** | 为三类新资源补齐类型标签、结构展示与校验状态（含空/失败态） | 前端类型编译 + 主要流程失败态检查 |
| **L 权限与隐私** | 已有 JWT 加固、资源授权、配置鉴权、教师范围、管理员后台测试 | 大量未鉴权写接口；硬编码 JWT 回退密钥 | 公开提交 `.env`（API Key + JWT_SECRET） | 当前明显更强 | **保留** | 上游缺陷仅作为反面依据；新资源类型沿用现有鉴权，不新增旁路 | 既有 authz 测试 + 新资源类型授权测试 |
| **M 本地姿态/摄像头自习** | 当前无此能力 | 未发现 | README 提及 | 引入会增加隐私与前端依赖 | **不采用** | 无 | 需独立隐私评估后再立项 |
| **N 代码沙箱执行** | 当前无隔离执行环境 | **无沙箱**（全仓库无 subprocess/exec/docker） | 未发现 | 无任何一方提供可信沙箱；执行模型生成代码不可接受 | **不采用（本轮）** | 代码实操资源仅提供**静态示例 + 人工运行说明**，校验器显式拒绝「已执行」声明 | `code_case_no_execution_claim` 测试 |

## 2. 关键判断说明

1. **不因「上游有」而采用。** LearnMate 的五类资源中，视频只产出脚本、代码无沙箱、思维导图是
   Mermaid 文本；只有把这三点按**诚实的产出形态**接入才有用户价值，因此新类型分别命名为
   `video_script`（脚本，不产生视频文件）、`code_case`（静态示例，不执行）、`mind_map`（结构化
   节点/边，并兼容 Mermaid 文本）。
2. **ZhiShu 的 RAG 流水线不可用。** 其 `document_parser`/`text_chunker` 不存在、`add_chunks` 从不
   被调用，因此其「语义切片」描述不能作为算法参考；当前 `rag.py` 是三家唯一真实可检索的实现。
3. **上游 README 与源码不一致的清单**（不得作为采用理由）：
   - LearnMate：`01016188介绍/` 6 份文档与录屏/PPT **不存在**；「LangChain 多智能体框架」实际只用
     LangChain 做 Chroma 包装；「9 个 Agent」调度器只注册 7 个。
   - ZhiShu：「StateGraph 10 节点」实为 9；「9 个流式端点」实为 6；「15 个服务模块」实为 14；
     「13 表」实为 15；「指数退避」不存在。
4. **两家上游的测试都不覆盖编排或 RAG。** LearnMate 67 个测试函数全部不触及任何 Agent、orchestrator
   或 RAG；ZhiShu 106 个测试函数中 `test_api.py` 断言的是**不存在的路由**（`/api/v1/profile/{id}`、
   `/api/v1/path/{id}`），必然失败。因此本次验收只使用当前项目的测试结果。
5. **A 阶段发现的真实缺陷**（本次已修）：`CoordinatorWorkflow._execute_agents` 在同步执行分支用只含
   5 个键的 `task_state` **整体覆盖**了 `run()` 产出的完整状态，导致 `task_plan`、`selected_agents`、
   `intent` 等在 `execute=True` 时丢失。统一任务状态要求使其必须合并而不是替换。

## 3. 本次实施边界

**已实施**：统一任务状态补全与合并修复；确定性结构检查 + 来源检查两层校验；三类新资源类型
（`mind_map`/`code_case`/`video_script`）的结构化 Schema、提示词与校验；后端路径解锁与依赖校验；
前端类型与展示补齐。

**未实施**：数据库迁移（新资源类型复用 `Resource.type`，无需迁移）；第二套推荐/RAG/错题/路径表；
React/Next.js 页面移植；摄像头自习；代码沙箱；上游代码或提示词复制；任何无法复现的算法指标宣称。
