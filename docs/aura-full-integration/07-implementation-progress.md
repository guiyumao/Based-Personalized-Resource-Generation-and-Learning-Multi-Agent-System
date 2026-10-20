# 实现进度与接续点

## 最新P1恢复入口（覆盖下方首轮下一步）

已实际补图谱核心边界、持久学习上下文、三栏文本/练习工作区、正式知识驱动计划准入和缺口管理，并复用0027真实文档/Worker/Chroma链。管理员已增加持久任务状态/执行阶段/预算预留读取，完整Token台账和独立Worker心跳仍未实现。整体PARTIAL。当前代码文件/接口/工作包状态和恢复顺序见[11-p1-learning-context-checkpoint.md](11-p1-learning-context-checkpoint.md)。根目录GRAPH_SECURITY_FIX_REPORT.md记录图谱修复与历史来源边界。最新证据artifacts/aura-p1-20261020，原目录和同期文档专项保留，未重启共享服务或执行真实模型调用。

更新：2026-10-20。总体状态：**未完成，非全功能融合交付**。已直接修改实际前后端与迁移，不止生成计划。

## 本轮已完成并隔离验收的子闭环

1. 首页聚合真实活动/路径/到期复习/本人资源/作答薄弱项；新账户空状态、后端503独立失败状态，数据不伪造。
2. 浏览器操作 → 带JWT心跳 → 服务端CAS去重/同事务区间 → 日/自然周统计 → 首页和报告。午夜切分、重放、跨标签、并发、存储失败、缺迁移均有测试。
3. 分析完成率改为读取LearningPathService实际写的JSON任务；计划页也按任务计算，旧无stages路径才回退LearningTask，避免重复计数。
4. 本人作答 → 本计划知识点证据 → 保存提案 → 显示前后差异 → 明确确认 → 追加后续补强任务 → 新统计读回。支持可用分钟调整、幂等确认和并发过期拒绝；没有修改已有任务和知识库。

## 关键新增/修改文件

- 后端：`common/models/learning.py`（仅本轮StudySession/Activity部分）；`alembic/versions/20261020_0026_study_activity.py`；evaluation服务 `study_activity.py`、`learning_analytics.py`、`api/routes/reports.py`；agent服务 `path_adaptation.py`、`learning_path.py`、`api/routes/learning.py`。
- 前端：`useStudyActivity.ts`、`AppLayout.vue`、`LearningOverviewPanel.vue`、`PlanAdaptationPanel.vue`；学生 DashboardView / LearningPathView / ExerciseView / ReportView。
- 测试：`test_study_activity.py`、`test_path_adaptation.py`；原先修策略测试的内存FakeDb改为显式隔离持久化，真实CAS在新SQLite测试验证；`study_activity_migration.py`、`study_overview_runtime.py`、`run-study-overview.mjs`。
- 文档：本目录01–09；运行和失败证据在 `artifacts/aura-full-integration-20261020/`。

## 未完成事项（准确恢复顺序）

- 补完参考与当前系统的逐项源码审计；03矩阵只覆盖24组，未完成所有原子需求核验。
- 优先处理图谱鉴权/私有资源/模型费用边界，再构建plan/module/resource/kp服务端上下文和三栏学习工作区；文件位置见04。
- 知识库驱动计划：前置覆盖校验、缺失知识点建设与审核联动，不能只依赖模型生成。
- 统一Resource与计划模块/任务/版本关联；完整导图交互、视频发现、动画、TTS、PPTX和对应Worker写屏障。
- 笔记分类/摘录定位、闪卡知识点证据与掌握度、题型/难度分析、统一画像推荐。
- 审完工作区独立的文档0027代码，不覆盖；管理端Token/任务/Worker监控尚未补。
- 场景A–E、全部18项强制标准、全站权限/组件/E2E/性能、真实Chroma和有限外部模型仍未验收。
- 共享数据库上线和旧服务激活未执行；本轮浏览器测试创建的独立监听器已在finally关闭，原8001–8007/5175未操作。

恢复时先读本文件、09、DEV_STATE及实际Git变化；复用已克隆的固定上游，针对下一项定位，不重复全仓库扫描。测试命令见08，付费验证仍须新的明确预算授权。

## 文档工作包续接完成项（2026-10-20）
文档上传→分类→审核→独立Worker发布→真实Chroma→学生检索，以及修订替换/回滚/撤回、并发同键请求、硬退出后attempt2恢复，已TESTED_ISOLATED。前端增加版本审核记录、来源筛选、未送审归档、撤回及对账入口。课件生成通过本地LLM桩验证真实知识上下文及版本引用持久化，未验收真实Provider。0009单步降级列归属修复与head0029隔离迁移通过。完整文件/接口/限制和失败记录见10；最新证据documents-browser-v9、migration-resume-v2、resume-final-unit-v2。
本条只更新文档子闭环，不替代上方学生端/管理员AI资源/统一Token预算/Worker全量监控等未完成项。源码及隔离验收并未在共享8001–8007/5175部署。
