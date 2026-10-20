# 本轮API契约

## P1新增接口（当前源码，旧共享进程未激活）

| 接口 | 认证/契约 |
|---|---|
| POST `/learning/contexts` | 本人；client_request_id、plan_id、module_id、task_key；选择资源必须传resource_id与expected_resource_version；幂等重放，冲突409 |
| GET `/learning/contexts/catalog`、`/{context_id}` | 本人有效计划/权威绑定快照；越权404，来源变更409 |
| POST `/assistant/chat`、`/chat/stream` | 可选learning_context_id；由服务端构建资源引用，会话不能跨ctx；生成任务保存ctx |
| POST `/paths/preflight` | 本人；subject/knowledge_point；返回ready、reason、发布版本和可选gap_id，不返回片段正文 |
| GET `/knowledge-base/admin/learning-gaps`、POST `/{id}/construction` | 仅管理员；记录缺口/显式进入原建设任务队列，不自动发布 |
| POST `/graph/enrichment` | 仅管理员；point_id/client_request_id；202持久队列，不在读取中隐式创建 |
| POST `/graph/visualization` | 认证；公共来源或本人/管理员显式resource_id+resource_version；个人快照不缓存 |
| POST `/study/notes`、PUT `/{id}` | 可选上下文及source_locator，服务端保存来源版本；已有来源不可改绑 |
| POST `/evaluation/practice/submit` | 可选ctx；必须为已绑定题、带client_request_id；标准答案以库中为准，证据同事务回写 |
| GET `/admin/operations`、`/tasks/{assistant\|knowledge}/{id}` | 仅管理员；1～90天任务聚合及安全阶段详情；实际Token和独立Worker在线状态UNKNOWN，不返回Prompt |

详细实现文件、测试及限制见11；API前缀按原多服务代理配置使用。

所有新增端点使用现有JWT身份，不接受任意目标user_id。保留既有路径前缀。

| API | 服务 | 行为/状态 |
|---|---|---|
| `GET /evaluation/overview/me` | evaluation | ApiResponse.data：analytics、active_plans、due_cards、recent_resources、weak_points、suggestions；只查询数据库，不请求模型 |
| `POST /evaluation/activity/heartbeat` | evaluation | 参数tab_id(UUID)、sequence(正整数)、active(bool)、page(允许的7类学习页面)；额外字段如user_id/duration_seconds返回422。匿名401，缺迁移503 |
| `GET /evaluation/analytics/{user_id}?days=30` | evaluation | 原本人/管理员权限保留；新增summary.study_seconds、current_streak_days、daily.study_seconds及自然周时长比较；缺活动表时study_seconds=null，不能当0 |
| `POST /paths/adaptation/preview` | agent | 可选daily_minutes=5..480。无变化返回status=no_change；否则proposed、proposal_id、base_revision、before/after、真实作答evidence、added_tasks。只保存提案，不改变stages |
| `POST /paths/adaptation/{proposal_id}/confirm` | agent | 仅本人活动路径中的服务器提案；applied或already_applied；返回path。不存在/被替换404，计划已更新409，匿名401 |
| `POST /paths/adjust` | agent | 保留原参数与响应；增加revision条件更新冲突409 |

## 心跳协议

```json
{"tab_id":"00000000-0000-4000-8000-000000000001","sequence":1,"active":true,"page":"exercise"}
```

首个请求只建立游标、计时为0。同标签后续连续active且间隔不超过45秒才写区间。重放/乱序、inactive、失焦、过期后恢复、换标签接管均不会补记中间空档。前端15秒发送，只有最近60秒内真实输入、可见、聚焦且处于学习页面才报告active。`started/resumed/recorded/replayed/another_tab/clock_rollback` 以及credited_seconds都是实际服务端结果。CAS竞争未能在3次内成功时409。

多个标签和设备竞争同一用户游标；新标签不能从未过期的活动拥有者抢占。前端刷新生成新tab UUID，不复用可被浏览器复制的sessionStorage ID。

## 计划提案

任务变化只使用服务器已保存的added_tasks，客户端确认不提交任务数组。提案保存在现有LearningPath JSON中；关闭对话框保留原任务。新的预览替换旧提案；任务完成/reset/skip使旧提案失效。保留最近20个已应用ID；更老确认返回不存在/过期，不会重建提案或重复任务。

本轮没有新增视频、TTS、动画、PPT、通用多模态生成接口；这些不能列为已经接通的API。
