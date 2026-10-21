# 管理员数据看板重构交付（2026-10-21）

## 范围和结果

在现有 `/admin` 页面实现参考图的四项 KPI、12 栅格分析区、模型/工具折线面积图及环图、Worker 状态分布、预算/Token 柱线图、任务堆叠柱图和最近六条任务。保留左侧菜单、顶部菜单、管理员路由及权限。页面使用现有 Vue 3、Element Plus、Axios 与 FastAPI/SQLAlchemy；ECharts 按模块引入 Canvas、折线、柱图、环图、图例、Tooltip 和可访问性组件。

已实现 7/30/90 天、自定义 UTC 自然日范围、按日/每7天聚合、图例显隐、点击趋势/环图/任务柱进入筛选明细、PNG/CSV 导出、刷新和最后更新时间。请求取消避免过期响应覆盖；各数据源独立报错，失败清除旧指标，不用假数据代替。支持 Skeleton、空记录状态、超时后的手动重试。未启用定时轮询。

完整调用记录在抽屉内保留搜索、日期、环境、请求模型、功能、类别、状态、分页、元数据查看和更多分组统计。任务抽屉保留原始状态、中文状态、创建/开始/完成、重试、心跳、安全错误代码、阶段及执行尝试，显示已持久化且归属匹配的资源成果。Worker 抽屉显示完整注册字段及待核查筛选。

原平台账号/路径/资源/作答统计、管理快捷入口及整个原有 TaskOperationsPanel 通过折叠区保留，按需挂载原有运营面板。原 `/admin/tasks` 入口继续使用原组件。预算配置仍由原服务持久保存，并保留环境限额优先的规则。

原助手组件嵌入顶栏预留槽位，数据看板显示紧凑按钮；其他页面仍可拖动。保留原会话、附件和任务功能。悬浮按钮与展开面板 Teleport 到 body，避免顶栏/侧栏的定位与堆叠上下文遮挡；顶栏使用原主题实色背景。

## 实际数据来源和口径

| 内容 | 数据与规则 |
| --- | --- |
| 调用与 Token | `ModelCall` 逐次持久台账；时间以 started_at 为准，每次真实尝试计一次，包含失败。LIVE/TEST 分开，不回填历史数据。 |
| 模型和工具 | `provider=deepseek-tools` 为现有工具网关记录；其他为模型。模型按请求 model 分组，response_model 在明细单列，账单模型不推断。不能仅凭 model 名称 search/fetch 分类。 |
| 今日 KPI | UTC 今日截至查询时刻的模型+工具尝试，分别展示二者数量；昨日比较同一 UTC 时刻，昨日为0时不算虚假增长率。 |
| Token | 模型输入/输出的已知小计，未知单独提示，失败调用的已知用量计入；cached_input_tokens 已包含在输入中，不重复求和。工具 Token 不适用的记录不混入模型 Token 完整度。 |
| 任务 | `AssistantTask` 与 `KnowledgeBuildTask` 按 created_at 归属所选周期；每个表内任务 ID 计一次，不 join 执行尝试或智能体阶段。不同持久任务（含知识子任务）各计一次，课件/习题是助手任务类型，不再重复累计独立计数。 |
| 成功率 | SUCCEEDED/COMPLETED 映射为成功；FAILED 为失败；分母为成功+失败。RUNNING/CANCEL_REQUESTED、PENDING/QUEUED、CANCELLED 分别归为执行中、等待、取消。未知原始状态显示其他。与前一个同长度创建周期比较百分点。 |
| Worker | `WorkerInstance` 实时心跳；沿用超过 max(15秒, 心跳间隔×3) 为 STALE、错误代码为 DEGRADED、正常运行为 ONLINE。在线分母排除 STOPPED；展示全部已登记状态分布。STALE 只标待核查，不宣称系统故障。迷你柱为最近注册的当前状态快照，不伪造历史在线率。 |
| 日预算 | 原 `KnowledgeBudgetCounter` 的 `model-day:环境:UTC日期` 预留量与 `effective_call_limits`。未配置显示“未配置预算上限”，0 显示禁止新调用，不虚构百分比。 |
| 工具预算预留 | 原 day/month 知识预算计数单独保留在运营明细中；不是工具完成次数，不和逐次工具台账相加。 |

调用统计和调用明细共用日期边界（包含起始日00:00、不包含结束日次日00:00）。缺记录的自然日填零。任务无环境字段，因此明示统计全部持久任务，不能按模型环境臆造隔离。预算图调用柱含模型+工具尝试，Token 柱只含模型；预算上限线只是当前配置参考，历史预算变更未知。无可靠费率/账单时不展示人民币或美元费用。

## 接口

全部接口沿用 `require_role('admin')`，无新增表、迁移或共享业务数据修复。

| 接口 | 变动 |
| --- | --- |
| `GET /admin/dashboard` | 新增 SQL 聚合：日期、趋势、模型/工具分布、今日比较、任务状态、成功率及上一周期；查询数不会随日数线性增长。 |
| `GET /admin/usage` | 保持原滚动 days 兼容；可选 start/end、字面搜索、call_type，原模型/功能/状态/用户/供应商及分页保留。 |
| `GET /admin/usage/export` | 新增同筛选 CSV；最多50,000条，超出要求缩小日期；防公式注入，不包含 Prompt 或凭证。 |
| `GET /admin/operations/tasks` | 新增跨两类持久任务的筛选分页列表，按类型/业务操作/统一状态筛选。 |
| `GET /admin/operations/tasks/{kind}/{id}` | 复用阶段和执行尝试；新增经过归属核验的资源成果元数据，不直接暴露任意 result_json。 |
| `GET /admin/workers` | 复用心跳语义；取消旧100条截断，返回注册总量、有效分母和状态分布。 |
| `GET/PUT /admin/model-budget` | 复用设置保存；GET 增加环境日预留量，原 configured/effective 不变。 |
| `GET /admin/operations` | 原接口及预算预留/每日任务等能力保留。 |

## 实际改动文件

- `web-app/src/views/admin/overview.vue`：接入新看板，保留原统计和运营折叠区。
- `web-app/src/components/admin/dashboard/OperationsDashboard.vue`：统一范围、并发读取及联动。
- 同目录 `DashboardChart.vue`、`charts.ts`：按需注册 ECharts、统一风格/时间/枚举、ResizeObserver、dispose、PNG。
- 同目录 `DashboardKpiCards.vue`、`WorkerHealthPanel.vue`：KPI、Worker 面板及完整注册抽屉。
- 同目录 `CallRecordDetails.vue`、`TaskRecordDetails.vue`：完整调用及任务记录抽屉。
- 同目录 `dashboard.css`：布局、卡片和五种宽度响应式。
- `web-app/src/layouts/AppLayout.vue`、`web-app/src/components/AppTopbar.vue`、`web-app/src/components/AssistantPet.vue`：助手预留位置及看板页头去重。
- `web-app/package.json`、`web-app/package-lock.json`：新增 ECharts，保留已存在的其他依赖改动。
- `services/agent_service/app/services/dashboard_statistics.py`：日期、调用分类与任务聚合。
- `services/agent_service/app/api/routes/model_usage.py`、`operations.py`：增量接口。
- `tests/unit/test_admin_dashboard.py`：统计与权限边界测试。
- `scripts/verify_admin_dashboard.py`、`tests/e2e/run-admin-dashboard.mjs`：真实库备份及现有服务浏览器验收，凭证只经内存传递。
- `DEV_STATE.md` 和本文：精简交接与交付依据。

## 已执行验证

1. 隔离无费用测试：`test_admin_dashboard.py`、`test_operational_ledger.py`、`test_admin_operations_p1.py` 组合 **18 passed / 106 warnings**，证据 `artifacts/admin-dashboard-20261021/unit-final/command.log`。覆盖日期半开区间、零日补齐、请求/响应模型分离、真实工具分类、失败及缺失 Token、缓存不重复、任务去重/分母、同长度比较、空态、非法范围、预算未配/0、超过100条 Worker、字面搜索、分页、CSV一致性与公式防护、匿名/教师拒绝、查询数不随7→90天增加。warnings 为现有生命周期和 naive UTC 弃用提示。
2. 新增及修改后端文件 Ruff 全部通过；修改文件 `git diff --check` 通过。
3. 前端 `npm run build` 通过，最终日志 `artifacts/admin-dashboard-20261021/build-final-verified.log`；有既存 vis-network 注释、分块大小与 overview 静态/动态导入提示。
4. 真实运行库 SQLite backup 副本上的 Chromium 验收通过；无种子/拦截成功响应假数据。证据 `real-snapshot-browser-final-v3/result.json`。
5. 现有 5175→8002 登录管理员上下文真实端到端验收通过；记录在 `activation/` 的各轮 browser 目录，最终以 `delivery-live-browser-v3/result.json` 为准。覆盖五种屏幕、四张KPI/六个面板、聚合与明细一致、7/30/90及自定义自然日、真实图表点/图例显隐、任务柱筛选、模型与工具、周聚合、导出、Worker和任务抽屉、503部分故障/清空/重试。旧任务页悬浮助手、顶栏助手展开/关闭及视口内定位也已通过。成功响应来自实际 API；只有故障用浏览器503注入。
6. 验收五种尺寸：1920×1080、1440×900、1366×768、820×1180、390×844，页面与 app-content 均无横向溢出。截图在对应验收目录，已人工查看桌面及手机截图。

## 现有运行环境

激活前验证实际数据库 `artifacts/local-start-20261019/runtime.sqlite`、quick_check=ok；无等待/运行中助手和知识任务、无维护计划，七服务健康。通过已有 `activate_current_operations.py --api-only` 备份数据库，仅重载8002（PID49204→10616，lifespan off），Worker20348及其他服务保留。备份/进程证据 `artifacts/admin-dashboard-20261021/activation/`。真实模型/工具台账验收前后均104条，无新增 Provider 请求、无迁移、无自动提交。

## 尚未支持及验收边界

- 历史预算配置、供应商账单/真实金额、未接入台账前历史调用及完整 Worker 历史在线序列不存在可靠来源；明确显示未知或当前参考，未造数据。
- 仅展示原服务已持久化并可安全披露的阶段/执行尝试/错误代码与资源关联；未输出未脱敏原始日志、Prompt、任意任务结果或不存在的成果关系。
- CSV有50,000条上限；大规模性能压测、长时间内存分析、真实第三方付费调用及全站回归不在此次通过声明内。
- P2个性化布局、自定义指标和自定义综合报表未实现。
- 本次是管理员数据看板的交付，不代表项目其他融合事项全部完成。源工作区其他未提交改动保留。

图表模块化引入方式参考 [Apache ECharts 官方文档](https://echarts.apache.org/handbook/en/basics/import/)。
