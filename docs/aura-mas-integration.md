# AURA-MAS 增量融合记录

详细差异矩阵、接口口径、迁移与验证记录见 [AURA-MAS 功能差异与交付边界](aura-mas-gap-matrix.md)。

核验日期：2026-10-17；上游：`cdz-hy/aura-mas`，固定提交
[`5923cf6cd766a58b112f24f02371bb87da1fa904`](https://github.com/cdz-hy/aura-mas/tree/5923cf6cd766a58b112f24f02371bb87da1fa904)，MIT。
本次根据上游源码中的 `StatsController`、`AdminDashboardController`、`AdminUserController`、`analytics.py` 与 `learning_analyzer.py` 核对能力；实现使用当前项目的数据表和服务，没有移植 Java 服务或第二套前端。
当前仓库的 `java-services` 是 Spring Boot 迁移骨架，README 指定 FastAPI 为当前主联调后端；新增能力接入当前主链路，并保留 Java 骨架。

| 能力 | 当前系统与本次改动 | 数据与权限 | 状态 |
| --- | --- | --- | --- |
| 学习分析 | 在现有 evaluation 服务增加 `/evaluation/analytics/{user_id}`；报告页展示 30 天作答、资源交互、提问与 14 天活动图 | `answer_records`、`resource_interactions`、用户提问 `chat_messages`；本人或管理员 | 已实施 |
| 学习画像 | 保留现有对话式画像、七维证据画像、深度分析和画像页面；新行为统计与报告同页互补 | `user_profiles` 与既有作答证据；沿用现有权限 | 已有能力，未另建画像 |
| 管理员概览 | 现有管理页增加真实用户、学习路径、资源和近 7 天作答统计 | 直接汇总已有表；仅管理员 | 已实施 |
| 管理员用户管理 | 增加分页、用户名/邮箱搜索、角色筛选；选择用户后沿用已有角色分配 | `users`；响应不含密码哈希；仅管理员 | 已实施 |
| 管理员知识库 | 当前 agent 服务已有知识库来源、增量重建和有权限的管理端点；管理页可查看语料、来源与索引状态，并手动增量重建 | 现有 RAG 索引；教师或管理员，重建仅管理员 | 基础运维已接入；文件上传和解析进度待实现 |
| 管理员资源管理 | 管理页接入现有资源目录、详情预览和发布/归档端点 | `resources` 生命周期字段；教师或管理员 | 基础操作已接入；版本管理待实现 |
| Token 用量 | 当前没有统一、可审计的模型调用 Token 记录，管理页明确不显示估算值 | 需先覆盖各模型调用路径并持久化 | 未实施 |
| 学习时长与效率时段 | 现有 `AnswerRecord.time_spent` 只表示答题用时，不能推断总学习时长或时段效率 | 需专用学习会话/前后台停留事件且防刷与隐私规则 | 未实施 |
| 个人笔记与复习闪卡 | 新增私有笔记、关联资源、闪卡、到期复习和逐次复习历史；复用当前 user 服务与账号 | `study_notes`、`review_cards`、`card_review_events`；本人读写；增量迁移 `20261017_0012`、`20261017_0014` | 已实施 |
| 成绩单到学习路径 | 个人分析页可进入原学习路径页，按最低均分科目预填；原路径服务验证成绩单归属并使用科目级证据调用现有模型、持久化来源 | 复用 `transcript_analyses` 与 `learning_paths`，不新增表；需模型可用且学生主动确认生成 | 已实施一键生成；自动重排未实施 |
| 音频/动画、Android | 当前已有多种结构化资源；真实音视频播放/存储与 Android 是独立产品能力 | 需要外部媒体服务、存储、内容审核与端到端验收 | 未实施 |

## 本次接口口径

- `accuracy_percent` 的分母是有 `is_correct` 判分的作答；未判分的作答仍计入题次。
- 活跃天数表示当天至少有一条作答、资源交互或用户提问，不等于学习时长。
- `question_seconds` 是有记录的做题用时；没有使用页面访问或资源浏览来推断掌握度。
- 按北京时间归入自然日；窗口支持 7–90 天，默认 30 天。
- 用户检索对 `%`、`_` 进行字面量转义，分页每页最多 100 条，不返回凭证字段。
- 管理页“启用标记数”汇总 `users.is_active`；本轮已将该字段接入共享鉴权依赖与登录接口，停用后的已有令牌被拒绝。
- 成绩单个人分析在多学生或身份不完整时要求明确选择；只将选中学生的有效成绩关联到当前学生账号。分析缓存同时按账号隔离，画像保存实际 `analysis_id`；深度画像分析读取科目级证据，分析 ID 变化会使旧结论失效。教师/管理员的个人分析只生成报告，不写入其教学账号画像。科目总分诊断仍是推断，不会冒充知识点级掌握证据。

验证入口：`tests/unit/test_aura_analytics_admin.py`、`tests/unit/test_study_tools.py`、`tests/unit/test_transcript_analysis.py`、`tests/unit/test_transcript_learning_path.py`、`tests/unit/test_profile_analysis.py`、`npm run build`。学习分析与管理员汇总复用既有表；私有笔记、闪卡及复习事件分别使用 `20261017_0012_study_notes_cards.py` 和 `20261017_0014_card_review_events.py` 增量迁移。
