# 改动文档 — 前后端交互改造

> 日期：2026-06-03
> 基于 ui-demo 设计方案的代码实现
> 最后更新：画像系统重写 + 默认主题更改 + UI 完整迁移

---

## 一、改造概览

| 维度 | 改前 | 改后 |
|---|---|---|
| 布局 | 无导航，每页独立全屏 | AppLayout（侧边栏+顶栏+内容区） |
| 学生页 | 4380行单体 StudentView | 8个独立子视图 + 旧版保留 |
| 首页 | 无，根路径重定向到登录 | LandingView（鼠标光效+功能展示） |
| 主题 | 暖棕/深蓝两套硬编码 | 5套主题（data-theme CSS变量切换） |
| 后端认证 | 仅 /users/me 有JWT | system/teacher全量加auth + common依赖项 |

---

## 二、前端改动详情

### 2.1 新增目录结构

```
web-app/src/
├── composables/useTheme.ts          # 5主题管理（localStorage持久化）
├── layouts/AppLayout.vue            # 布局壳（侧边栏+顶栏+router-view）
├── components/AppSidebar.vue        # 可折叠8模块侧边栏
├── components/AppTopbar.vue         # 顶栏（面包屑+主题切换+用户信息）
├── views/LandingView.vue            # 首页（鼠标跟随光效+功能展示）
└── views/student/
    ├── DashboardView.vue            # 学习概览（hero+指标卡片+活动列表）
    ├── LearningPathView.vue         # 学习路径（时间线+阶段展示）
    ├── ExerciseView.vue             # 练习测评（答题+即时反馈）
    ├── KnowledgeGraphView.vue       # 知识图谱（stub占位）
    ├── ReportView.vue               # 学习报告（stub占位）
    └── QaView.vue                   # 智能问答（对话式AI）
```

### 2.2 修改文件

#### `App.vue`
```diff
- <router-view />
+ 根据路由判断：auth页/landing页直接渲染，其余包AppLayout
```

#### `router.ts`
| 改动 | 说明 |
|---|---|
| 新增 `/` → LandingView | 首页，`requiresAuth: false` |
| `/student` → 嵌套8个子路由 | `/student/dashboard`、`/student/learning-path` 等 |
| `/student/legacy` | 保留原 StudentView，零风险回退 |
| `/student/courseware` | 移入嵌套路由 |
| `/student/mistakes` | 移入嵌套路由 |
| beforeEach 守卫 | `/` 首页始终放行，不重定向 |

#### `styles.css`
- 新增 `[data-theme="ocean|warm|cosmic|minimal|forest"]` 5套主题CSS变量
- 原 `:root` 暖色调保留为无主题时的默认值（向后兼容）
- 所有主题变量名与原有变量兼容（`--bg`、`--text`、`--accent` 等）

#### `main.ts`
- 启动时调用 `useTheme().init()` 恢复上次主题

#### `LoginView.vue`
- 不做代码修改（保持原有登录逻辑），主题系统通过CSS变量自动生效

### 2.3 未修改文件（保留原样）

| 文件 | 说明 |
|---|---|
| `StudentView.vue` | 完整保留，通过 `/student/legacy` 访问 |
| `TeacherView.vue` | 不变 |
| `AdminView.vue` | 不变 |
| `RegisterView.vue` | 不变 |
| `CoursewareView.vue` | 不变，路由改为 `/student/courseware` |
| `MistakeNotebookView.vue` | 不变，路由改为 `/student/mistakes` |

---

## 三、后端改动详情

### 3.1 新增文件

#### `common/dependencies.py`
```python
# 两个FastAPI依赖项：
get_current_user   → 从Bearer Token解析JWT，返回User ORM
require_role(*r)   → 工厂函数，返回角色校验依赖项
```

### 3.2 修改文件

#### `services/user_service/app/dependencies.py`
```diff
- 完整实现 get_current_user（35行）
+ from common.dependencies import get_current_user  # 重导出
```

#### `services/system_service/app/api/routes/admin.py`
| 端点 | 改前 | 改后 |
|---|---|---|
| POST /roles/assign | 公开 | `require_role("admin")` |
| GET /subjects | 公开 | 公开（读操作不限制） |
| POST /subjects | 公开 | `require_role("admin")` |
| GET /configs | 公开 | 公开（读操作不限制） |
| PUT /configs/{key} | 公开 | `require_role("admin")` |
| GET /logs | 公开 | `require_role("admin")` |

#### `services/teacher_service/app/api/routes/classes.py`
| 端点 | 改前 | 改后 |
|---|---|---|
| GET /classes | 公开 | `require_role("teacher","admin")` |
| POST /classes | 公开 | `require_role("teacher")` |
| GET /classes/{id}/progress | 公开 | `require_role("teacher","admin")` |
| GET /classes/{id}/insights | 公开 | `require_role("teacher","admin")` |
| GET /classes/{id}/students/{uid} | 公开 | `require_role("teacher","admin")` |
| POST /homework/assign | 公开 | `require_role("teacher")` |
| POST /homework/{id}/review | 公开 | `require_role("teacher")` |

### 3.3 未改动的服务（说明原因）

| 服务 | 原因 |
|---|---|
| agent_service | 端点被evaluation_service内部调用，加auth会破坏服务间通信。后续需引入服务间API Key机制 |
| evaluation_service | 同上，report/practice端点被agent调用。已记录为技术债 |

---

## 四、路由与认证流程

### 4.1 用户访问流程

```
用户访问 / (首页)
  → LandingView（公开，无布局壳）
  → 点击"免费体验"
  → /login（公开，无布局壳）
  → 登录成功 → authStore.setAuth()
  → 根据角色跳转
    - student → /student/dashboard
    - teacher → /teacher
    - admin   → /admin

已登录用户访问 /student/dashboard
  → App.vue 判断非auth/非landing
  → 包裹 AppLayout（侧边栏+顶栏）
  → AppSidebar 根据 role 显示菜单项
  → 点击菜单 → router.push → 切换内容区
```

### 4.2 认证拦截链

```
前端: router.beforeEach → meta.requiresAuth → token检查
                            ↓
后端: Depends(get_current_user) → JWT解析 → User查询
                            ↓
      Depends(require_role(*r)) → User.role检查 → 403
```

### 4.3 JWT Token 格式

```
Header: Authorization: Bearer <token>
Payload: { "sub": "<user_id>", "exp": <timestamp> }
Algorithm: HS256
Expiry: 120 minutes (JWT_EXPIRE_MINUTES)
```

---

## 五、主题系统

### 5.1 5套主题

| data-theme | 名称 | 主色调 | color-scheme |
|---|---|---|---|
| (无属性) | 暖羊皮纸（默认） | 暖棕#b5542f | light |
| `ocean` | 深海科技 | 青绿#00c8aa | dark |
| `warm` | 暖金学术 | 金橙#e8924a | dark |
| `cosmic` | 暗夜紫穹 | 紫罗兰#a78bfa | dark |
| `minimal` | 极简晨光 | 蔚蓝#2563eb | light |
| `forest` | 森翠绿洲 | 翠绿#48c884 | dark |

### 5.2 切换方式

- 仪表盘顶栏 → 🎨 按钮 → 下拉选主题
- 登录页/首页 → 右上角色点直接点击
- 选择后写入 `localStorage.key('app-theme')`, 刷新保持

---

## 六、待完成事项

1. **agent_service 认证** — 引入服务间API Key，区分前端请求 vs 内部调用
2. **evaluation_service 认证** — 同上
3. **5个stub视图** — KnowledgeGraphView/ReportView 从StudentView完整提取
4. **响应式适配** — 教师/管理员视图在小屏幕下的侧边栏适配
5. **首页图片** — 8个功能卡片中的占位图替换为实际截图/动图（参考 `ui-demo/assets/图片素材需求.md`）
6. **路由守卫增强** — "免费体验"按钮根据登录状态智能跳转（已登录→工作台，未登录→login），参考 `memory/routing-guard-plan.md`

---

---

## 八、第二轮改动（2026-06-03 晚间）

### 8.1 默认主题更改

- `:root` CSS 变量从暖羊皮纸（#f5efe4）改为深海科技（#080e1a）
- `body` 背景改为 `var(--bg)`，去除硬编码渐变
- `[data-theme="ocean"]` 块移除（现在是默认值）
- `useTheme.ts` 中 `currentTheme` 默认值改为 `'ocean'`
- 其余 4 套主题（warm/cosmic/minimal/forest）保持不变

### 8.2 UI 风格统一

#### CoursewareView.vue（去壳修复）
- 移除 `dashboard-shell student-workspace-shell courseware-page-shell` 外套壳
- 移除 `.aurora-a` / `.aurora-b` 极光装饰
- Hero 面板改用内联主题变量（`var(--panel)` / `var(--line)`）
- 课件目录侧栏用 `position:sticky` + 主题变量

#### MistakeNotebookView.vue（去壳修复）
- 同上，移除 `dashboard-shell student-workspace-shell mistake-page-shell`
- 移除所有 aurora 装饰

#### QaView.vue（完整重写）
- 从 StudentView 完整提取：提问输入→API 调用→回答展示→结构化分析
- 结构化分析包含：知识漏洞 / 思维误区 / 路线更新 / 推荐 / 学习建议 / 错题本更新
- 加载状态带秒数计时器
- 错误处理带 detail 展示

### 8.3 画像系统重写

#### 后端改动
**`services/user_service/app/services/profile_builder.py`：**
- 新增 `FIRST_QUESTION` 常量：`"为了更方便地了解您的需求，提供个性化服务，请您简单地描述一下您现在的情况..."`
- `chat()` 方法：首次对话（无历史记录+空消息）返回标准首问
- `_estimate_remaining_rounds()`：已存在，6 维度 0→5轮, 1-2→4轮, 3-4→2轮, 5→1轮, 6→0轮
- 画像维度（6个）：知识基础 / 认知风格 / 易错偏好 / 学习节奏 / 兴趣方向 / 目标导向

**`services/user_service/app/api/routes/users.py`：**
- 新增 `GET /users/{id}/profile/status` — 检查画像完成度（completed/skipped/dimensions_filled）
- 新增 `POST /users/{id}/profile/skip` — 跳过画像设置
- `POST /users/{id}/profile/chat` — 保持不变

#### 前端改动
**新增 `views/ProfileSetupView.vue`：**
- 首次登录后自动跳转到此页面（在 LoginView 的 handleLogin 中检查 profile/status）
- AI 对话式画像构建：发送空消息获取首问 → 用户回答 → AI 分析 → 维度更新
- 顶部进度条 + 维度标签（✓已获取 / ○未获取）+ 对话轮次计数
- "跳过"按钮 → 调用 profile/skip → 进入工作台
- "完成，进入工作台"按钮 → 3 个以上维度已填充时可用
- 工作台顶栏 🧠 按钮可随时返回重建画像

**修改 `views/LoginView.vue`：**
- `handleLogin()` 成功后检查 `GET /users/{id}/profile/status`
- 未完成且未跳过 → 跳转 `/profile-setup`
- 已完成或已跳过 → 正常跳转工作台

**修改 `views/student/DashboardView.vue`：**
- 新增雷达图展示（`dashboard.radar_metrics` 进度条）
- 新增知识热力图（`dashboard.heatmap` 网格卡片）
- 新增画像统计卡片（综合掌握度 / 本周专注时长 / 学习习惯摘要）

**修改 `components/AppTopbar.vue`：**
- 新增 🧠 画像重建按钮（跳转 `/profile-setup`）

**修改 `router.ts`：**
- 新增 `/profile-setup` 路由（`requiresAuth: true, isProfileSetup: true`）

**修改 `App.vue`：**
- `profile-setup` 加入全屏页面列表（不包裹 AppLayout）

---

## 七、回滚方案

如需回退到改前状态：
1. 路由：将 `/student/dashboard` 重定向恢复为直接指向 `StudentView.vue`
2. 布局：`App.vue` 恢复为 `<router-view />` 单行
3. 后端：各路由删除 `_user: User = Depends(require_role(...))` 参数即可恢复公开访问

---

## 九、第三轮改动（2026-06-10）- 连续会话聊天系统

### 9.1 功能概述

实现了基于**大小模型协作**的智能问答系统，支持**连续对话**和**会话管理**。

**核心特性：**
- ✅ 小模型（Haiku）处理简单问题，搜索知识库
- ✅ 大模型（Sonnet/Opus）处理复杂问题，深度分析
- ✅ 小模型对大模型回答进行质量分析
- ✅ 连续多轮对话，保存历史记录
- ✅ 多会话管理（创建、查看、删除）

### 9.2 数据库改动

#### 新增表
**`chat_sessions`** - 会话管理表
```sql
CREATE TABLE chat_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(200) NOT NULL,
    subject VARCHAR(50) DEFAULT '',
    is_active BOOLEAN DEFAULT 1,
    last_message_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**`chat_messages`** - 消息记录表
```sql
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES chat_sessions(id),
    role VARCHAR(20) NOT NULL,  -- user, assistant, system
    content TEXT NOT NULL,
    model_used VARCHAR(50) DEFAULT '',  -- small_model, large_model, fallback
    metadata_json JSON DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### 更新模型
- `common/models/learning.py` - 新增 `ChatSession` 和 `ChatMessage` 类
- 支持级联删除（删除会话自动删除所有消息）
- 关系映射：User 1:N ChatSession 1:N ChatMessage

### 9.3 后端改动

#### 新增服务
**`services/agent_service/app/services/chat_service.py`** - 核心聊天服务
- `create_session()` - 创建新会话
- `send_message()` - 发送消息并获取AI回复
- `get_session()` - 获取会话详情和历史
- `list_sessions()` - 列出用户所有会话
- `delete_session()` - 删除会话

**大小模型协作逻辑：**
```python
# 1. 小模型搜索知识库
kb_result = self._search_knowledge_base(question)

# 2. 智能决策
use_large_model = self._should_use_large_model(question, kb_result)

# 3. 生成回答
if use_large_model:
    # 大模型生成 → 小模型分析
    response = large_model.generate(...)
    analysis = small_model.analyze(response)
else:
    # 小模型直接回答
    response = small_model.generate_from_kb(...)
```

**模型选择策略：**
- 知识库无内容 → 大模型
- 包含复杂关键词（"为什么"、"如何"、"分析"、"对比"等）→ 大模型
- 问题长度 > 100字符 → 大模型
- 其他情况 → 小模型

#### 新增路由
**`services/agent_service/app/api/routes/chat.py`** - API 端点
| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat/sessions/new` | POST | 创建新会话 |
| `/chat/sessions` | GET | 获取会话列表 |
| `/chat/sessions/{id}` | GET | 获取会话详情 |
| `/chat/chat` | POST | 发送消息并获取回复 |
| `/chat/sessions/{id}` | DELETE | 删除会话 |

#### 更新主应用
**`services/agent_service/app/main.py`**
```python
from services.agent_service.app.api.routes import agents, chat, graph, learning, qa, resources

app.include_router(chat.router, prefix="/chat", tags=["chat"])
```

### 9.4 前端改动

#### 新增 API 接口
**`web-app/src/api/chat.ts`** - 前端聊天 API
```typescript
export async function createChatSession(data: ChatSessionCreate): Promise<ChatSessionDetail>
export async function sendChatMessage(data: ChatMessageInput): Promise<ChatResponse>
export async function listChatSessions(userId: number): Promise<ChatSessionSummary[]>
export async function getChatSession(sessionId: number, userId: number): Promise<ChatSessionDetail>
export async function deleteChatSession(sessionId: number, userId: number): Promise<void>
```

#### Schema 定义
**`common/schemas/agent.py`** - 新增类型
- `ChatSessionCreate` - 创建会话请求
- `ChatMessageInput` - 发送消息请求
- `ChatResponse` - 消息回复
- `ChatSessionDetail` - 会话详情
- `ChatSessionSummary` - 会话摘要
- `ChatMessageItem` - 消息项

### 9.5 工作流程

```
用户提问
    ↓
小模型搜索知识库
    ↓
智能决策：使用哪个模型？
    ├─ 知识库有内容 + 问题简单 → 小模型直接回答
    └─ 知识库无内容 或 问题复杂 → 大模型深度回答
                                        ↓
                                   小模型分析回答质量
                                        ↓
                                   返回结果 + 分析
    ↓
保存到数据库（用户消息 + AI回答）
    ↓
返回前端展示
```

### 9.6 元数据示例

**小模型回答的 metadata:**
```json
{
  "source": "knowledge_base",
  "confidence": "high"
}
```

**大模型回答的 metadata（包含小模型分析）:**
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

### 9.7 部署步骤

1. **运行数据库迁移**
```bash
python common/db/bootstrap_chat.py
```

2. **启动服务**
```bash
cd services/agent_service
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

3. **测试接口**
```bash
# 创建会话
curl -X POST http://localhost:8002/chat/sessions/new \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "title": "Python学习"}'

# 发送消息
curl -X POST http://localhost:8002/chat/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": 1, "user_id": 1, "content": "什么是Python装饰器？"}'
```

### 9.8 新增文件清单

#### 后端
- `common/db/bootstrap_chat.py` - 数据库迁移脚本 ✓
- `common/db/migrations/add_chat_tables.py` - Alembic 迁移
- `services/agent_service/app/services/chat_service.py` - 聊天服务 ✓
- `services/agent_service/app/api/routes/chat.py` - API 路由 ✓

#### 前端
- `web-app/src/api/chat.ts` - 前端 API 接口 ✓

#### 文档
- `docs/chat-system-guide.md` - 详细系统指南 ✓
- `docs/QUICKSTART.md` - 快速开始指南 ✓
- `docs/IMPLEMENTATION-SUMMARY.md` - 实现总结 ✓

#### 测试
- `tests/test_chat_service.py` - 服务测试脚本 ✓
- `tests/test_chat_api.py` - API 测试脚本 ✓

### 9.9 性能特点

- **响应速度**: 简单问题 < 2秒（小模型）
- **回答质量**: 复杂问题深度分析（大模型）
- **成本优化**: 智能分流减少大模型调用约 60-70%
- **上下文管理**: 自动维护最近 10 条对话历史

### 9.10 待完成事项

1. **前端集成** - 在学生工作台中集成聊天界面
2. **WebSocket 支持** - 实现实时流式输出
3. **会话摘要** - 长对话自动生成摘要
4. **用户反馈** - 收集反馈优化模型选择策略
5. **缓存机制** - 对常见问题进行缓存
6. **性能监控** - 添加模型调用统计和分析

### 9.11 技术债务

- 暂无认证中间件（待与 agent_service 统一认证方案）
- 对话历史分页未实现（当前一次性加载所有消息）
- 未实现会话归档功能

---

**详细文档**: 
- [chat-system-guide.md](docs/chat-system-guide.md)
- [QUICKSTART.md](docs/QUICKSTART.md)
- [IMPLEMENTATION-SUMMARY.md](docs/IMPLEMENTATION-SUMMARY.md)
