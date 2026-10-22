# 平台学习打卡、课堂广场与课程表交付说明（2026-10-22，按最新口径修订）

> 本文件已按用户最新要求重写：**平台学习打卡独立于课堂与考勤**；课堂是可选协作入口；学生可自主加入/退出课堂；加入后课程表自动同步。

## 一、实际架构

沿用现有 FastAPI 多服务 + Vue 3/Vite + SQLite，不重建项目、不改框架。

- 后端复用 `teacher_service`（8005）：账号、课堂、成员、作业、通知均在此服务；新增 `/learning/checkin/*`、`/learning/classrooms/*`、`/learning/classes/*/schedule`、`/learning/schedule/me`。
- 数据层沿用 SQLAlchemy `Base` 与 Alembic；新增 3 张业务表，课堂表增量 6 列，废弃并删除仅本轮产生的空/孤儿 `study_checkin_logs`。
- 前端复用 Element Plus、`teacherApi`、统一导航与 `LearningContent`；新增学生「课堂广场 / 我的课堂 / 我的课程表 / 学习打卡」与教师「课程安排」。
- 通知复用 `common/notifications.emit/visible/target_path`，未建第二套铃铛。
- 时间统一按 `Asia/Shanghai` 计算自然日；数据库仍存 naive UTC。

## 二、三个核心功能

### 1. 平台学习打卡（独立）

- 学生无需加入任何课堂即可打卡；打卡记录**没有 class_id / course_id / 课堂日程引用**。
- 每个自然日最多一条有效记录（数据库唯一约束 `(user_id, checkin_date)`）。
- 一键打卡，可选填写「今日学习目标」「打卡感想」；重复请求幂等，不增加天数。
- 展示连续天数、累计天数、本周目标进度、本月天数、月历、历史记录。
- 连续天数只按平台打卡日期计算，教师课堂任务通过与课堂出勤都不计入。
- 登录本身不会自动打卡；不统计学习分钟数，也直接提升知识点掌握度。
- 教师端没有读取学生私人打卡明细的接口。

### 2. 课堂广场（可选）

- 只展示 `status=active` 且 `is_public=true` 的课堂；不泄露邀请码。
- 支持按课堂名称/学科/教师搜索、按学科筛选。
- 课堂卡片展示：学科、教师、成员数/人数上限、学期、课程简介、教学目标、教学大纲、最近教学范围、进行中的课堂任务数。
- `join_mode=open` 可直接加入；`invite` 仍走邀请码。加入默认无需审批。
- 人数上限由后端在写事务内校验；并发加入不突破上限。
- 支持学生自主退出课堂：停止展示未来课程，保留历史作业/提交/考勤等记录。
- 「我的课堂」展示已加入课堂、简介、学期、人数与退出入口，并保留作业、讨论、邀请码加入。
- 教师创建课堂可设置：简介、教学目标、教学大纲、学期、人数上限、是否公开、加入方式。

### 3. 课程表（随课堂自动同步）

- 教师为本人课堂创建每周课程：主题、星期、起止时间、教学周范围、地点、线上/线下。
- 后端确定性冲突检测：同课堂或同教师在时间重叠且教学周重叠时返回 409，不依赖模型。
- 单次调整：停课、调课（新日期/时间/地点）、补课（新日期与时间），均需填写原因。
- 调整后向课堂成员发送站内通知；学生课程表即时反映。
- 学生课程表按周展示；仅显示当前已加入且有权限的课堂；退出后未来安排不再出现。
- 调课、补课在周视图中标记「已调课」「补课」。

### 4. 保留的课堂协作能力

原有课堂作业、课件范围、讨论、课堂签到与教师打卡任务保留；它们与平台学习打卡**分属不同数据与统计口径**，不会互相冒充。

## 三、数据库与接口

### 新增/修改表

- `platform_daily_checkins`：`user_id`、`checkin_date`、`checkin_at`、`timezone`、`goal`、`reflection`、`created_at`；唯一 `(user_id, checkin_date)`。
- `class_sessions`：课堂、教师、主题、星期、起止时间、教学周、地点、方式、状态。
- `class_schedule_exceptions`：`session_id`、`date`、`kind(cancel/reschedule/makeup)`、新日期/时间/地点、原因；唯一 `(session_id, date)`。
- `classrooms` 新增：`join_mode`、`description`、`objective`、`syllabus`、`semester`、`is_public`、`capacity`。
- Alembic：`0037_checkin`、`0038_classroom_plaza`、`0039_platform_checkin_schedule`。

### 关键接口

学生：

- `GET/POST /learning/checkin/daily`、`GET /learning/checkin/daily/history`、`GET /learning/checkin/daily/calendar`
- `GET /learning/classrooms/plaza`、`GET /learning/classrooms/mine`、`GET /learning/classrooms/{id}`
- `POST /learning/classrooms/{id}/join`、`POST /learning/classrooms/{id}/leave`
- `GET /learning/schedule/me?week_start=`
- 课堂任务与课堂签到：`/learning/checkin/tasks*`、`/learning/checkin/attendance*`

教师：

- `GET/POST/PUT/DELETE /learning/classes/{id}/schedule*`
- `POST /learning/classes/{id}/schedule/{session_id}/exceptions`
- `DELETE /learning/classes/{id}/schedule/exceptions/{exception_id}`
- 课堂/任务/签到管理沿用 `/teacher/*` 与 `/learning/checkin/manage/*`

管理员：

- `GET /learning/checkin/admin/overview`、`GET /learning/checkin/admin/audits`（只读汇总/审计）

### 权限规则

- 所有读写由后端 JWT 身份 + 课堂所有权/当前成员关系校验。
- 学生只能看到公开课堂或已加入课堂；邀请码不进入广场响应。
- 非授课教师不能排课、调课或删除课程。
- 平台打卡仅本人可见；教师无读取接口。
- 退出课堂后不能继续提交该课堂任务或读取课程表；历史数据保留。

## 四、验证结果（本次真实执行）

| 验证 | 命令/方式 | 结果 |
| --- | --- | --- |
| 打卡/课堂任务/签到 | `pytest tests/unit/test_checkin_loop.py` | 9 passed（含并发打卡） |
| 课堂广场/容量/退出/元数据 | `pytest tests/unit/test_classroom_plaza.py` | 3 passed |
| 课程表/冲突/调停补课/退课 | `pytest tests/unit/test_classroom_schedule.py` | 2 passed |
| 班级与通知回归 | `pytest tests/unit/test_classroom_loop.py tests/unit/test_unified_notifications.py` | 12 passed |
| 真实 HTTP（运行库） | `python scripts/verify_checkin_runtime.py` | 平台打卡幂等、无课堂可打卡、广场公开、自主加入、课程表同步、停课移除、任务/审核/签到/通知/持久化全部通过；临时数据清理 |
| 真实浏览器 | `python scripts/verify_checkin_browser.py` | 16 项通过：教师任务/审核/实时出勤/课程安排，学生一键打卡/历史/课堂任务/签到/课程表/课堂广场/390px；`pageErrors`、5xx 均为空 |
| 前端构建 | `npm run build` | 退出 0 |
| Python 静态检查 | `ruff check` 全部新增/修改文件 | 通过 |

运行库处理：

- 备份：`artifacts/checkin-20261022/runtime-before-checkin.sqlite`、`runtime-before-plaza.sqlite`、`runtime-before-platform-checkin.sqlite`。
- `scripts/apply_checkin_schema.py` 幂等建表 + `ADD COLUMN`；仅删除无有效用户关联的旧 `study_checkin_logs`（本轮测试遗留 5 条孤儿记录）。
- 仅重载 8005（最终 PID 49376），其他服务与业务数据未动。
- 截图与 `result.json`：`artifacts/checkin-20261022/browser/`。

## 五、已知问题与边界

1. **课程表未叠加个人学习计划**：需求建议的“正式课堂课程表 + 个人学习日程”双层视图尚未实现；当前课程表只含教师课堂安排，个人学习路径仍是独立页面。数据实体已分离，未互相覆盖。
2. **无教室资源模型**：冲突检测覆盖同课堂/同教师时间冲突，不包含教室占用冲突。
3. **课堂封面未实现**：未提供封面上传与展示。
4. **课堂详情为列表卡片 + 接口**：未单独做详情路由页。
5. **管理员只读**：无违规课堂处置、学期/校历配置入口。
6. **课堂签到二维码图片未渲染**：签到码与安全令牌可用，未生成二维码图像。
7. **课堂任务附件 UI 未接入**：接口预留 `attachment_ids`，页面未接上传组件。
8. **到期自动提醒未调度**：当前为教师手动提醒。
9. **平台打卡未写入画像/知识点/推荐**：仅作为学习习惯与参与度记录，符合“不直接提升掌握度”的要求，但尚未在画像中展示。
10. 未在 PostgreSQL/公网/多实例下压测；仅验证当前 SQLite 运行库与隔离测试库。

## 六、运行与入口

```powershell
# 增量应用 schema（先备份）
$env:DATABASE_URL = 'sqlite+pysqlite:///C:/.../artifacts/local-start-20261019/runtime.sqlite'
$env:PYTHONPATH = (Get-Location).Path
python scripts/apply_checkin_schema.py

# 重载 teacher 服务
python -m uvicorn services.teacher_service.app.main:app --host 127.0.0.1 --port 8005 --lifespan off

# 测试
pytest tests/unit/test_checkin_loop.py tests/unit/test_classroom_plaza.py tests/unit/test_classroom_schedule.py -q
cd web-app; npm run build
```

入口：

- 学生：`/student/classroom-plaza`（课堂广场）、`/student/classroom`（我的课堂）、`/student/timetable`（我的课程表）、`/student/checkin`（平台学习打卡）。
- 教师：`/teacher/schedule`（课程安排）、`/teacher/checkin`（课堂任务与签到）、`/teacher/classes`（课堂创建/成员）。
- 管理员：`/admin/checkin`（汇总与审计）。
