# 数据库迁移与兼容边界

## 当前head0031与共享只读核查

0030接0029新增model_calls/worker_instances/task_attempts；0031接0030新增resource_artifacts/resource_revisions。隔离migration-final验证空库至0031、0031→0028→0027→0031，旧用户笔记保留；migration-v1另验证0029↔0031。降级会丢弃新增账本/产物/快照数据，不是无损业务回滚。共享learning_system.db只读审计无Alembic版本记录，缺13表及9张旧表字段；不得直接stamp head或按0029假定升级。脚本 `python -m scripts.audit_shared_schema --output artifacts/aura-ops-20261020/shared-schema-readonly.json` 仅读schema，不读取业务行/迁移。完整差异与后续限制见12。以下保留较早演练历史。

## P1增量0028/0029

原0026有效活动、同期0027文档元数据保留。0028以0027为父，新增learning_contexts/context_exercises与study_notes三个可空来源字段；0029以0028为父新增learning_knowledge_gaps。两项不回填历史私有来源，不重写已有计划。`tests/e2e/learning_context_migration.py`在隔离空库验证head0029及0029→0028→0027→0029，原用户与笔记正文保留；降级会丢弃这两版本新增的绑定/缺口数据，不能当作无损业务回滚。共享SQLite基线未审计，未迁移或修改其alembic_version。证据artifacts/aura-p1-20261020/migration-v1/migration-result.json。

本轮新增 `alembic/versions/20261020_0026_study_activity.py`，上接 `20261019_0025`。仅新建两表，不修改/删除历史用户、计划、资源、知识内容。

| 表 | 关键结构 | 用途 |
|---|---|---|
| study_sessions | user_id主键及users外键、tab_id、sequence、revision、active、heartbeat_at | 同一用户跨标签/设备的唯一活动游标；UPDATE WHERE revision实现CAS |
| study_activities | id、user_id外键、started_at、ended_at、page，用户/起止索引 | 只保存已计入的服务端连续活动区间 |

模型位于 `common/models/learning.py`。路径提案、每日分钟约束、path_revision和最近已应用ID复用LearningPath.path_data_json，无新计划表。`commit_path_update`条件检查身份、active和revision，避免并发完成/确认覆盖。

## 本轮实际迁移演练

证据：`artifacts/aura-full-integration-20261020/migration-v3/`。空隔离SQLite升级至0026 → 插入隔离用户/活动 → downgrade0025 → 检查两表删除且用户保留 → upgrade0026 → 保留用户 → upgrade当前head成功。演练时工作区另有独立0027文档迁移，因此最终head记录为0027；没有把它算成本轮实现。

第一次调用采用了不可导入的tests.e2e模块路径（未执行迁移）；第二次空库升级到新出现的0027后，固定0026的断言失败。已改为明确演练本轮revision，再检验当前head，第三次通过。失败日志保留，不覆盖。

## 运行库尚未部署

本轮没有在共享历史SQLite、`artifacts/local-start-20261019/runtime.sqlite`执行迁移，也没有自动stamp、create_all或重启正在运行的业务服务。已有历史基线未知的问题仍需解决。

在可信、已版本化且备份的独立目标库，设置DATABASE_URL后可用 `python -m alembic upgrade head`；不得直接将该命令用于未知基线的共享库。已有数据库需先审计当前版本、schema与0027等其他变更，制定基线/备份后再执行上线。不要为本功能修改全链历史降级。

0026降级会删除新活动记录，应在维护窗口导出需要保留的数据；本轮只在隔离测试库降级。PostgreSQL和共享运行库升级未验证。
