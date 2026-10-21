# 笔记历史、分类与闪卡证据（2026-10-21）

在当前平台直接可用修复之后继续P1-09，已把本批功能接入实际5175/8001运行环境。用户服务最终重载PID45480；实际库仍为 `artifacts/local-start-20261019/runtime.sqlite`，未换库或覆盖其他会话的学情修复。

## 可操作内容

- 学生进入 `/student/study-tools`“笔记与闪卡”：按标题/正文搜索，按实际学科名称、资源ID、知识点ID筛选。分类从本人LearningContext/Resource/KnowledgePoint及计划读取；无法确认的旧笔记显示未分类，不用模型猜测。
- 笔记记录摘录位置、来源版本。每次保存追加不可变快照；历史可以查看并把旧正文放回编辑器，由用户检查后保存。新增expected_version校验及SQL比较更新，旧标签页不能覆盖新正文。旧笔记从首次接入后的保存开始记录，不补造更早的修改。
- 从关联笔记创建闪卡时，服务端继承知识点、来源资源SHA及上下文，客户端不能随意改写归属。无来源的手动闪卡保留原功能，不凭问题文字认定知识点。
- 复习仍使用原到期/间隔算法；新增请求回执及SQL比较更新，同一请求重放不增加次数。复习事件、卡片调度、画像自评摘要和有效上下文对应任务证据同事务提交；冲突全部回滚。
- 自评记住率存入独立 `mastery_json.flashcard_review`，不改写习题评分、正式知识点掌握度或完成状态。任务/资源变化后旧卡可继续私人复习，但不把证据写入已变化的计划。删除闪卡重算仍存在的复习统计，删除笔记同时清除其历史并保留原有闪卡。
- 用户服务增加请求追踪，使笔记AI整理调用可以关联认证用户与功能，支持已有每用户调用预算。真实AI整理未在本轮调用，只用受控模型验证归属与响应。

## 修改位置

| 文件 | 作用 |
|---|---|
| common/models/study.py；common/models/__init__.py | NoteRevision、CardKnowledgeBinding、CardReviewReceipt及注册 |
| alembic/versions/20261021_0033_note_card_evidence.py | 接0032，仅新增三表，不重写旧用户/笔记/卡片 |
| common/study_evidence.py | 真实来源分类、快照、闪卡绑定、分离自评及任务证据 |
| services/user_service/app/api/routes/study_tools.py | 搜索/分类/历史、版本保护、私有来源检查、复习回执和原子更新 |
| services/user_service/app/services/learning_content_profile.py | 学习画像返回独立flashcard_review_evidence，不混入习题统计 |
| services/user_service/app/main.py | 认证用户请求追踪 |
| web-app/src/views/student/StudyToolsView.vue | 筛选、来源定位/版本、历史查看与加载、闪卡知识点/自评展示及重放ID |
| scripts/activate_study_tools.py | 备份、运行库副本演练、只加所需表/可空兼容列、仅重载8001 |
| scripts/audit_shared_schema.py；tests/e2e/learning_context_migration.py；operations_migration.py | 跟随实际Alembic head，避免0031固定断言误报 |
| tests/unit/test_study_evidence.py | 历史/版本/权限/归属/重放/画像与任务事务/失败回滚/调用归属 |
| tests/unit/test_coordinator.py；test_learning_workspace.py；test_teaching_migration_repair.py | 更新同期生产契约：subject参数、未归属临时题掌握度UNKNOWN及实际迁移head；不放宽生产门禁 |
| tests/e2e/study_evidence_migration.py；current_study_launcher.py；verify_current_study.mjs | 迁移保留旧数据及当前平台浏览器验收 |

## 当前库兼容与部署

当前实际库的study_notes缺少0028原应新增的learning_context_id/source_resource_version/source_locator，第一次真实保存500由此暴露。不是把三张新表建好就算笔记已可用。

先保存新的SQLite backup并quick_check，再在副本上新增三张表及上述三个可空列，验证旧用户/笔记/卡片行数不变，然后对当前库执行同样的兼容增量。没有运行全库Alembic upgrade/stamp，没有删除旧列、恢复旧备份覆盖运行库或重启其他服务。记录在 `artifacts/aura-study-20261021/activation*`；副本及备份含本地用户数据，不向外发送。

## 验证与证据

证据根 `artifacts/aura-study-20261021/`，测试批次有重叠，不能相加为去重总数。

- `global-unit-final`：681 passed /2526 warnings，191.04秒，退出0。此前全量677 passed /4 failed：测试假服务缺subject参数、两项未归属临时题错误期待非空掌握度、迁移固定期待0032。修正测试契约后22项定向通过，随后全量通过。
- 用户服务追踪为随后追加改动；`attribution-fixed`为7 passed /83 warnings，包含真实JWT认证后模型边界的用户/功能归属。首次该测试因测试文件漏import json失败，修正后通过；没有把失败藏成生产成功。
- `migration/result.json`：0032→0033→0032→0033，旧用户及笔记保留；`context-migration`：空库到0033及回退0028/0027后再到head，旧记录保留。
- `current-browser-final/result.json`：真实5175/8001/8002与当前运行库，笔记分类/资源/摘录/保存/两版历史、旧版本409；笔记→闪卡知识点绑定→复习→到期→请求重放只有一次事件→页面自评统计，两组均passed，pageErrors为空。截图已实际复核；历史对话框补等待过渡动画后重新拍摄。
- 浏览器使用明确标记的私有账号 `local-study-acceptance-20261021` 和本地验收材料，没有给真实学习用户灌入自评分数；这些是功能测试数据，不是模型内容或真实学生表现证据。示例数据未自动删除，以便保留读回链。
- `current-readback.json`：用户服务健康200且有X-Request-ID；model_calls仍18，本轮付费调用0。三张证据表实际存在且有数据。未点击真实AI整理或其他付费能力。
- 前端 `build-v1.log`：TypeScript/Vite退出0，21.82秒。相关Python Ruff通过；没有把这项构建当作全站性能指标。

## 范围与恢复位置

本批完成笔记历史/真实来源分类、新闪卡来源与自评/任务证据。旧闪卡不自动补造归属；卡片仅绑定单一来源笔记；筛选学科按真实名称精确匹配。当前留存版本最多展示最近100项，原始快照不会因列表限额自动删除。

P1-07管理员AI改写/图文编排的完整业务验收、视频URL验证、全部资源类型版本历史、18项/A–E全场景及公网部署仍不能宣称完成。下一步先核对同期Prompt/图文/分章课件提交，复用原Coordinator/Worker继续；不要覆盖其他会话的已完成学情归属修复，也不要再次把已有台账/心跳/本地产物当作空白重做。
