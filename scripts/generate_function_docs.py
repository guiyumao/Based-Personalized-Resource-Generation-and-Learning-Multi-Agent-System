"""Generate a Markdown feature document from the current codebase."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "docs" / "functionality.md"


@dataclass(frozen=True)
class RouteInfo:
    """Normalized route information extracted from FastAPI files."""

    method: str
    path: str
    function_name: str
    summary: str


def extract_routes(file_path: Path) -> list[RouteInfo]:
    """Extract FastAPI route definitions from a Python file."""

    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    routes: list[RouteInfo] = []

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue

        summary = ast.get_docstring(node) or ""
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name):
                continue
            if decorator.func.value.id != "router":
                continue

            method = decorator.func.attr.upper()
            path = ""
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                path = str(decorator.args[0].value)

            routes.append(
                RouteInfo(
                    method=method,
                    path=path,
                    function_name=node.name,
                    summary=summary,
                )
            )

    return routes


def render_route_table(base_path: str, routes: list[RouteInfo]) -> str:
    """Render a Markdown table for route definitions."""

    lines = [
        "| Method | Path | Handler | Description |",
        "| --- | --- | --- | --- |",
    ]
    for route in routes:
        full_path = f"{base_path}{route.path}"
        lines.append(
            f"| `{route.method}` | `{full_path}` | `{route.function_name}` | {route.summary or '-'} |"
        )
    return "\n".join(lines)


def generate_markdown() -> str:
    """Build the full feature document."""

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_routes = extract_routes(
        PROJECT_ROOT / "services" / "user_service" / "app" / "api" / "routes" / "users.py"
    )
    agent_routes = extract_routes(
        PROJECT_ROOT / "services" / "agent_service" / "app" / "api" / "routes" / "agents.py"
    )
    graph_routes = extract_routes(
        PROJECT_ROOT / "services" / "agent_service" / "app" / "api" / "routes" / "graph.py"
    )
    resource_routes = extract_routes(
        PROJECT_ROOT / "services" / "agent_service" / "app" / "api" / "routes" / "resources.py"
    )
    learning_routes = extract_routes(
        PROJECT_ROOT / "services" / "agent_service" / "app" / "api" / "routes" / "learning.py"
    )
    evaluation_routes = extract_routes(
        PROJECT_ROOT / "services" / "evaluation_service" / "app" / "api" / "routes" / "reports.py"
    )
    teacher_routes = extract_routes(
        PROJECT_ROOT / "services" / "teacher_service" / "app" / "api" / "routes" / "classes.py"
    )

    lines: list[str] = [
        "# 功能说明文档",
        "",
        "> 本文档由 `scripts/generate_function_docs.py` 自动生成。",
        f"> 最近生成时间：`{generated_at}`",
        "",
        "## 1. 项目当前实现概览",
        "",
        "当前仓库已经实现的核心能力如下：",
        "",
        "- 后端已提供 `user-service`、`agent-service`、`evaluation-service`、`teacher-service` 四个可运行的 FastAPI 服务。",
        "- 数据层已提供 SQLAlchemy 模型、Alembic 初始迁移和本地建表脚本。",
        "- 学生端已经支持学习路径、课件阅读、在线答题、即时反馈、错题本、重练题和学习报告。",
        "- 教师端已经支持班级管理、作业布置与批改、学生洞察以及学生详细诊断查看。",
        "- 前端已提供 `Vue 3 + Element Plus` Web 工作台，可直接联调当前后端。",
        "",
        "## 2. 已实现模块",
        "",
        "### 2.1 用户服务 `user-service`",
        "",
        "功能说明：",
        "",
        "- 创建平台用户。",
        "- 提供注册接口，并在注册后直接签发 JWT。",
        "- 提供登录接口。",
        "- 初始化空白学习者画像。",
        "- 查询用户详情、用户画像和当前登录用户信息。",
        "",
        "接口清单：",
        "",
        render_route_table("/users", user_routes),
        "",
        "### 2.2 智能体服务 `agent-service`",
        "",
        "功能说明：",
        "",
        "- 接收前端或上游服务的智能体任务请求。",
        "- 提供协调调度、资源生成、知识图谱查询、学习路径生成、结构化练习生成。",
        "- 提供知识图谱可视化节点和边数据。",
        "",
        "协调调度接口：",
        "",
        render_route_table("/agents", agent_routes),
        "",
        "知识图谱接口：",
        "",
        render_route_table("/graph", graph_routes),
        "",
        "资源生成接口：",
        "",
        render_route_table("/resources", resource_routes),
        "",
        "学习路径与练习接口：",
        "",
        render_route_table("", learning_routes),
        "",
        "### 2.3 效果评估服务 `evaluation-service`",
        "",
        "功能说明：",
        "",
        "- 支持在线答题即时判分与反馈。",
        "- 支持错题本、错题重练题生成。",
        "- 支持阶段报告与综合报告详情。",
        "",
        "接口清单：",
        "",
        render_route_table("/evaluation", evaluation_routes),
        "",
        "### 2.4 教师服务 `teacher-service`",
        "",
        "功能说明：",
        "",
        "- 支持班级列表与班级创建。",
        "- 支持班级进度概览与学生洞察卡片。",
        "- 支持教师查看单个学生的错题本、阶段报告、综合报告详情。",
        "- 支持作业布置与批改结果提交。",
        "",
        "接口清单：",
        "",
        render_route_table("/teacher", teacher_routes),
        "",
        "### 2.5 Web 前端",
        "",
        "核心页面：`LoginView.vue`、`RegisterView.vue`、`StudentView.vue`、`TeacherView.vue`、`AdminView.vue`",
        "",
        "当前页面能力：",
        "",
        "- 登录、注册、JWT 持久化、请求拦截器、路由守卫、角色分流已完成。",
        "- 学生端已从测试面板升级为正式学习工作台，支持路径、课件、练习、反馈、错题本、报告、图谱可视化。",
        "- 教师端已从摘要卡片升级为正式工作台，支持查看班级、学生洞察，并可点开学生详情抽屉查看错题本与报告。",
        "- 管理员端已接入 `system-service` 基础能力。",
        "",
        "默认访问地址：`http://127.0.0.1:5175`",
        "",
        "## 3. 当前未完成但已预留的模块",
        "",
        "- `resource-service` 仍待从骨架推进到真实资源库业务。",
        "- `system-service` 已有基础接口，但管理端复杂业务仍待扩展。",
        "- 移动端 `React Native` 尚未创建。",
        "- 更深层的智能体真实化、真实数据库写入和 LangGraph 端到端闭环仍待继续推进。",
        "",
        "## 4. 文档更新机制",
        "",
        "### 4.1 手动更新",
        "",
        "```bash",
        "python scripts/generate_function_docs.py",
        "```",
        "",
        "### 4.2 实时监听更新",
        "",
        "```bash",
        "python scripts/watch_function_docs.py",
        "```",
        "",
        "## 5. 推荐维护规则",
        "",
        "- 新增接口后，先更新代码，再运行文档生成脚本。",
        "- 新增页面后，在文档中补充页面职责与交互入口。",
        "- 提交代码前，建议先运行一次文档生成脚本，确保文档与实现一致。",
        "",
    ]

    return "\n".join(lines)


def main() -> None:
    """Generate the functionality document."""

    markdown = generate_markdown()
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")
    print(f"Functionality document generated: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
