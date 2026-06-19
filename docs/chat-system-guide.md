# 连续会话聊天系统 - 大小模型协作

## 概述

本系统实现了基于大小模型协作的智能问答系统，支持连续对话和会话管理。

### 核心特性

1. **大小模型协作**
   - 小模型（Haiku）：处理简单问题，搜索知识库，快速响应
   - 大模型（Sonnet/Opus）：处理复杂问题，深度分析，全面讲解
   - 小模型分析大模型回答：质量评估，提取要点，生成建议

2. **智能决策**
   - 根据问题复杂度自动选择模型
   - 知识库覆盖度判断
   - 问题长度和关键词分析

3. **连续会话**
   - 保存对话历史
   - 支持上下文理解
   - 多会话管理

4. **会话管理**
   - 创建新会话
   - 查看会话列表
   - 获取会话详情
   - 删除会话

## 数据流程

```
用户提问
    ↓
1. 小模型搜索知识库
    ↓
2. 决策：使用哪个模型？
    ├─→ 知识库有内容 + 问题简单 → 小模型直接回答
    └─→ 知识库无内容 或 问题复杂 → 大模型深度回答
                                        ↓
                                   3. 小模型分析回答质量
                                        ↓
                                   返回结果 + 分析
```

## API 接口

### 1. 创建新会话

```http
POST /chat/sessions/new
Content-Type: application/json

{
  "user_id": 1,
  "title": "Python 学习讨论",
  "subject": "Python"
}
```

**响应:**
```json
{
  "id": 1,
  "user_id": 1,
  "title": "Python 学习讨论",
  "subject": "Python",
  "is_active": true,
  "created_at": "2026-06-10T10:00:00",
  "last_message_at": "2026-06-10T10:00:00",
  "message_count": 0,
  "messages": []
}
```

### 2. 发送消息

```http
POST /chat/chat
Content-Type: application/json

{
  "session_id": 1,
  "user_id": 1,
  "content": "什么是 Python 装饰器？",
  "context": {
    "current_topic": "Python 进阶"
  }
}
```

**响应:**
```json
{
  "session_id": 1,
  "message_id": 2,
  "role": "assistant",
  "content": "Python 装饰器是一种设计模式...",
  "model_used": "small_model",
  "metadata": {
    "source": "knowledge_base",
    "confidence": "high"
  },
  "created_at": "2026-06-10T10:01:00"
}
```

### 3. 获取会话列表

```http
GET /chat/sessions?user_id=1&limit=50
```

**响应:**
```json
[
  {
    "id": 1,
    "user_id": 1,
    "title": "Python 学习讨论",
    "subject": "Python",
    "is_active": true,
    "created_at": "2026-06-10T10:00:00",
    "last_message_at": "2026-06-10T10:05:00",
    "message_count": 8
  }
]
```

### 4. 获取会话详情

```http
GET /chat/sessions/1?user_id=1
```

**响应:** 返回完整的会话详情，包含所有消息历史

### 5. 删除会话

```http
DELETE /chat/sessions/1?user_id=1
```

**响应:**
```json
{
  "status": "deleted",
  "session_id": "1"
}
```

## 模型选择逻辑

### 使用大模型的情况：

1. **知识库无相关内容** - 需要大模型的通用知识
2. **问题包含复杂关键词** - "为什么"、"如何"、"分析"、"对比"、"解释"、"证明"
3. **问题较长** - 超过100字符，表示需要全面回答

### 使用小模型的情况：

- 知识库有相关内容
- 问题简单直接
- 问题较短

## 元数据说明

### 小模型回答的 metadata:
```json
{
  "source": "knowledge_base",
  "confidence": "high"
}
```

### 大模型回答的 metadata（包含小模型分析）:
```json
{
  "source": "large_model_with_analysis",
  "analysis": {
    "completeness": 5,
    "clarity": 4,
    "key_points": ["装饰器语法", "应用场景"],
    "suggestions": ["练习编写装饰器", "理解闭包概念"]
  }
}
```

## 数据库表结构

### chat_sessions
- id: 会话ID
- user_id: 用户ID
- title: 会话标题
- subject: 学科
- is_active: 是否活跃
- created_at: 创建时间
- last_message_at: 最后消息时间

### chat_messages
- id: 消息ID
- session_id: 会话ID
- role: 角色（user/assistant/system）
- content: 消息内容
- model_used: 使用的模型（small_model/large_model/fallback）
- metadata_json: 元数据（JSON格式）
- created_at: 创建时间

## 部署步骤

### 1. 运行数据库迁移

```bash
# 方法1：使用 bootstrap 脚本
cd common/db
python bootstrap_chat.py

# 方法2：使用 alembic（如果配置了）
alembic upgrade head
```

### 2. 启动服务

```bash
cd services/agent_service
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

### 3. 测试接口

```bash
# 创建会话
curl -X POST http://localhost:8002/chat/sessions/new \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "title": "测试会话"}'

# 发送消息
curl -X POST http://localhost:8002/chat/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": 1,
    "user_id": 1,
    "content": "什么是Python？"
  }'
```

## 前端集成示例

```typescript
import { createChatSession, sendChatMessage, listChatSessions } from '@/api/chat'

// 创建新会话
const session = await createChatSession({
  user_id: currentUser.id,
  title: '新对话',
  subject: 'Python'
})

// 发送消息
const response = await sendChatMessage({
  session_id: session.id,
  user_id: currentUser.id,
  content: '你好，请解释装饰器'
})

console.log(response.content) // AI 回答
console.log(response.model_used) // small_model 或 large_model
console.log(response.metadata) // 分析结果

// 获取会话列表
const sessions = await listChatSessions(currentUser.id)
```

## 性能优化建议

1. **缓存策略**
   - 对常见问题的知识库搜索结果进行缓存
   - 缓存小模型的分析结果

2. **批量处理**
   - 支持批量获取会话列表
   - 分页加载消息历史

3. **异步处理**
   - 大模型生成可以异步处理
   - 使用 WebSocket 实现实时响应

4. **模型优化**
   - 根据用户反馈调整模型选择策略
   - 定期评估小模型分析的准确性

## 故障处理

### Fallback 机制

当模型调用失败时，系统会自动降级：

1. **小模型失败** → 返回知识库摘要
2. **大模型失败** → 返回友好提示，建议重试
3. **知识库不可用** → 使用模型内置知识

### 错误码

- 404: 会话不存在或无权访问
- 500: 模型调用失败或系统错误

## 扩展功能建议

1. **多轮对话优化**
   - 增加对话轮次限制
   - 支持会话摘要

2. **个性化**
   - 根据用户画像调整回答风格
   - 记录用户偏好（详细/简洁）

3. **协作增强**
   - 多个小模型投票决策
   - 大模型结果的多维度分析

4. **监控指标**
   - 模型选择准确率
   - 用户满意度反馈
   - 平均响应时间
