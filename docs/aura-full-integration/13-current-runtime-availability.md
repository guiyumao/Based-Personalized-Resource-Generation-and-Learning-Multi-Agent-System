# 当前平台直接可用修复（2026-10-21）

本次交付目标是用户正在使用的5175/8002页面可操作。此前隔离验证不能证明当前运行服务可用。

## 根因与实际处理

1. 8002已加载新路由，但旧进程仍使用会导致知识任务统计500的旧代码。实际调用 `/admin/operations` 返回500，而 `/admin/usage` 为200、有18条LIVE台账；嵌套在概览v-if下的台账整个被隐藏。重载API并把面板移到独立区域，概览现200。
2. 旧Worker PID82280没有新注册逻辑，worker_instances/task_attempts均0。备份后更新Worker，最终PID79584，独立心跳ONLINE，实际本地产物任务出现SUCCEEDED执行尝试。
3. 本人旧课件指向原有无学科KnowledgePoint，工作区另造同名PERSONAL_DRAFT点，导致选择课件409。create_context现在优先复用本人旧资源对应的真实点ID；资源归属、版本及公私边界仍验证。原有资源候选也恢复可见。
4. 旧资源中心只显示导图列表，编辑器仅在工作区。现将MindmapEditor接入个人资源详情；新增 `/learning/resources/{id}/mindmap` GET/PUT及resource-history GET，只有本人可读写，保存仍执行版本CAS、单根/无环校验和ResourceRevision快照，不要求创建虚假学习计划。
5. 原预算只能依赖进程环境变量。新增 `/admin/model-budget` GET/PUT、页面保存入口和SystemConfig持久策略，每次模型调用从同一库读取，API/Worker无需为预算设置重启。0禁止新调用，留空不额外设限；环境更严上限仍生效。未擅自替用户选择消费额度，现保留未设限策略，由管理员页面配置。

## 当前可直接打开的入口

- 管理员：`http://127.0.0.1:5175/admin/tasks`，菜单“AI 与任务管理 → AI 用量与任务监控”。顶部显示Token台账、预算设置和独立Worker；下方任务的“查看”显示执行尝试。
- 学生：`http://127.0.0.1:5175/student/workspace`，选择计划/任务，再选择已有课件，显示“生成PPTX / 生成步骤动画 / 生成语音”。这些是原Worker上的本地任务，无需外部模型。
- 个人导图：`http://127.0.0.1:5175/student/resources`，打开本人思维导图详情，可以增删/改名/设置父节点/缩放/保存/读取历史。

登录身份决定可见数据；不会把某个验收账户的课件/上下文链接公开给其他账户。

## 当前环境与备份

真实8002和5175均指向 `artifacts/local-start-20261019/runtime.sqlite`；根目录learning_system.db是另一个旧数据库，先前只读缺表清单不适用于当前运行库。

先检查助手/知识队列无PENDING/RUNNING/CANCEL_REQUESTED、维护表为空，SQLite在线backup并quick_check成功后重载。最终8002 PID83068，Worker79584；其他六个服务/5175未重启。保留原进程内数据库目标和凭证环境，不将密钥写入启动参数/状态文件，不进行Alembic stamp/全库升级。`artifacts/local-start-20261019/processes.json` 的agent/worker PID已更新。

备份与启动记录在 `artifacts/aura-availability-20261021/activation*/{runtime-backup.sqlite,state.json,api.log,worker.log}`。多次API重载分别激活预算和后续旧资源/导图修复，最新activation-editor为API单独重载。备份包含用户数据，按本地数据库文件保管，不对外发送。

## 实际验证

- current-browser-final/result.json：真实5175页面、原8001/8002/8003和同一运行库，四组检查全部passed，pageErrors为空。不是隔离端口/受控Provider验收。
- 管理员LIVE台账读取18条，预算表单保存原策略并读回，Worker ONLINE。
- 使用现有本人课件生成3份实际本地产物，原Worker排队、执行、完成。PPTX浏览器下载并校验ZIP头，SVG截图两帧不同，WAV加载/时长/播放时间推进通过；执行尝试表可读。原课件正文未修改。
- 在实际库新增唯一私有“导图编辑验收示例”，来源标LOCAL_ACCEPTANCE_TEMPLATE；用它在资源中心编辑、保存版本、读取历史及API再次读回，未用模型生成，未覆盖用户原导图。此示例不是正式知识或模型生成效果证据。
- Provider调用计数前后均18，本次实际付费调用0。台账5条旧usage不完整，因此总量保持UNKNOWN，另外显示已知小计；不伪造补齐历史usage或金额。
- unit：12 passed；context-fix：19 passed；regression：32 passed；direct-editor：5 passed。批次有重叠，不相加为去重总数。零预算阻断、权限、环境上限不可放宽及旧版本409均有单元证据。
- build-final-verified.log：TypeScript/Vite退出0，3.72秒；同时修正normalizeMermaidSource未使用变量造成的现有构建失败。相关Python Ruff通过，未声称整仓全站回归。
- 原始失败保留：current-browser-v1旧资源409；v2过渡期多个ONLINE严格定位失败；v3测试错误地只接受200而创建接口实际201。修正实现/测试后final通过。

## 代码位置

`common/learning_context.py`：旧资源知识点复用；`common/model_usage.py`：读取持久预算；`services/agent_service/app/api/routes/model_usage.py`：预算API/审计；`resource_revisions.py`：资源中心导图API；`main.py`：注册；`UsageWorkerPanel.vue`：预算表单；`TaskOperationsPanel.vue`：面板脱离500概览；`adminNavigation.ts`：可发现的菜单；`MindmapEditor.vue`：资源ID入口及保存后重读；`student/ResourceView.vue`：本人导图编辑器；`normalizeMermaidSource.ts`：构建修复；`scripts/activate_current_operations.py`：先校验/备份再重载指定API/Worker；新增对应单元和当前平台浏览器验收脚本。没有自动提交或重置其他工作树改动。

这些入口现已在当前本地平台激活。公网/其他浏览器指向不同服务地址的部署不在本次结论内；其余全功能缺口仍按12报告继续，不能扩大成全部融合完成。
