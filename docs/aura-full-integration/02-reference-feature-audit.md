# AURA-MAS 源码参考核对

## P1参考使用边界

继续使用本地已核验5923cf6cd766a58b112f24f02371bb87da1fa904及MIT许可。三栏和管理员任务能力适配到现有业务表/权限/Worker；未复制上游平行后端。24项是能力组，尚未完成全部原子功能识别，不报告100%覆盖；新工作包状态与独立模块验收见11，不将文本/习题演示扩大到全部多模态。

本轮通过 `git ls-remote` 与实际克隆重新核验上游 [cdz-hy/aura-mas](https://github.com/cdz-hy/aura-mas/tree/5923cf6cd766a58b112f24f02371bb87da1fa904)，HEAD 为 `5923cf6cd766a58b112f24f02371bb87da1fa904`，MIT。克隆目录：`artifacts/aura-full-integration-20261020/reference/`。以下依据实际源码片段和调用链，不把 README 或组件名称当成运行验收。

## 已读取的关键实现及适配结论

- `Vue-frontend/src/views/DashboardView.vue`：计划卡片、状态/进度、周学习分布、最近活动、空状态。采用集中呈现思路；当前项目使用自己现有的数据库统计。
- `PlanDetailView.vue`：selectedModuleContext、selectedResourceId、知识树当前节点与资源切换联动；生成资源继承模块/节点上下文。当前三栏工作区仍需实现，不声称本轮首页组件等于该工作区。
- `components/plan/PlanResourceOutline.vue`：模块/资源两类节点、树结构、provide 上下文与拖动入口。后续适配现有 LearningPath JSON，不迁移 Java module 数据库。
- `components/resource/ResourcePreviewDrawer.vue`：quiz/mindmap/video/pptx 分支渲染，PPT 可使用 Office Online 或 HTML。后续应按结构化协议分类型呈现，HTML 需要安全边界。
- `MindmapPlayer.vue`：画布适应、居中、PNG/SVG 导出等交互。现有 structured_json 生成尚不能覆盖编辑保存验收。
- `AnimationPlayer.vue`：sandbox iframe、播放/字幕/进度/音量、异步导出状态。仅 iframe 隔离不能替代模型产物验证、网络限制和受限渲染服务。
- `PptxViewer.vue`：Office Online iframe 依赖可从公网访问的 PPTX URL；不能照搬到本地私有文件后宣称预览成功。
- `Python-backend/app/api/v1/endpoints/resource_chat.py`：Ticket 验证、plan/module/session 请求上下文、SSE 事件、人工确认与 checkpointer 恢复。当前复用自己的鉴权、AssistantTask、事件与 Worker，不复制 GET 参数传长会话的协议。
- `plan_generator.py`：Ticket → Java 用户画像/对话 → task_decomposer，后台线程与 SSE 分离。当前持久 Worker 优先于新增临时线程队列。
- `flashcard.py`：本人笔记校验、全篇/选段生成、JSON Q&A、SSE。当前保留自己的 ReviewCard 调度和写入，后续新增 AI 提案仍需确认保存。
- `agents/video_search_agent.py`：Bilibili/Tavily 多轮候选搜索、平台白名单与去重、模型筛选。当前不可假定 DeepSeek chat 端点具有这些搜索工具。
- `agents/resource_type_generator.py`：真实 MiMo TTS 请求、音频 base64 解码与长文分段 WAV 合并。这是外部付费依赖，不能把 DeepSeek 文本响应当音频；本轮未移植或调用。
- `graph/learning_graph.py`：StateGraph 节点、主控意图路由、异常回退、最大迭代、RAG 后分支、人工确认；MemorySaver 与 Java 持久化分工。当前复用执行代次和持久任务，不另建平行图框架。
- `api/v1/endpoints/analytics.py` 与 Java `StatsService.java` / `StatsController.java`：AI 建议消费统计数据，真实行为统计由数据库服务提供，包含 DailyStudyTime、计划/复习/作答。当前聚合由既有评价服务承担，首页读数不调用模型。
- `LearningPlanController.java`：认证后计划创建、分页读取、修改、删除、状态与 internal 路由。当前兼容 `/paths/*`，不新增重复的 Java REST 层。

## 尚未完成的参考审计

AnalyticsDashboard、ProfileView、KnowledgeGraphView、NoteList/Detail、FlashcardReview 全部交互及其 Java Service/Mapper/表约束尚未逐项读完；knowledge_graph/knowledge_tree endpoints、全部资源播放器和审核/回退分支也未完成深入验证。上游没有在本机部署或运行；上游源码支持某功能不代表本项目已融合。

本检查点按 24 个能力组建立差异矩阵；这是规划/核对分组数，**不是已完整审计的原子功能总数**。
