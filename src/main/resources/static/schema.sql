-- ============================================================
-- AgentCore 完整数据库结构
-- 运行前确保 PostgreSQL 已安装 pgvector 扩展:
--   CREATE EXTENSION IF NOT EXISTS vector;
-- ============================================================

-- 用户画像表
CREATE TABLE IF NOT EXISTS user_profile (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    knowledge_base VARCHAR(255),
    cognitive_style VARCHAR(255),
    error_preference TEXT,
    learning_speed VARCHAR(255),
    interest_direction VARCHAR(255),
    goal_orientation VARCHAR(255),
    profile_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 对话历史表
CREATE TABLE IF NOT EXISTS profile_conversation (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    role VARCHAR(10),
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- RAG 知识库表（含向量存储）
-- embedding 存储为 JSON 数组字符串，如 "[0.1,0.2,...]"
-- 向量相似度计算在 Java 层完成，无需 pgvector 扩展
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_base (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    content_type VARCHAR(50) DEFAULT 'text',
    knowledge_point VARCHAR(255),
    tags TEXT,
    source VARCHAR(500),
    embedding TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 学习资源表（增强版）
-- ============================================================
CREATE TABLE IF NOT EXISTS resource (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    resource_type VARCHAR(30) NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    format VARCHAR(20) DEFAULT 'markdown',
    knowledge_point VARCHAR(255),
    difficulty_level VARCHAR(20) DEFAULT 'medium',
    estimated_time_minutes INT DEFAULT 30,
    tags TEXT,
    metadata_json JSONB,
    status VARCHAR(20) DEFAULT 'ready',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 学习记录表（增强版）
-- ============================================================
CREATE TABLE IF NOT EXISTS learning_record (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    resource_id BIGINT NOT NULL,
    action VARCHAR(30) NOT NULL,
    score DECIMAL(5,2),
    progress_percent INT DEFAULT 0,
    time_spent_seconds INT DEFAULT 0,
    metadata_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 学习路径表
-- ============================================================
CREATE TABLE IF NOT EXISTS learning_path (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    subject VARCHAR(255),
    status VARCHAR(20) DEFAULT 'active',
    total_nodes INT DEFAULT 0,
    completed_nodes INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 学习路径节点表（邻接表 + sort_order）
-- ============================================================
CREATE TABLE IF NOT EXISTS learning_path_node (
    id BIGSERIAL PRIMARY KEY,
    learning_path_id BIGINT NOT NULL REFERENCES learning_path(id),
    parent_node_id BIGINT,
    knowledge_id VARCHAR(100) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    resource_type_hint VARCHAR(30),
    sort_order INT NOT NULL DEFAULT 0,
    estimated_time_minutes INT DEFAULT 30,
    status VARCHAR(20) DEFAULT 'pending',
    resource_ids TEXT,
    metadata_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 用户进度表（分析追踪）
-- ============================================================
CREATE TABLE IF NOT EXISTS user_progress (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    knowledge_point VARCHAR(255),
    mastery_score DECIMAL(5,2) DEFAULT 0,
    total_time_minutes INT DEFAULT 0,
    exercise_count INT DEFAULT 0,
    correct_count INT DEFAULT 0,
    last_activity_at TIMESTAMP,
    metadata_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, knowledge_point)
);

-- ============================================================
-- 资源生成记录表（协调智能体追踪）
-- ============================================================
CREATE TABLE IF NOT EXISTS resource_generation_record (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    resource_id BIGINT,
    request_text TEXT,
    resource_type VARCHAR(30),
    knowledge_point VARCHAR(255),
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    tokens_used INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
