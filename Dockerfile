# ============================================================
# AgentCore 多阶段构建
# 队友无需安装 JDK/Maven，仅需 Docker 即可构建运行
# ============================================================

# ---- 构建阶段 ----
FROM maven:3.9-eclipse-temurin-17-alpine AS builder
WORKDIR /build
COPY pom.xml .
# 预下载依赖（利用 Docker 缓存层）
RUN mvn dependency:go-offline -q 2>/dev/null || true
COPY src ./src
RUN mvn package -DskipTests -q

# ---- 运行阶段 ----
FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY --from=builder /build/target/*.jar app.jar
EXPOSE 8048
ENTRYPOINT ["java", "-jar", "app.jar"]
