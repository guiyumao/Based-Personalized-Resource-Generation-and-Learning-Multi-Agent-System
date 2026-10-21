# 项目长期约定

## 知识库补建策略（2026-10-21 决策）

- 学生触发的知识构建不再等待管理员：公共知识库缺学科/知识点/已发布内容时，生成的草稿**直接自动入库**（建 SystemSubject/KnowledgePoint + 发布 KnowledgeVersion + 索引），并标记 `license_name=AI_GENERATED`、正文注明「AI 自动构建，管理员可修订/下架」。
- 入库失败（索引不可用等）必须回滚新建的目录行，退回个人草稿模式，不污染公共目录。
- 约定：相关单测中 `plan_knowledge.KNOWLEDGE_ROOT` 若被夹具指向 tmp_path，需指回运行时根才能验证端到端「发布→检索命中」；测试需自行清理 `auto_*` 学科码产生的行。
- 事务约定：SQL/语料文件/Chroma 无法原子提交，自动入库必须走「写锁 → 复用检查 → 发布 → 版本级校验 → 失败补偿（DB→文件→索引→reconcile）→ 补偿失败写 AuditLog ERROR 并排队 RECONCILE_PUBLICATIONS」。返回 `{"ok":False,"reason":...}` 而不是伪成功。
- 状态约定：`AUTO_APPROVED` = AI 自动生成并自动发布（未经人工审核），必须与人工 `APPROVED` 区分；语料头写「来源类型: ai_generated_auto_published」。管理员下架（WITHDRAWN）/驳回（REJECTED）的知识不得被自动补建。
- 测试约定：完整 unit 存在 20 个失败（vulnerability_policy 11 / resource_type_integration 6 / teaching_migration_repair 2 / knowledge_lock 1），经对照基线取证来自用户其他未提交改动，不是自动入库引入。
