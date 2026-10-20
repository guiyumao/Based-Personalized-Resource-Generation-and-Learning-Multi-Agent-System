# 管理功能融合差异矩阵

2026-10-20。上游核验提交 `5923cf6cd766a58b112f24f02371bb87da1fa904`，MIT；本地源码位于 `artifacts/aura-full-integration-20261020/reference`。状态按实际执行证据更新，旧测试不等于本轮验收。

| 功能 | 参考实现（相对上游根） | 当前实现 | 缺失内容 | 融合方式 | 验收状态 |
|---|---|---|---|---|---|
| 管理首页 | Vue-frontend/src/views/admin/AdminDashboard.vue → Java-backend/src/main/java/com/learning/controller/AdminDashboardController.java | system_service/app/api/routes/admin.py、views/admin/overview.vue | AI/知识增长趋势、下钻 | 扩展现有统计查询 | PARTIAL |
| 用户管理 | UserManagement.vue → AdminUserController.java | system_service admin、user_service users、views/admin/users.vue | 批量管理、编辑完整性 | 复用账户和即时角色验证 | PARTIAL |
| 文档知识库 | KBManagement.vue → api/kb.ts → KnowledgeBaseController/KnowledgeBaseService、Python-backend KB 路由 | knowledge_documents Service/API、KnowledgeDocumentManager.vue | 大文件异步解析、OCR、原生DOCX预览、复杂归档/删除未完成 | 原语料目录适配 + 原件/正文/来源/分类/Chunk/版本审核记录 | PARTIAL；核心链 TESTED_ISOLATED，见docs/aura-full-integration/10 |
| 学科与知识库 | 上游 KB collection/doc metadata | SystemSubject、KnowledgePoint、knowledge_documents.py、subjects.vue | preflight实时Chroma匹配尚未查询 | 显式多点关联；活动审核版本和索引清单覆盖；不按相似名合并 | PARTIAL；关联/覆盖 TESTED_ISOLATED |
| 知识审核发布 | AdminResourceService approve/reject、KB ingest | knowledge_candidates/versions/tasks、knowledge_publication.py、Worker | 共享激活、长期压力、跨数据库验收未完成 | 原队列发布/撤回/对账；数据库有效版本读取门禁；修订/回滚/崩溃接管 | PARTIAL；真实Chroma HTTP及浏览器 TESTED_ISOLATED |
| AI补充资源 | ResourceManagement.vue → api/adminResource.ts → AdminResourceController/Service、Python admin_resource | assistant_tasks/coordinator、resource_service、views/admin/resources.vue | 专用生成编辑、优化、改写、图片适配 | 扩展现有任务和资源；图片需Provider | PARTIAL |
| Token分析 | TokenAnalysis.vue → AdminTokenController → AiTokenUsageService/Mapper | knowledge_budget、knowledge_tasks usage、AI performance日志 | 覆盖全模型持久账本、筛选图表 | UNKNOWN与实测usage分开；后端预算 | MISSING |
| 系统日志 | LogManagement.vue → AdminDashboardController logs/page/stats/trend/hourly | AuditLog、system_service logs、views/admin/logs.vue | 趋势/关联ID/异常排行 | 现有审计表扩展 | PARTIAL |
| Worker | 上游异步资源处理 | assistant_worker、knowledge_worker、tasks.vue | 跨Worker健康、执行时长汇总 | 原队列/租约为准 | PARTIAL |
| 全局A—H联动 | 参考业务链，非逐项等价 | 本地多个既有流程 | 完整跨模块E2E与学生端回归 | 隔离数据库/Chroma/本机Mock Provider | NOT_TESTED |

后端路径省略前缀 `services/`，前端页面省略 `web-app/src/`。Java控制器位于同一 `com/learning/controller` 目录，Service位于相邻 service 目录。当前不宣称全部融合完成。共享库、线上索引和付费Provider不在本轮测试写入范围。

2026-10-20续接：文档专项证据 `artifacts/aura-full-integration-20261020/documents-browser-v9/`；当前单步迁移演练升级至head0029，保留同期0028/0029改动。IMPLEMENTED不等于TESTED_ISOLATED，更不等于LIVE_VERIFIED。共享运行未激活，其他功能仍按原状态列出。
