"""Tag analysis agent — auto-tag crawled educational content using LLM + keyword fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from common.config import Settings, get_settings
from services.agent_service.app.services.llm_factory import LLMFactory

TAG_SYSTEM_PROMPT = """你是教育资源标签分析器。分析给定内容，返回 3-6 个标签。
标签应涵盖：编程语言/学科名、具体主题、难度级别（基础/进阶）、内容类型（概念讲解/代码示例/练习题）。

只返回一个 JSON 数组，例如：["Python","循环结构","while","基础","概念讲解"]
不要输出任何其他文字。"""

# ── Keyword → tag fallback mapping ──
KEYWORD_TAG_MAP: dict[str, list[str]] = {
    "python": ["Python"],
    "java": ["Java"],
    "c语言": ["C语言"],
    "c++": ["C++"],
    "cpp": ["C++"],
    "循环": ["循环结构"],
    "while": ["while"],
    "for": ["for"],
    "条件": ["条件判断"],
    "if": ["if-else"],
    "switch": ["switch"],
    "数据类型": ["数据类型"],
    "变量": ["变量"],
    "数组": ["数组"],
    "链表": ["链表"],
    "栈": ["栈"],
    "队列": ["队列"],
    "面向对象": ["OOP"],
    "继承": ["OOP", "继承"],
    "多态": ["OOP", "多态"],
    "类": ["OOP", "类"],
    "指针": ["指针"],
    "函数": ["函数"],
    "递归": ["递归"],
    "排序": ["排序"],
    "冒泡": ["冒泡排序"],
    "快速排序": ["快速排序"],
    "归并": ["归并排序"],
    "分治": ["分治"],
    "贪心": ["贪心"],
    "回溯": ["回溯"],
    "微积分": ["数学", "微积分"],
    "导数": ["数学", "导数"],
    "积分": ["数学", "积分"],
    "极限": ["数学", "极限"],
    "线性代数": ["数学", "线性代数"],
    "概率": ["数学", "概率论"],
    "mysql": ["数据库", "MySQL", "SQL"],
    "sql": ["数据库", "SQL"],
    "数据库": ["数据库"],
    "输入": ["IO", "输入输出"],
    "输出": ["IO", "输入输出"],
    "算法": ["算法"],
    "数据结构": ["数据结构"],
    "操作系统": ["操作系统"],
    "网络": ["计算机网络"],
    "软件工程": ["软件工程"],
    "基础": ["基础"],
    "进阶": ["进阶"],
    "入门": ["基础"],
}

DIFFICULTY_KEYWORDS = {
    "基础": ["基础", "入门", "初学", "简单", "概述", "简介", "tutorial"],
    "进阶": ["进阶", "高级", "深入", "原理", "源码", "底层", "优化"],
}


class TagAnalysisService:
    """Analyze educational content and generate structured tags via LLM."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def analyze_tags(self, content: str, title: str = "", subject: str = "") -> list[str]:
        """Generate 3-6 tags for the given content.

        Returns a list like ["Python","循环结构","while","基础","概念讲解"].
        Falls back to keyword matching if LLM is unavailable.
        """
        # ── Try LLM first ──
        try:
            llm_tags = self._analyze_with_llm(content, title)
            if llm_tags:
                return list(dict.fromkeys(llm_tags))  # dedupe preserving order
        except Exception:
            pass

        # ── Keyword fallback ──
        return self._analyze_with_keywords(content, title, subject)

    def _analyze_with_llm(self, content: str, title: str) -> list[str] | None:
        """Use LLM to generate tags."""
        excerpt = content[:2000]
        prompt = f"标题：{title}\n\n内容摘录：\n{excerpt}"
        try:
            llm = LLMFactory(self.settings).build_chat_model(temperature=0.1)
            result = llm.invoke([
                {"role": "system", "content": TAG_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            raw = self._coerce_llm_text(result.content)
            parsed = self._extract_json_array(raw)
            if isinstance(parsed, list) and len(parsed) >= 2:
                return [str(t).strip() for t in parsed if str(t).strip()]
        except Exception:
            pass
        return None

    def _analyze_with_keywords(self, content: str, title: str = "", subject: str = "") -> list[str]:
        """Keyword-based tag generation (fallback)."""
        tags: list[str] = []
        text = (title + " " + content[:3000]).lower()

        for keyword, mapped_tags in KEYWORD_TAG_MAP.items():
            if keyword in text:
                for tag in mapped_tags:
                    if tag not in tags:
                        tags.append(tag)

        # Add subject as tag if not present
        if subject and subject not in tags:
            tags.insert(0, subject)

        # Add difficulty
        for level, patterns in DIFFICULTY_KEYWORDS.items():
            if any(p in text for p in patterns):
                if level not in tags:
                    tags.append(level)

        # Add content type
        if any(kw in text for kw in ("示例", "代码", "code", "```")):
            tags.append("代码示例")
        if any(kw in text for kw in ("定义", "概念", "是什么", "介绍")):
            tags.append("概念讲解")

        return tags

    def _coerce_llm_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if hasattr(content, "content"):
            return str(content.content)
        return str(content)

    def _extract_json_array(self, raw: str) -> list[str] | None:
        """Extract a JSON array from LLM output."""
        cleaned = raw.strip()
        # Strip markdown fences
        for prefix in ("```json", "```"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        # Find [...] in the text
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
        return None
