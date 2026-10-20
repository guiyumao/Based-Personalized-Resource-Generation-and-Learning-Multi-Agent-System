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

2026-10-20 AI 内容编排真实可用性修复（本轮）：根因是 agent_service 8002 仍在跑 P1-07 之前的旧代码，前端已热加载新导航但后端 `/admin/prompts`、`/admin/image-provider`、`/admin/resources/{id}/rewrite|sections|illustrations` 全部 404，表现为截图中的"提示词列表获取失败/Provider 状态失败/改写失败"。本轮：

- **部署修复**：按 `artifacts/local-start-20261019/start.ps1` 同款运行时 DB 与 env，重启 agent_service 8002（`--lifespan off`），openapi 已含全部 admin 路由；真实 HTTP 验证：`GET /admin/prompts`=200/11 模板、`GET /admin/image-provider`=blocked(未配置)、`GET /admin/resources/220/sections`=9 节、`POST rewrite`=blocked(未授权)、`POST illustrations`=blocked(未配置)。
- **提示词统一加载**：`_load_prompt_template` 三处 lru_cache 改为 `prompt_registry.load_prompt_template`（按 mtime 失效），管理员编辑后新生成任务无需重启即生效。
- **提示词版本生命周期**：`prompt_registry` 新增 `.history/` 文件式快照、`list/read/restore`；`/admin/prompts/{name}/versions[/{version}][/restore]` 路由 + 前端版本列表/恢复 UI。实测 save→1 版本→restore→2 版本闭环通过。
- **图片 Provider 状态细分**：`image_provider_status` 增加 `enabled/health` 字段与 `blocked/invalid/disabled/configured` 四态（未配置/配置不全/已停用/就绪），`PUT /admin/image-provider` 支持 `enabled`；无凭据时诚实返回 blocked 而非故障。
- **AI 改写付费闸门**：`rewrite_resource` 增加 `RUN_LIVE_LLM=1` 且 `DEEPSEEK_LIVE_PAID_ACK=1` 双闸门（INC-01 缓解），未授权返回 blocked"需要授权"，杜绝后台误触发真实付费调用（此前会因 `model_calls` 表缺失在台账 begin_call 处崩溃）。

状态：提示词列表/Provider 状态/章节读取/改写路由已 **LIVE_VERIFIED（接口真实可调用）**；改写真实模型调用仍 BLOCKED（无付费授权，符合预期）；图片生成后端未接入（blocked 为预期安全态）。未决：runtime.sqlite 缺 P1-06 台账表（`model_calls` 等 0030/0031），授权后改写/真实生成需先补齐该表；孤儿模板 coordinator/knowledge_graph/learner_profile/path_planning/qa 无生成消费方，待后续接线或移出白名单。单测 53 passed，Ruff 通过，前端 build 退出 0。
