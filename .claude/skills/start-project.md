---
name: start-project
description: 启动整个智学平台项目（6 后端 + 前端），含环境检查、数据库验证和常见问题排错
model: haiku
---

# 启动智学平台项目

## 项目架构

| 服务 | 端口 | 启动命令 |
|------|------|----------|
| user-service | 8001 | `python -m uvicorn services.user_service.app.main:app --host 127.0.0.1 --port 8001` |
| agent-service | 8002 | `python -m uvicorn services.agent_service.app.main:app --host 127.0.0.1 --port 8002` |
| resource-service | 8003 | `python -m uvicorn services.resource_service.app.main:app --host 127.0.0.1 --port 8003` |
| evaluation-service | 8004 | `python -m uvicorn services.evaluation_service.app.main:app --host 127.0.0.1 --port 8004` |
| teacher-service | 8005 | `python -m uvicorn services.teacher_service.app.main:app --host 127.0.0.1 --port 8005` |
| system-service | 8006 | `python -m uvicorn services.system_service.app.main:app --host 127.0.0.1 --port 8006` |
| 前端 (Vite) | 5175 | `cd web-app && npx vite --host=127.0.0.1 --port=5175` |

## 前置检查

### 1. Python 环境

```bash
python --version  # 需要 3.11+
```

依赖安装（首次运行或拉取新代码后）：

```bash
pip install -e .
```

关键包：fastapi, uvicorn, sqlalchemy, psycopg, langchain, langchain-openai

### 2. Node.js 环境

```bash
node --version  # 需要 18+
```

前端依赖（首次运行或拉取新代码后）：

```bash
cd web-app && npm install
```

### 3. PostgreSQL 数据库

**Windows**：检查服务是否运行：

```bash
sc query postgresql
```

STATE 应为 `RUNNING`。如果未运行：

```bash
net start postgresql
```

**创建数据库**（首次设置）：

```bash
python -c "
import psycopg
conn = psycopg.connect(host='localhost', port=5432, user='postgres', password='postgres123', dbname='postgres')
conn.autocommit = True
cur = conn.cursor()
existing = [row[0] for row in cur.execute('SELECT datname FROM pg_database').fetchall()]
if 'learning_system' not in existing:
    cur.execute('CREATE DATABASE learning_system')
    print('Created database: learning_system')
cur.close(); conn.close()
"
```

数据库表会自动由服务启动时的 `ensure_database_schema()` 创建，不需要手动 migration。

### 4. Docker（可选，仅完整功能需要）

如果只需要核心功能（用户、智能体、资源、评估、教师、系统），PostgreSQL 是唯一必需的依赖。

完整功能需要 Docker 运行的服务（Neo4j 知识图谱、MinIO 对象存储、Elasticsearch 搜索、ChromaDB 向量库、Redis 缓存、RabbitMQ 消息队列）。缺少这些时核心功能不受影响，仅知识图谱可视化和部分高级搜索功能降级。

```bash
docker compose up -d postgres redis rabbitmq neo4j minio elasticsearch chroma
```

## 环境变量

### 根目录 `.env`（后端服务读取）

关键配置项：

```env
# 数据库
DATABASE_URL=postgresql+psycopg://postgres:postgres123@localhost:5432/learning_system

# JWT
JWT_SECRET_KEY=change-me

# LLM API Key（必须配置真实 key，否则 AI 功能走本地模板）
OPENAI_API_KEY=sk-your-key-here
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
LLM_REQUEST_TIMEOUT_SECONDS=30

# CORS（必须，否则前端无法访问后端）
CORS_ALLOW_ORIGINS=http://127.0.0.1:5175,http://localhost:5175
```

### 前端 `web-app/.env`（Vite 读取）

```env
VITE_USER_API_BASE_URL=http://127.0.0.1:8001
VITE_AGENT_API_BASE_URL=http://127.0.0.1:8002
VITE_RESOURCE_API_BASE_URL=http://127.0.0.1:8003
VITE_EVALUATION_API_BASE_URL=http://127.0.0.1:8004
VITE_TEACHER_API_BASE_URL=http://127.0.0.1:8005
VITE_SYSTEM_API_BASE_URL=http://127.0.0.1:8006
```

## 启动步骤

### 一键启动

```bash
# Windows PowerShell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1

# Windows CMD
start-dev.bat
```

### 手动逐服务启动（推荐，便于调试）

**1. 启动所有后端（6 个终端窗口或后台进程）：**

```bash
# 项目根目录下，每个服务一个终端
python -m uvicorn services.user_service.app.main:app --host 127.0.0.1 --port 8001
python -m uvicorn services.agent_service.app.main:app --host 127.0.0.1 --port 8002
python -m uvicorn services.resource_service.app.main:app --host 127.0.0.1 --port 8003
python -m uvicorn services.evaluation_service.app.main:app --host 127.0.0.1 --port 8004
python -m uvicorn services.teacher_service.app.main:app --host 127.0.0.1 --port 8005
python -m uvicorn services.system_service.app.main:app --host 127.0.0.1 --port 8006
```

**2. 启动前端：**

```bash
cd web-app && npx vite --host=127.0.0.1 --port=5175
```

## 验证服务

启动后逐个验证健康状态：

```bash
python -c "
import urllib.request,json
for p,n in [(8001,'user'),(8002,'agent'),(8003,'resource'),(8004,'eval'),(8005,'teacher'),(8006,'sys')]:
    try:
        r=urllib.request.urlopen(f'http://127.0.0.1:{p}/health',timeout=3)
        d=json.loads(r.read())
        print(f'  [{p}] {n}: {d.get(\"status\",\"?\")}')
    except Exception as e:
        print(f'  [{p}] {n}: DOWN')
try:
    r=urllib.request.urlopen('http://127.0.0.1:5175',timeout=3)
    print(f'  [5175] frontend: HTTP {r.status}')
except: print(f'  [5175] frontend: DOWN')
"
```

全部 7 个服务显示 OK 即启动成功。访问 `http://127.0.0.1:5175`。

## 常见问题

### 1. "无法连接到后端服务"（红色弹框）

原因：CORS 未配置。确认根目录 `.env` 中有：

```env
CORS_ALLOW_ORIGINS=http://127.0.0.1:5175,http://localhost:5175
```

添加后**重启所有后端服务**（CORS 在服务启动时读取）。

### 2. 注册/登录 API 返回 422

请求缺少 `Content-Type: application/json` 头。前端 axios 自动带，Python 测试需手动加。

### 3. AI 功能无响应 / 返回模板内容

原因一：`OPENAI_API_KEY` 是占位符 `sk-your-key-here`。填入真实 DeepSeek/OpenAI key。

原因二：前端 axios timeout 太短。当前已设为 120 秒（`web-app/src/api/http.ts`），足够 DeepSeek 响应。

原因三：`LLM_REQUEST_TIMEOUT_SECONDS` 太小。建议 >= 30。

### 4. 智能问答一直显示"分析中..."

DeepSeek 响应需要 20-60 秒。刷新前端（Vite HMR 已热更新 timeout 配置），等待即可。

### 5. 切换到浅色主题后部分内容看不清

`[data-theme="minimal"]` 是浅色主题。部分旧版全局 CSS 类（`.hero-panel`、`.workspace-panel`）仍使用硬编码浅色背景，与深色默认主题不一致。这是已知待修复项。

### 6. 后端报 `JWT_SECRET_KEY` 未设置

根目录 `.env` 必须有 `JWT_SECRET_KEY=xxx`。该变量在 `common/config.py` 中标记为 `_get_required`，缺失会导致启动失败。

### 7. PostgreSQL 连接失败

确认：
- PostgreSQL 服务已启动（`sc query postgresql`）
- `.env` 中 `DATABASE_URL` 的 host/port/user/password 正确
- 数据库 `learning_system` 已创建
