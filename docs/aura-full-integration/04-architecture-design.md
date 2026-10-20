# 增量架构与恢复位置

## 当前P1架构

LearningContext持久绑定user→LearningPath→stage_id/task_id→KnowledgePoint→Resource/SHA版本；ContextExercise绑定生成题与助手任务，StudyNote保存同一上下文及来源版本。common/learning_context.py由agent、user、evaluation共同复用；评分回执/作答/画像/任务证据同事务CAS。正式计划入口由plan_knowledge.py核验有效发布文件与当前Chroma片段，缺口进入LearningKnowledgeGap和原Knowledge Worker受控队列；模型生成后和草案确认时复核。图谱读操作不排模型，私有快照不入公共关系。下一步从11列出的P1-06逐调用台账与Worker事件开始，后续功能继续绑定这套上下文。

沿用用户服务（身份/画像/笔记闪卡）、智能体服务（Coordinator/路径/持久任务）、资源服务（保存/审核/导出）、评价服务（作答/报告/行为聚合）及原知识库。没有复制上游框架或新增第二份用户/画像/计划数据库。

## 本轮已实现的数据链

```text
真实浏览器输入 + 页面焦点/可见性
 → evaluation/activity/heartbeat（身份来自JWT）
 → StudySession单用户CAS游标 + StudyActivity区间（同一事务）
 → learning_analytics（北京时间归日）
 → 首页overview与报告有效活动时长

AnswerRecord → Exercise → KnowledgePoint
 → path_adaptation（近30天、本计划知识点、至少3次判分、正确率<60%）
 → LearningPath JSON中保存提案（不改任务）
 → 用户预览并确认
 → JSON revision条件更新、追加后续练习、保存提案ID防重放
 → overview/analytics读取同一份计划任务
```

掌握率和近期练习正确率保持区分。3次判分是建议门槛，不是高置信度能力诊断；首页不足5次显示样本不足。新补强练习要由用户进入现有流程生成/作答，不因确认提案直接发送付费调用。

活动是受限的浏览器活动估计，不是防作弊计时。伪造客户端active仍可能报告活动；服务端只保证时间受界、去重、所有权和事务一致。无操作观看视频/音频暂不计入，需要后续专用播放事件协议。

## 后续优先顺序（尚未实现）

1. 审完 `graph.py` / `neo4j_connector.py` 匿名、私有资源和后台模型费用边界；测试应先证明匿名无法触发代价操作、另一学生草稿不能成为共享图谱来源。
2. `LearningPathView.vue`、`studentWorkspace.ts`、`AssistantPet.vue`、`assistant_tasks.py` 与 Resource 之间建立服务端 plan/module/resource/kp 上下文；再做三栏工作区。
3. `common/schemas/agent.py`、Coordinator与知识检索链中补齐生成前学科/目标知识点/覆盖率校验，缺口进入原KnowledgeBuildTask，不伪造知识库完整。
4. 新资源类型沿 AssistantTask 执行代次/取消写屏障接入；先实现结构化导图编辑、视频发现，再做安全动画模板、真实PPTX与TTS；外部服务没有授权时只验证协议与状态。
5. 接续独立文档0027变更的真实上传、原文件预览、解析、审核、索引验证；管理员Token/Worker监控使用真实账本。
6. 最后跑场景A–E、全路由权限、全站浏览器和真实外部服务有限验收。现有首轮结果不能替代这些标准。

跨服务仍共用当前既有数据库。线上基线、PostgreSQL JSON CAS兼容、读写并发压力和长期区间保留策略尚待验证。

## 文档发布专项续接（2026-10-20）
文档原件在originals、审核草稿在原候选表，复用Knowledge Worker的PUBLISH_CANDIDATE/RECONCILE_PUBLICATIONS。SQL活动版本授权每次RAG/缓存/单篇详情/生成上下文读取；Chroma孤立写入不能直接公开。确定路径重放、知识锁、执行权写屏障与SQL异常补偿配合对账恢复，非跨存储原子事务。详见10-knowledge-publication-acceptance.md。共享环境未激活。
