# 连续会话聊天系统 - 快速开始

## 功能概述

✅ **已实现功能：**

1. **大小模型协作**
   - 小模型（Haiku）处理简单问题，搜索知识库
   - 大模型（Sonnet/Opus）处理复杂问题，深度分析
   - 小模型对大模型回答进行质量分析

2. **连续对话**
   - 支持多轮对话，保存历史记录
   - 自动维护对话上下文

3. **会话管理**
   - 创建新会话
   - 查看会话列表
   - 获取会话详情
   - 删除会话

## 快速部署

### 1. 数据库迁移

```bash
# 进入项目目录
cd "c:\Users\wdx\Desktop\基于大模型的个性化资源生成与学习多智能体系统"

# 运行迁移脚本
python common/db/bootstrap_chat.py
```

### 2. 启动服务

```bash
# 启动 agent-service
cd services/agent_service
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

### 3. 测试接口

```bash
# 运行测试脚本
python tests/test_chat_service.py
```

或使用 curl 测试：

```bash
# 创建会话
curl -X POST http://localhost:8002/chat/sessions/new \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "title": "Python学习"}'

# 发送消息
curl -X POST http://localhost:8002/chat/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": 1,
    "user_id": 1,
    "content": "什么是Python装饰器？"
  }'

# 获取会话列表
curl "http://localhost:8002/chat/sessions?user_id=1"

# 获取会话详情
curl "http://localhost:8002/chat/sessions/1?user_id=1"
```

## API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/chat/sessions/new` | 创建新会话 |
| GET | `/chat/sessions` | 获取会话列表 |
| GET | `/chat/sessions/{id}` | 获取会话详情 |
| POST | `/chat/chat` | 发送消息 |
| DELETE | `/chat/sessions/{id}` | 删除会话 |

## 前端集成

### 安装前端 API

前端 API 文件已创建：`web-app/src/api/chat.ts`

### 使用示例

```typescript
import { createChatSession, sendChatMessage, listChatSessions } from '@/api/chat'

// 创建新会话
const session = await createChatSession({
  user_id: 1,
  title: 'Python 学习',
  subject: 'Python'
})

// 发送消息
const response = await sendChatMessage({
  session_id: session.id,
  user_id: 1,
  content: '什么是装饰器？'
})

console.log(response.content)      // AI 回答
console.log(response.model_used)   // small_model 或 large_model
console.log(response.metadata)     // 分析结果
```

## 核心逻辑

### 模型选择策略

```python
def _should_use_large_model(question, kb_result):
    # 1. 知识库无内容 → 大模型
    if not kb_result["found"]:
        return True
    
    # 2. 复杂问题（包含分析类关键词）→ 大模型
    complex_keywords = ["为什么", "如何", "分析", "对比", "解释", "证明"]
    if any(kw in question for kw in complex_keywords):
        return True
    
    # 3. 问题较长 → 大模型
    if len(question) > 100:
        return True
    
    # 否则使用小模型
    return False
```

### 工作流程

```
用户问题
    ↓
小模型搜索知识库
    ↓
决策：使用哪个模型？
    ├─ 简单 → 小模型回答（基于知识库）
    └─ 复杂 → 大模型深度回答 → 小模型分析质量
              ↓
         返回回答 + 元数据
```

## 文件结构

```
├── common/
│   ├── models/learning.py              # 数据库模型（新增 ChatSession, ChatMessage）
│   ├── schemas/agent.py                # API 数据模型
│   └── db/
│       ├── bootstrap_chat.py           # 数据库迁移脚本
│       └── migrations/add_chat_tables.py
│
├── services/agent_service/
│   ├── app/
│   │   ├── main.py                     # 主应用（已添加 chat 路由）
│   │   ├── api/routes/chat.py          # 聊天 API 路由
│   │   └── services/chat_service.py    # 聊天服务核心逻辑
│
├── web-app/src/api/chat.ts             # 前端 API
├── tests/test_chat_service.py          # 测试脚本
└── docs/
    ├── chat-system-guide.md            # 详细文档
    └── QUICKSTART.md                   # 本文件
```

## 数据库表

### chat_sessions
```sql
CREATE TABLE chat_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    subject VARCHAR(50),
    is_active BOOLEAN DEFAULT 1,
    last_message_at DATETIME,
    created_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### chat_messages
```sql
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    model_used VARCHAR(50),
    metadata_json JSON,
    created_at DATETIME,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
);
```

## 下一步

1. ✅ 数据库表已创建
2. ✅ 后端服务已实现
3. ✅ API 路由已配置
4. ✅ 前端接口已准备
5. ⏳ 运行测试验证功能
6. ⏳ 集成到前端界面

## 技术栈

- **后端**: FastAPI, SQLAlchemy, LangChain
- **数据库**: SQLite (可切换 PostgreSQL)
- **AI 模型**: 
  - 小模型: Haiku (快速响应)
  - 大模型: Sonnet/Opus (深度分析)
- **前端**: Vue 3, TypeScript, Axios

## 性能优化

- 小模型用于简单问题，响应快
- 知识库缓存减少重复搜索
- 对话历史限制在最近10条
- 大模型仅在必要时调用

## 故障恢复

- 模型调用失败自动降级
- 知识库不可用时使用模型内置知识
- 完整的错误处理和日志记录

---

更多详情请查看：[chat-system-guide.md](./chat-system-guide.md)
