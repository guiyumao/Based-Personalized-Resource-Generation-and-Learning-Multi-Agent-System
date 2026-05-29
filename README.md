# Based-Personalized-Resource-Generation-and-Learning-Multi-Agent-System

# 基于大模型的个性化资源生成与学习多智能体系统

当前后端已开始切换为 `Java 17 + Spring Boot 3`。

## 当前状态

- 前端仍为 `Vue 3 + Element Plus`
- 新增 `Java Spring Boot` monorepo 骨架
- 已落地可运行骨架：
  - `java-services/common`
  - `java-services/user-service`
  - `java-services/agent-service`
- 现有 Python 服务代码暂未删除，作为旧版本保留

## 新后端目录

```text
java-services/
  common/
  user-service/
  agent-service/
pom.xml
```

## 已迁移的核心接口

### user-service

- `GET /health`
- `POST /users`
- `POST /users/register`
- `POST /users/login`
- `GET /users/me`
- `GET /users/{userId}`
- `GET /users/{userId}/profile`
- `GET /users/{userId}/profile/dashboard`
- `POST /users/{userId}/token`

### agent-service

- `GET /health`
- `POST /agents/coordinate`
- `POST /resources/generate`
- `POST /paths/generate`
- `POST /exercises/generate`
- `POST /graph/dependencies`
- `POST /graph/visualization`
- `GET /graph/related-resources/{knowledgePoint}`

## 环境要求

- JDK 17
- Maven 3.9+
- Node.js 20+

## 启动方式

### 1. 启动 user-service

```bash
mvn -pl java-services/user-service spring-boot:run
```

默认端口：`8001`

### 2. 启动 agent-service

```bash
mvn -pl java-services/agent-service spring-boot:run
```

默认端口：`8002`

### 3. 启动前端

```bash
cd web-app
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5175`

## 说明

- 当前机器上未检测到 `mvn`，所以还没有完成本地 Java 编译验证。
- 如果你安装了 Maven，优先先跑：

```bash
mvn -DskipTests package
```

- 现阶段是“新增 Java 版后端骨架”，不是“所有 Python 服务已经全部迁完”。
- 下一步建议继续迁移：
  - `evaluation-service`
  - `teacher-service`
  - `system-service`
  - PostgreSQL / JPA 持久化
  - Spring Security + JWT 过滤器
  - RabbitMQ / Neo4j / Redis 集成

## 前端联调说明

前端当前仍然访问：

- `http://127.0.0.1:8001`
- `http://127.0.0.1:8002`

所以只要先把新的 `user-service` 和 `agent-service` 跑起来，登录、课件、自测、路径、图谱这些核心页面就可以继续联调。
