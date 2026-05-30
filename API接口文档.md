# AgentCore API 接口文档

**Base URL:** `http://localhost:8080`
**通用请求头:** `X-User-Id`（用户ID，当前明文传递，后续切换JWT）
**Content-Type:** `application/json`

---

## 一、用户画像（画像构建智能体）

### 1.1 画像构建对话

智能体与学生自然对话，自动从对话中提取六维度画像信息并更新。

| 项目 | 内容 |
|------|------|
| **接口名称** | 画像构建对话 |
| **URL** | `POST /api/profile/chat` |
| **作用** | 发送对话消息给画像构建智能体，智能体自然回复并提取六维度画像 |
| **登录要求** | 是（X-User-Id） |

**入参：**

```json
{
  "userId": 1,
  "message": "你好，我在学习Java，感觉并发编程很难"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| userId | Long | 是 | 用户ID |
| message | String | 是 | 用户发送的消息内容 |

**返回示例：**

```json
{
  "reply": "你好！并发编程确实是Java中的一个难点，很多人在学习时都会遇到挑战。你之前有Java基础吗？",
  "profileUpdates": {
    "interestDirection": "Java",
    "knowledgeBase": "Java基础"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| reply | String | 智能体的自然语言回复 |
| profileUpdates | Map<String,String> | 本轮提取到的维度更新，无更新时为空对象`{}` |

---

### 1.2 获取用户画像

| 项目 | 内容 |
|------|------|
| **接口名称** | 获取用户画像 |
| **URL** | `GET /api/profile` |
| **作用** | 获取当前用户的完整六维度画像数据 |
| **登录要求** | 是（X-User-Id） |

**入参：**

```
Header: X-User-Id: 1
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| X-User-Id | Long | 是 | 请求头，用户ID |

**返回示例：**

```json
{
  "userId": 1,
  "knowledgeBase": "Java基础, Python入门",
  "cognitiveStyle": "动手实践型",
  "errorPreference": "并发编程, 数据库优化",
  "learningSpeed": "适中",
  "interestDirection": "后端开发, 微服务",
  "goalOrientation": "找到Java后端实习",
  "profileJson": null,
  "createdAt": "2026-05-30T17:00:00",
  "updatedAt": "2026-05-30T17:30:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| userId | Long | 用户ID |
| knowledgeBase | String | 知识基础 |
| cognitiveStyle | String | 认知风格（视觉型/文本型/动手实践型/听觉型） |
| errorPreference | String | 易错点偏好 |
| learningSpeed | String | 学习节奏（较快/适中/较慢） |
| interestDirection | String | 兴趣方向 |
| goalOrientation | String | 学习目标 |
| profileJson | Object | 扩展画像JSON |
| createdAt | String | 创建时间 |
| updatedAt | String | 更新时间 |

> **404:** 用户画像不存在

---

### 1.3 手动更新画像

| 项目 | 内容 |
|------|------|
| **接口名称** | 手动更新画像 |
| **URL** | `PUT /api/profile` |
| **作用** | 手动更新用户画像的指定维度 |
| **登录要求** | 是（X-User-Id） |

**入参：**

```
Header: X-User-Id: 1
```

```json
{
  "knowledgeBase": "Spring Boot, Java高级",
  "interestDirection": "后端开发, 分布式系统"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| X-User-Id | Long | 是 | 请求头，用户ID |
| Body | Map | 是 | key为维度英文名，value为更新值（支持部分更新） |

**返回示例：** 同 [1.2](#12-获取用户画像)

---

## 二、资源生成（资源生成协调智能体 + 通用资源生成智能体）

### 2.1 请求生成资源

协调智能体分析用户意图，自动判断资源类型，委托生成智能体生成个性化资源。支持5种资源类型：`lecture`（讲解文档）、`mindmap`（思维导图）、`exercise`（练习题）、`extended_reading`（拓展阅读）、`code_example`（代码案例）。

| 项目 | 内容 |
|------|------|
| **接口名称** | 请求生成资源 |
| **URL** | `POST /api/resource/generate` |
| **作用** | 传入自然语言需求，协调智能体分析意图后生成个性化学习资源 |
| **登录要求** | 是（X-User-Id） |

**入参：**

```json
{
  "requestText": "我想学习Java并发编程的线程池原理",
  "resourceType": "lecture",
  "knowledgePoint": "Java线程池"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| requestText | String | 是 | 用户自然语言需求描述 |
| resourceType | String | 否 | 期望类型，不指定则智能体自动判断 |
| knowledgePoint | String | 否 | 知识点名称 |

**返回示例：**

```json
{
  "resourceId": 1,
  "resourceType": "lecture",
  "title": "Java线程池原理与实践",
  "status": "ready",
  "message": "资源生成成功"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| resourceId | Long | 生成的资源ID |
| resourceType | String | 资源类型 |
| title | String | 资源标题 |
| status | String | 状态：ready/failed |
| message | String | 提示信息 |

---

### 2.2 获取生成历史

| 项目 | 内容 |
|------|------|
| **接口名称** | 获取生成历史 |
| **URL** | `GET /api/resource/history?page=1&size=20` |
| **作用** | 分页查询用户的历史资源生成记录 |
| **登录要求** | 是（X-User-Id） |

**入参：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| X-User-Id | Long | 是 | 请求头 |
| page | int | 否 | 页码，默认1 |
| size | int | 否 | 每页条数，默认20 |

**返回示例：**

```json
[
  {
    "id": 1,
    "resourceType": "lecture",
    "title": "Java线程池原理与实践",
    "content": "# Java线程池原理与实践\n\n## 概述...",
    "format": "markdown",
    "knowledgePoint": "Java线程池",
    "difficultyLevel": "medium",
    "estimatedTimeMinutes": 20,
    "status": "ready",
    "createdAt": "2026-05-30T18:00:00"
  }
]
```

---

### 2.3 获取资源详情

| 项目 | 内容 |
|------|------|
| **接口名称** | 获取资源详情 |
| **URL** | `GET /api/resource/{resourceId}` |
| **作用** | 获取指定资源的完整内容 |
| **登录要求** | 是（X-User-Id） |

**入参：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| X-User-Id | Long | 是 | 请求头 |
| resourceId | Long | 是 | 路径参数，资源ID |

**返回示例：** 同 [2.2](#22-获取生成历史) 中的单个对象（含完整 `content` 字段）

---

### 2.4 上报学习进度

| 项目 | 内容 |
|------|------|
| **接口名称** | 上报学习进度 |
| **URL** | `POST /api/resource/progress` |
| **作用** | 前端定时上报资源学习进度，用于学习记录追踪和分析 |
| **登录要求** | 是（X-User-Id） |

**入参：**

```json
{
  "resourceId": 1,
  "action": "reading",
  "progressPercent": 60,
  "timeSpentSeconds": 300
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| resourceId | Long | 是 | 资源ID |
| action | String | 是 | 学习动作（reading/practicing/completed） |
| progressPercent | Integer | 否 | 进度百分比 0-100 |
| timeSpentSeconds | Integer | 否 | 本次学习时长（秒） |

**返回：** HTTP 200（无响应体）

---

## 三、学习路径（学习路径规划+推送智能体）

### 3.1 获取/生成学习路径

基于用户画像自动规划个性化学习路径。如有活跃路径则返回已有，否则调用LLM生成新路径。

| 项目 | 内容 |
|------|------|
| **接口名称** | 获取/生成学习路径 |
| **URL** | `GET /api/learning-path` |
| **作用** | 基于用户画像自动规划个性化学习路径 |
| **登录要求** | 是（X-User-Id） |

**入参：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| X-User-Id | Long | 是 | 请求头 |

**返回示例：**

```json
{
  "id": 1,
  "title": "Java后端开发学习路径",
  "description": "从Java基础到Spring Boot微服务全面掌握",
  "subject": "后端开发",
  "status": "active",
  "totalNodes": 5,
  "completedNodes": 1,
  "nodes": [
    {
      "id": 1,
      "parentNodeId": null,
      "knowledgeId": "java-basics",
      "title": "Java基础巩固",
      "description": "复习Java核心语法与面向对象编程",
      "resourceTypeHint": "lecture",
      "sortOrder": 1,
      "estimatedTimeMinutes": 120,
      "status": "completed",
      "resourceIds": "1"
    },
    {
      "id": 2,
      "parentNodeId": 1,
      "knowledgeId": "concurrency",
      "title": "Java并发编程",
      "description": "深入学习多线程与并发工具",
      "resourceTypeHint": "lecture",
      "sortOrder": 2,
      "estimatedTimeMinutes": 180,
      "status": "in_progress",
      "resourceIds": "2,3,4,5"
    },
    {
      "id": 3,
      "parentNodeId": 2,
      "knowledgeId": "spring-boot",
      "title": "Spring Boot框架",
      "description": "学习Spring Boot核心特性与开发",
      "resourceTypeHint": "code_example",
      "sortOrder": 3,
      "estimatedTimeMinutes": 240,
      "status": "pending",
      "resourceIds": null
    }
  ],
  "createdAt": "2026-05-30T18:00:00"
}
```

---

### 3.2 手动调整学习路径

标记节点为完成、跳过或重置，更新路径整体进度。

| 项目 | 内容 |
|------|------|
| **接口名称** | 手动调整学习路径 |
| **URL** | `POST /api/learning-path/adjust` |
| **作用** | 标记节点状态（完成/跳过/重置） |
| **登录要求** | 是（X-User-Id） |

**入参：**

```json
{
  "nodeId": 2,
  "action": "complete"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| nodeId | Long | 是 | 节点ID |
| action | String | 是 | 操作：complete（完成）/ skip（跳过）/ reset（重置） |

**返回示例：** 同 [3.1](#31-获取生成学习路径)，路径节点状态已更新

---

### 3.3 获取知识点推送资源

| 项目 | 内容 |
|------|------|
| **接口名称** | 获取知识点推送资源 |
| **URL** | `GET /api/learning-path/resources/{nodeId}` |
| **作用** | 根据学习路径节点获取关联的学习资源列表 |
| **登录要求** | 是（X-User-Id） |

**入参：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| X-User-Id | Long | 是 | 请求头 |
| nodeId | Long | 是 | 路径参数，节点ID |

**返回示例：**

```json
[
  {
    "id": 2,
    "resourceType": "mindmap",
    "title": "并发编程知识体系",
    "knowledgePoint": "并发编程",
    "difficultyLevel": "medium",
    "estimatedTimeMinutes": 10,
    "status": "ready",
    "createdAt": "2026-05-30T18:00:00"
  },
  {
    "id": 3,
    "resourceType": "exercise",
    "title": "线程池参数配置练习",
    "knowledgePoint": "Java线程池",
    "difficultyLevel": "medium",
    "estimatedTimeMinutes": 30,
    "status": "ready",
    "createdAt": "2026-05-30T18:01:00"
  }
]
```

---

## 四、智能辅导（智能辅导智能体 — 加分项）

### 4.1 提问答疑

基于RAG向量检索知识库，结合LLM生成详细解答。检索到的知识库上下文也一并返回供调试。

| 项目 | 内容 |
|------|------|
| **接口名称** | 提问答疑 |
| **URL** | `POST /api/tutor/ask` |
| **作用** | 基于向量检索知识库的多模态智能答疑 |
| **登录要求** | 是（X-User-Id） |

**入参：**

```json
{
  "question": "什么是Java线程池？它的核心参数有哪些？",
  "imageUrls": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| question | String | 是 | 学生提问内容 |
| imageUrls | List\<String\> | 否 | 图片URL列表（预留多模态支持） |

**返回示例：**

```json
{
  "answer": "## 什么是线程池\n\n线程池是一种多线程处理形式...\n\n### 核心参数\n1. **corePoolSize**：核心线程数，线程池中一直保持存活的线程数量\n2. **maximumPoolSize**：最大线程数，线程池中允许的最大线程数量\n3. **keepAliveTime**：空闲线程存活时间\n4. **workQueue**：工作队列，用于存放待执行的任务\n\n### 常见误区\n- 误区1: corePoolSize必须大于maximumPoolSize（实际上corePoolSize <= maximumPoolSize）\n- 误区2: 线程池线程越多越好（线程过多会导致上下文切换开销增大）\n\n### 延伸思考\n你可以尝试自己实现一个简单的线程池来加深理解。",
  "contextSnippets": [
    "Java线程池核心原理: 线程池是一种多线程处理形式，处理过程中将任务添加到队列..."
  ],
  "confidence": 0.8
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| answer | String | Markdown格式的详细解答 |
| contextSnippets | List\<String\> | 检索到的知识库上下文片段 |
| confidence | Double | 置信度 0-1，0.8以上表示检索到相关知识 |

---

## 五、学习分析（学习效果评估智能体 — 加分项）

### 5.1 获取评估报告

| 项目 | 内容 |
|------|------|
| **接口名称** | 获取评估报告 |
| **URL** | `GET /api/analytics/report` |
| **作用** | 多维度学习效果评估，汇总学习时长、练习正确率、各知识点掌握度 |
| **登录要求** | 是（X-User-Id） |

**入参：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| X-User-Id | Long | 是 | 请求头 |

**返回示例：**

```json
{
  "totalStudyMinutes": 350,
  "resourceCount": 8,
  "exerciseCount": 15,
  "correctRate": 73.3,
  "masteryByKnowledgePoint": [
    {
      "knowledgePoint": "Java线程池",
      "masteryScore": 75.0,
      "exerciseCount": 10,
      "correctCount": 8
    },
    {
      "knowledgePoint": "并发编程",
      "masteryScore": 60.0,
      "exerciseCount": 5,
      "correctCount": 3
    }
  ],
  "weeklyActivity": []
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| totalStudyMinutes | Integer | 总学习时长（分钟） |
| resourceCount | Integer | 已学习资源数量 |
| exerciseCount | Integer | 练习总数 |
| correctRate | BigDecimal | 正确率 0-100 |
| masteryByKnowledgePoint | List | 各知识点掌握度明细 |
| weeklyActivity | List | 每周活动统计 |

---

### 5.2 获取雷达图数据

| 项目 | 内容 |
|------|------|
| **接口名称** | 获取雷达图数据 |
| **URL** | `GET /api/analytics/radar` |
| **作用** | 返回六维度能力数值，供前端渲染雷达图 |
| **登录要求** | 是（X-User-Id） |

**入参：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| X-User-Id | Long | 是 | 请求头 |

**返回示例：**

```json
{
  "labels": ["知识基础", "认知能力", "练习正确率", "学习速度", "兴趣广度", "目标达成"],
  "scores": [65, 80, 73, 65, 60, 60],
  "details": []
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| labels | List\<String\> | 六个维度标签 |
| scores | List\<Integer\> | 各维度分值 0-100 |
| details | List | 维度详细数据 |

---

### 5.3 获取AI学习建议

| 项目 | 内容 |
|------|------|
| **接口名称** | 获取AI学习建议 |
| **URL** | `GET /api/analytics/suggestion` |
| **作用** | 基于学习数据由LLM生成个性化改进建议 |
| **登录要求** | 是（X-User-Id） |

**入参：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| X-User-Id | Long | 是 | 请求头 |

**返回示例：**

```json
{
  "suggestions": [
    "并发编程是当前的薄弱环节，建议每天安排30分钟专项练习",
    "可以利用思维导图整理已学知识点之间的联系",
    "学习速度适中，建议每周完成2-3个学习路径节点"
  ],
  "focusAreas": [
    "并发编程",
    "数据库优化"
  ],
  "recommendedResourceIds": []
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| suggestions | List\<String\> | 个性化改进建议列表 |
| focusAreas | List\<String\> | 需重点关注的知识领域 |
| recommendedResourceIds | List\<Long\> | 推荐资源ID列表 |

---

## 附录：公共说明

### 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数缺失或不合法（如 requestText 为空） |
| 404 | 资源/画像不存在 |
| 500 | 服务端异常（如LLM调用失败） |

### 六维度画像说明

| 维度英文名 | 中文名 | 示例值 |
|-----------|--------|--------|
| knowledgeBase | 知识基础 | "Java基础, Python入门" |
| cognitiveStyle | 认知风格 | "动手实践型" / "视觉型" / "文本型" |
| errorPreference | 易错点偏好 | "并发编程, 数据库优化" |
| learningSpeed | 学习节奏 | "较快" / "适中" / "较慢" |
| interestDirection | 兴趣方向 | "后端开发, 微服务" |
| goalOrientation | 学习目标 | "找到Java后端实习" |

### 五种资源类型

| 类型值 | 中文名 | 说明 |
|--------|--------|------|
| lecture | 讲解文档 | 结构化讲解，含概念、示例、总结 |
| mindmap | 思维导图 | 层次化知识结构，多级标题 |
| exercise | 练习题 | 选择/填空/简答，含答案和解析 |
| extended_reading | 拓展阅读 | 推荐阅读材料和延伸方向 |
| code_example | 代码案例 | 可运行代码 + 注释解析 |
