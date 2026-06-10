# evaluation-service

学习效果评估与个性化反馈智能体服务，负责基于真实答题记录完成以下工作：

- 单题提交与批量提交
- 客观题判分与主观题 / 编程题 LLM 评分
- 知识点掌握度更新、薄弱点识别、错误模式聚合
- 阶段报告、月度综合报告生成
- 向用户画像智能体和学习路径规划智能体发送事件

## Primary APIs

- `POST /evaluation/submit`
- `POST /evaluation/batch_submit`
- `GET /evaluation/stage-report/{user_id}/{chapter_id}`
- `GET /evaluation/monthly-report/{user_id}`

## Compatibility APIs

为了兼容现有前端和教师端，以下旧接口仍保留：

- `POST /evaluation/practice/submit`
- `POST /evaluation/mistakes/qa`
- `DELETE /evaluation/mistakes/{user_id}`
- `GET /evaluation/reports/stage/{user_id}`
- `GET /evaluation/reports/stage/{user_id}/detail`
- `GET /evaluation/reports/comprehensive/{user_id}`
- `GET /evaluation/reports/comprehensive/{user_id}/detail`
- `GET /evaluation/mistakes/{user_id}/detail`
- `GET /evaluation/mistakes/{user_id}/remedial`
- `GET /evaluation/profiles/{user_id}/snapshot`
- `GET /evaluation/reports/suggestions/{user_id}`

## Core Submission Fields

主提交流程使用 `AnswerRecordSubmission`，核心字段：

- `user_id`
- `exercise_id`
- `user_answer`
- `time_spent`
- `knowledge_point_ids`
- `exercise_type`
- `difficulty`

客观题需要：

- `standard_answer`

主观题 / 编程题需要：

- `reference_answer`
- `max_score`

建议同时传入：

- `exercise_content`
- `explanation`
- `chapter_id`
- `chapter_name`

## Persistence And Events

评估结果会写入：

- `answer_records`
  保存答题记录、时间戳和 `evaluation_json` 明细。
- `user_profiles`
  保存知识点掌握度、历史曲线、薄弱点和错误模式标签。
- `learning_reports`
  保存阶段报告与月度综合报告。

事件会发送到：

- `profile_updates`
  `ProfileUpdateEvent`
- `path_adjustments`
  `PathAdjustmentRequest`
