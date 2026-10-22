# 学生端与教师端统一通知系统验收记录

日期：2026-10-21，Asia/Shanghai。基于现有 Vue 3 / FastAPI 多服务项目增量实现；没有重建独立应用，没有静态业务消息。

## 实际交付

- 公共 AppTopbar 中使用同一个 NotificationCard。学生、教师各页面均默认收起；图标、文字、未读数构成小卡片，零未读隐藏数字。点击向下展开，再次点击、外部点击和 Escape 关闭，关闭不自动已读；支持原生键盘按钮、焦点恢复与减少动画偏好。
- 卡片每次读取最近8条，固定桌面宽度390px、视口内滚动；移动端宽度适配。消息中心每页20条，支持分页、仅看未读、全部已读、刷新和消息详情。原班级页默认展开的教学通知大面板已移除，其功能统一由公共卡片及消息中心承接。
- 管理员 `/admin/notifications` 发布通知；教师通过 `/teacher/notifications` 的发布表单向本人班级、课程、班级学生发送。学生消息中心为 `/student/notifications`。
- 消息详情先请求后端复核当前权限，再执行幂等已读。作业进入对应学生作业卡片或教师提交批改列表；讨论详情读取真实讨论和回复，并可调用原回复接口。学习任务链接打开本人原助手会话；学习计划消息进入原计划页。

## 审计与复用

原项目已有 Notification、Classroom、ClassEnrollment、Course、Assignment、AssignmentSubmission、DiscussionThread/Reply，原 `/learning/notifications` 列表与单条已读接口均保留。原通知局限于学生班级页，最多100条，无准确全量未读统计、分页消息中心及管理员发送。

复用8005教师服务处理教学通知、管理员发送和统一收件箱；复用 JWT/有效账号校验、教师课程归属校验、Vue Router、Pinia 和 Element Plus。已有助手 SSE 是单次问答流，并非跨服务通知订阅通道，因此通知采用共享数据库持久化加轻量轮询，不新增消息中间件。

## 数据模型与迁移

正式 Alembic `20261021_0034` 继承 `20261021_0033`：

- 在原 notifications 增加 sender_id、event_key、read_at，保留历史 id、正文及 is_read。
- `(user_id,event_key)` 唯一约束/索引用于事件去重；`(user_id,is_read,id)` 用于收件箱查询。
- notification_dispatches 保存发送者、请求幂等键、发送内容/范围及人数。相同请求重试返回原回执，不重复扩散；相同键不同内容返回422。
- 继续采用原来的每用户通知行，因此每条通知拥有独立已读状态。发送服务端重新解析有效接收人；单次超过5000人整体拒绝，不会部分发送，需按班级/课程拆分。

空库迁移至0033，0033→0034→0033→0034演练通过，历史消息正文和已读状态保留，见 `artifacts/notifications-20261021/migration/command.log`。

实际运行库无 Alembic 版本记录，本轮没有 stamp 或执行整库 upgrade。确认进程实际 DATABASE_URL、没有运行/排队任务后，用SQLite备份API保存 `runtime/before.sqlite`，在 `runtime/rehearsal.sqlite` 上演练本次迁移，再对实际库执行同一0034增量操作。SQLite使用新增列/索引，避免重建现有收件箱。integrity_check=ok，既有用户、资源、计划、笔记行数未改变。

## 接口

均基于现有8005，需有效 JWT：

|接口|用途|
|---|---|
|GET /learning/notifications|保留原列表契约|
|PATCH /learning/notifications/{id}/read|复用原单条已读，补充幂等read_at及当前权限检查|
|GET /learning/notifications/inbox?page=1&size=8&unread=false|分页、匹配范围总数、全量未读数量，size最大50|
|GET /learning/notifications/unread-count|当前账号有权接收的未读统计|
|POST /learning/notifications/read-all|仅标记当前账号当前合法范围内的通知|
|GET /learning/notifications/{id}/detail|检查收件人及业务当前权限，返回详情及服务端固定映射的站内目标|
|POST /learning/notifications/publish|管理员/教师按合法范围发送，返回真实人数与发送回执|

学生不能发布；教师不能跨课程发送或全体广播；客户端提交的用户列表不会被用作接收人依据。管理员可选择全体学生、全体教师、指定班级/课程/学生/教师。

## 实际业务接入

|事件|状态与事实|
|---|---|
|管理员公告、维护、账号及管理通知|已实现真实发布，角色/班级/课程/个人范围均由服务端解析|
|教师班级/课程/个人通知|已接入相同发布接口，限定本人管理范围|
|加入班级|复用原事件，补发送者及事件去重|
|发布作业|复用原业务事务，向当前班级学生发通知|
|学生提交/更新作业|新增教师通知，按提交记录聚合，反复修改同一提交不轰炸教师|
|教师批改|复用原事件，补发送者和去重，成绩正文仅发送给本人|
|学生课程提问|真实讨论创建后通知该班教师；教师可在详情中回复|
|讨论回复|复用原回复通知，详情可查看真实回复内容|
|助手任务成功/失败/超时|在真实终态事务内通知任务所有者；取消不冒充成功|
|知识建设任务成功/失败/中断终态|在终态写入事务内通知发起人；有关学习知识请求同步通知其本人|
|知识请求受理/可用性检查通过|真实 REQUESTED/PENDING_REVIEW/RESOLVED 处理链通知；不会把建设完成说成已经审核发布|
|学习计划反馈确认|真实确认应用后通知；预览、重复确认、普通保存不发通知|
|作业截止时间调整|当前没有独立调整接口，本轮没有虚构此事件|
|班级课程资料更新|当前没有明确的课程资料发布与班级接收绑定链，未将私人资源编辑擅自广播|
|其他教学审核/协作申请|未发现现有正式流程，作为扩展项，不伪造通知|

## 实时同步、可靠性与安全

- 在线可见页面每15秒查询未读数，卡片打开时同步最近消息；未读数变化也刷新消息中心。15秒是轮询间隔，并非毫秒推送。
- 断网错误可见，失败间隔按30/60/120秒退避；online、前台恢复及跨标签页已读事件立即重新同步。隐藏页不发送定时请求。
- 通知持久化，刷新与重连重新查库，不依赖浏览器保存消息。跨设备以轮询同步，跨标签页用Storage事件加速。
- 轮询生命周期仅在公共卡片中启动，组件卸载清理计时器及监听；账号变化清空状态并防止旧请求覆盖新账号。
- 原业务与通知共用数据库事务；失败回滚不会留下成功通知。共享数据库架构不需要额外Outbox。SQLite/PostgreSQL使用ON CONFLICT原子去重；并发重放测试验证6个线程仅入库1条。
- 查询、未读、已读、详情每次校验当前收件人及课程/班级归属；退班或教师失去管理范围后不能继续读取相关内容。禁用账号由原JWT依赖拒绝。
- 跳转由后端按业务类型固定映射；前端再次限制站内学生/教师/管理员路径，目标业务沿用原鉴权。无任意外部URL；正文使用Vue文本插值。
- 资源删除或权限撤销时详情返回明确404说明。历史已读消息没有准确read_at时不虚构时间。

## 本次执行的验证

- `unit-final-v2`：82 passed，覆盖通知、原班级业务、助手任务、知识任务、计划反馈、计划适应及知识准入；这是较早完整定向集的通过记录。
- 最终 `notification-delivery`：9 passed，增加课程提问/回复、5000人限制及6线程并发去重，含原班级作业闭环。
- `events-final`：11 passed，含真实知识任务终态以及计划确认、助手终态通知的新增数据库断言。
- `knowledge-delivery`：知识任务中断恢复通知补齐后的最终定向回归，详见其command.log。上述集合有重叠，不合并为独立测试总数。
- TypeScript + Vite最终构建退出0，`build-delivery.log`，4.83秒；保留既有第三方构建提示。
- 新增通知模块、路由、迁移、测试与执行脚本Ruff通过；未宣称整仓lint通过。
- 隔离真实SQLite/JWT浏览器通过管理员发布UI、双端卡片、关闭逻辑、详情已读与刷新、提交进入对应批改、网络恢复、移动端等，未拦截API或使用静态业务数据。
- 实际5175/8005最终浏览器 `current-browser-final/result.json`：学生/教师定向管理员通知；发布→提交→批改→双端正确目标；课程提问→教师详情回复；多标签页及刷新已读；断网提示与重连恢复；390px双端面板。pageErrors=[]。截图已实际查看。
- 当前平台验收只向本轮专用账号发送，不向真实学生广播。专用账号、班级、作业、提交、讨论、通知和发送回执已清理，cleanup.json记录剩余账号0。
- 初次旧教师画像测试有4项依赖固定账号/班级的失败，未把它算为通过。一次扩大回归遇磁盘不足，记录为失败；改为串行独立临时目录后82项通过。自动审批拒绝删除临时目录，相关临时目录保留。

## 当前运行状态及限制

当前8002、8005、8007和原助手/知识Worker已加载新代码；5175继续由原Vite提供页面。0034仅做本次增量迁移，没有改写共享Alembic版本。验收清理后仍为 users=96、resources=118、learning_paths=162、study_notes=2、notifications=0，model_calls=133。本轮未调用付费模型、搜索/抓取或外部图片服务。原有及同期未提交改动保留，没有自动提交。

未做生产大规模压测、长时间内存监测、真实PostgreSQL迁移演练和新付费生成验证；多设备同步最长受当前轮询退避间隔影响。未给项目不存在的截止调整、资料分发或审批流程造数据。磁盘剩余空间较少，旧失败日志与临时目录均保留。

## 本轮文件清单

后端与迁移：
- common/models/learning.py
- common/notifications.py
- alembic/versions/20261021_0034_unified_notifications.py
- services/teacher_service/app/main.py
- services/teacher_service/app/api/routes/notifications.py
- services/teacher_service/app/services/teacher_manager.py
- services/agent_service/app/api/routes/learning_gaps.py
- services/agent_service/app/services/assistant_tasks.py
- services/agent_service/app/services/knowledge_tasks.py
- services/agent_service/app/services/learning_path.py
- services/agent_service/app/services/plan_knowledge.py

前端：
- web-app/src/components/AppTopbar.vue
- web-app/src/components/AssistantPet.vue
- web-app/src/components/notifications/NotificationCard.vue
- web-app/src/components/notifications/NotificationItem.vue
- web-app/src/components/notifications/NotificationDetail.vue
- web-app/src/stores/notifications.ts
- web-app/src/views/NotificationCenter.vue
- web-app/src/views/admin/notifications.vue
- web-app/src/views/TeacherView.vue
- web-app/src/views/student/ClassroomView.vue
- web-app/src/router.ts
- web-app/src/config/adminNavigation.ts

测试、运行与交接：
- tests/unit/test_unified_notifications.py
- tests/unit/test_assistant_tasks.py
- tests/unit/test_knowledge_tasks.py
- tests/unit/test_plan_feedback.py
- tests/e2e/notification_server.py
- tests/e2e/run-notifications.mjs
- tests/e2e/run-notifications-current.mjs
- scripts/run_notification_browser.py
- scripts/verify_notification_current.py
- scripts/verify_notification_migration.py
- scripts/apply_notification_runtime.py
- docs/unified-notifications-20261021.md
- DEV_STATE.md

主要证据统一位于 artifacts/notifications-20261021/；其中 runtime/before.sqlite 是操作前备份，runtime-delivery/result.json 是最后的进程与数据核对记录。启动清单 artifacts/local-start-20261019/processes.json 只更新对应PID。
