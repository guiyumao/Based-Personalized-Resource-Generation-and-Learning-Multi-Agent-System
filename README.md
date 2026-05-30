# AgentCore — 个性化学习多智能体后端

AgentCore 是"个性化学习智能体系统"的 Java 后端模块，基于 Spring Boot 3 + MyBatis-Plus + PostgreSQL + DeepSeek API，负责承载全部 6 个智能体的核心业务逻辑。完整的项目需求说明见同目录下的 [总需求文档.md](./总需求文档.md)。

---

## 一、核心功能

| 功能 | 智能体 | 状态 |
|------|--------|------|
| 对话式学习画像构建 | 画像构建智能体 | ✅ 已实现 |
| 多智能体协同资源生成 | 资源生成协调 + 通用资源生成智能体 | ✅ 已实现（5 种类型） |
| 个性化学习路径规划 | 学习路径规划 + 推送智能体 | ✅ 已实现 |
| 智能辅导 | 智能辅导智能体（RAG 答疑） | ✅ 加分项已实现 |
| 学习效果评估 | 学习效果评估智能体 | ✅ 加分项已实现 |

### 1.1 画像构建智能体

通过自然语言对话自动抽取学生画像的六个维度，支持随学随新。

- **六维度**：知识基础、认知风格、易错点偏好、学习节奏、兴趣方向、学习目标
- **对话管理**：完整对话历史存储，每次请求带上最近 20 条作为 LLM 上下文
- **自动更新**：LLM 分析对话后自动提取维度信息并持久化
- **智能轮次控制**：LLM 每轮回复自动评估六维度完整度（已获取/部分/未获取），给出预估剩余对话轮次。超过 8 轮自动加速收尾，所有维度完成后告知前端"画像构建完成"。前端应在 `estimatedRemainingRounds=0` 时结束对话，引导进入学习模块

### 1.2 资源生成智能体（核心）

协调智能体分析用户需求意图，分发到通用生成智能体，按类型生成：

| 类型 | 说明 |
|------|------|
| `lecture` | 结构化讲解文档，含概念、示例、总结 |
| `mindmap` | 层次化知识思维导图（Markdown 多级标题） |
| `exercise` | 练习题，含答案和详细解析 |
| `extended_reading` | 拓展阅读材料和延伸方向推荐 |
| `code_example` | 可运行的代码示例 + 注释解析 |

每种类型使用独立的 System Prompt 模板，基于用户画像个性化调整难度和呈现方式。

**异步生成流程**：资源生成采用 RabbitMQ 异步消费模式——
```
POST /api/resource/generate  → { taskId, status:"queued" }   // taskId 是任务追踪号
GET  /api/resource/generate/{taskId}/status                   // 查询生成进度
  → { status:"completed", resourceId:12 }                     // resourceId 是真正的资源ID
GET  /api/resource/{resourceId}                               // 获取资源内容
```

### 1.3 学习路径规划

基于用户画像，由 LLM 生成 5-8 个节点的科学学习路径（从基础到进阶）。支持手动调整节点状态（完成/跳过/重置），自动更新整体进度。

### 1.4 智能辅导（加分）

基于 RAG 向量检索 + LLM 的多模态答疑：将问题向量化后在知识库中检索相关内容，拼接为 LLM 上下文后生成详细解答。解答包含：概念解释 → 核心要点 → 举例说明 → 常见误区 → 延伸思考。

### 1.5 学习效果评估（加分）

- **评估报告**：汇总学习时长、练习正确率、各知识点掌握度
- **雷达图数据**：六维度能力数值化（0-100 分）
- **AI 建议**：基于学习数据由 LLM 生成个性化改进方案

---

## 二、技术架构

```
┌──────────────────────────────────────────────────┐
│                   Controller 层                    │
│  Profile │ Resource │ LearningPath │ Tutor │ Analytics │
├──────────────────────────────────────────────────┤
│                   Service 层 (6 个智能体)           │
│  ProfileAgent │ ResourceCoordinator │ Generation   │
│  LearningPath │ TutorAgent │ AnalyticsAgent        │
├──────────────────────────────────────────────────┤
│            Client 层 │ Mapper 层                   │
│     DeepSeekClient  │ MyBatis-Plus (9 Mapper)     │
├──────────────────────────────────────────────────┤
│                   PostgreSQL                       │
│  10 张表 │ Embedding 向量存储 │ JSONB 扩展字段      │
└──────────────────────────────────────────────────┘
```

### 技术栈

| 层次 | 选型 |
|------|------|
| 框架 | Spring Boot 3.0.2 |
| ORM | MyBatis-Plus 3.5.15 |
| 数据库 | PostgreSQL（AgentSQL 库） |
| 向量检索 | 余弦相似度 Java 层计算（embedding 存为 JSON 数组） |
| AI 服务 | DeepSeek Chat API |
| 缓存 | Redis（`spring-boot-starter-data-redis`，画像 30min / 资源 24h TTL） |
| 异步消息 | RabbitMQ（`spring-boot-starter-amqp`，资源生成异步化、事件解耦） |
| API 文档 | Knife4j 4.4.0（基于 SpringDoc OpenAPI 3） |
| 工具 | Lombok, Jackson |

### 架构设计理念

**缓存策略**：高频读取、低频写入的数据（画像、资源内容）采用 Redis Cache-Aside 模式，按数据特性设差异化 TTL，写操作时主动失效。画像查询首次命中后 30min 内不再查 DB。

**异步消息**：资源生成耗时长（7-18 秒，含两次 LLM 调用），引入 RabbitMQ 实现异步化——POST 请求立即返回 taskId，消费者后台生成后写库。优点：用户体验从白屏等待变为毫秒级响应，同时控制 DeepSeek API 并发调用量。

**画像评分**：借鉴队友 PersonalizationService 设计，通过基础分（正确 85 / 错误 40）+ 速度修正（-10 到 +8）+ 难度修正（0/4/8）三因子加权计算知识点掌握度。每次学习进度上报后异步刷新 `user_progress` 表。

### 设计模式

- **构造器注入**：所有 Service 和 Controller 使用 final 字段 + 构造器
- **统一 DTO 映射**：Controller 内 `toDto()` 私有方法手动转换
- **MyBatis-Plus 模式**：Entity 用 `@TableName/@TableId`，Mapper 继承 `BaseMapper<T>`，Service 继承 `ServiceImpl<M, T>`
- **用户标识**：通过 `X-User-Id` 请求头传递（后续切换 JWT）
- **LLM Prompt 管理**：每个智能体的 System Prompt 定义为 `private static final String` 常量
- **JSON 容错**：统一 `extractJson()` 方法处理 LLM 输出的 markdown 代码块包裹

---

## 三、目录结构

```
AgentCore/
├── pom.xml
├── README.md                         ← 本文件
├── 总需求文档.md                       ← 项目整体设计方案
├── API接口文档.md                      ← 完整接口文档
│
├── src/main/java/com/softwarecompetition/agentcore/
│   ├── AgentCoreApplication.java     ← Spring Boot 入口
│   │
│   ├── client/
│   │   └── DeepSeekClient.java       ← LLM API 客户端（chat + embed）
│   │
│   ├── config/
│   │   ├── Knife4jConfig.java         ← API 文档配置
│   │   └── WebMvcConfig.java          ← 消息转换器配置
│   │
│   ├── controller/                    ← 5 个 Controller，12 个端点
│   │   ├── ProfileController.java
│   │   ├── ResourceController.java
│   │   ├── LearningPathController.java
│   │   ├── TutorController.java
│   │   └── AnalyticsController.java
│   │
│   ├── dto/                           ← 15 个请求/响应 DTO
│   │   ├── ChatRequest.java / ChatResponse.java / ProfileDto.java
│   │   ├── ResourceGenerateRequest.java / ResourceGenerateResponse.java
│   │   ├── ResourceDto.java / ResourceProgressRequest.java
│   │   ├── LearningPathDto.java / LearningPathNodeDto.java
│   │   ├── LearningPathAdjustRequest.java
│   │   ├── TutorAskRequest.java / TutorAskResponse.java
│   │   ├── AnalyticsReportDto.java / RadarChartDto.java
│   │   └── AnalyticsSuggestionDto.java
│   │
│   ├── entity/                        ← 9 个数据库实体
│   │   ├── UserProfile.java / ProfileConversation.java
│   │   ├── Resource.java / LearningRecord.java
│   │   ├── KnowledgeBase.java / ResourceGenerationRecord.java
│   │   ├── LearningPath.java / LearningPathNode.java
│   │   └── UserProgress.java
│   │
│   ├── mapper/                        ← 9 个 MyBatis-Plus 数据访问接口
│   │   ├── UserProfileMapper.java / ProfileConversationMapper.java
│   │   ├── ResourceMapper.java / LearningRecordMapper.java
│   │   ├── KnowledgeBaseMapper.java / ResourceGenerationRecordMapper.java
│   │   ├── LearningPathMapper.java / LearningPathNodeMapper.java
│   │   └── UserProgressMapper.java
│   │
│   └── service/                       ← 10 个接口
│       │   ├── ProfileAgentService.java / UserProfileService.java
│       │   ├── ResourceCoordinationService.java / ResourceGenerationService.java
│       │   ├── LearningPathService.java
│       │   ├── TutorService.java / AnalyticsService.java
│       │   └── EmbeddingService.java
│       │
│       └── impl/                      ← 8 个实现
│           ├── ProfileAgentServiceImpl.java
│           ├── ResourceCoordinationServiceImpl.java
│           ├── ResourceGenerationServiceImpl.java
│           ├── LearningPathServiceImpl.java
│           ├── TutorServiceImpl.java
│           ├── AnalyticsServiceImpl.java
│           ├── EmbeddingServiceImpl.java
│           ├── UserProfileServiceImpl.java
│           └── ProfileConversationServiceImpl.java
│
├── src/main/resources/
│   ├── application.properties         ← 数据库 & LLM 配置
│   ├── schema.sql                     ← 10 张表 DDL
│   └── data-test.sql                  ← 测试数据（3 用户 + 8 资源 + 1 路径）
│
└── src/test/
    ├── java/com/softwarecompetition/agentcore/
    │   ├── AgentCoreApplicationTests.java
    │   ├── ProfileControllerTest.java
    │   └── ProfileAgentIntegrationTest.java
    └── resources/
        ├── application.properties     ← 测试环境 H2 配置
        └── schema.sql                 ← H2 兼容 DDL
```

---

## 四、快速上手

### 环境要求

- JDK 17+
- Maven 3.9+
- PostgreSQL（数据库名 `AgentSQL`）

### 1. 初始化数据库

在 PostgreSQL 中创建数据库并执行建表脚本：

```sql
CREATE DATABASE "AgentSQL";
```

然后连接 `AgentSQL` 数据库，执行：

```sql
-- 执行建表脚本
\i src/main/resources/schema.sql

-- （可选）插入测试数据
\i src/main/resources/data-test.sql
```

### 2. 配置

编辑 `src/main/resources/application.properties`，确认数据库连接和 API Key：

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/AgentSQL
spring.datasource.username=postgres
spring.datasource.password=你的密码
llm.deepseek.api-key=你的API-Key
```

### 3. 启动

```bash
mvn spring-boot:run
```

或者使用 IDE 运行 `AgentCoreApplication`。

### 4. 访问 API 文档

启动后浏览器打开：

```
http://localhost:8080/doc.html
```

Knife4j 界面可查看全部 12 个接口的详细文档，并直接在线调试。

### 5. 运行测试

```bash
mvn test
```

测试使用 H2 内存数据库，无需 PostgreSQL 运行。

---

## 五、数据库表结构

| 表名 | 说明 |
|------|------|
| `user_profile` | 用户六维度画像 |
| `profile_conversation` | 画像构建对话历史 |
| `resource` | 学习资源（5 种类型 + 元数据） |
| `learning_record` | 学习行为记录 |
| `learning_path` | 个性化学习路径 |
| `learning_path_node` | 路径节点（邻接表） |
| `knowledge_base` | RAG 知识库（含 embedding） |
| `user_progress` | 知识点掌握度追踪 |
| `resource_generation_record` | 资源生成流水 |

---

## 六、API 端点一览

| 分组 | 方法 | URL | 说明 |
|------|------|-----|------|
| 用户画像 | POST | `/api/profile/chat` | 画像构建对话 |
| 用户画像 | GET | `/api/profile` | 获取当前画像 |
| 用户画像 | PUT | `/api/profile` | 手动更新画像 |
| 资源生成 | POST | `/api/resource/generate` | 请求生成资源 |
| 资源生成 | GET | `/api/resource/history` | 生成历史 |
| 资源生成 | GET | `/api/resource/{id}` | 资源详情 |
| 资源生成 | POST | `/api/resource/progress` | 上报进度 |
| 学习路径 | GET | `/api/learning-path` | 获取/生成路径 |
| 学习路径 | POST | `/api/learning-path/adjust` | 调整路径节点 |
| 学习路径 | GET | `/api/learning-path/resources/{id}` | 节点推送资源 |
| 智能辅导 | POST | `/api/tutor/ask` | RAG 答疑 |
| 学习分析 | GET | `/api/analytics/report` | 评估报告 |
| 学习分析 | GET | `/api/analytics/radar` | 雷达图数据 |
| 学习分析 | GET | `/api/analytics/suggestion` | AI 学习建议 |

> 完整请求/响应格式见 [API接口文档.md](./API接口文档.md)。

---

## 七、待实现模块

当前已完成 6 个智能体共 12 个端点（截至 2026-05-30），以下模块为总需求文档中规划但尚未实现的部分：

- 用户认证（JWT 登录/注册/Token 刷新）
- 首页仪表盘（推荐/进度/今日任务）
- 流式生成（SSE）
- 管理员上传资料（向量化入库）
- 个人中心

---

*AgentCore 是软件杯比赛项目"个性化学习智能体系统"的智能体核心模块。*
