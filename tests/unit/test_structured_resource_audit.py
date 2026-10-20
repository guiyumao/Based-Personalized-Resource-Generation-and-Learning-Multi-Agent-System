"""Audit contract for the structured (non-prose) resource types.

Regression guard for a defect that stub-only testing hid: ``audit_courseware``
demands the courseware section list ("学习目标" / "知识讲解" / "示例" / "小结" /
"自测"). A mind map, a code case and a video script legitimately have none of
those sections, so reusing the courseware rule set rejected **every** real
generation attempt — while the stubbed unit tests kept passing.

These tests are deterministic and never call a model: the topical-relevance rule
matches first for every fixture below.
"""

from __future__ import annotations

import pytest

from services.agent_service.app.services.audit_service import (
    STRUCTURED_RESOURCE_TYPES,
    AuditService,
)

MIND_MAP_MARKDOWN = """# 二分查找思维导图

- **二分查找**：在有序数组中折半定位目标
  - **有序数组**：二分查找的前提
  - **中间位置**：每次比较的中点
- **边界处理**：left/right 的开闭区间必须写清楚
"""

CODE_CASE_MARKDOWN = """# 二分查找代码实操

**语言**：python

**目标**：手写一个能在有序数组中定位目标的二分查找

## 示例代码

```python
def binary_search(items, target):
    left, right = 0, len(items) - 1
    while left <= right:
        mid = (left + right) // 2
        if items[mid] == target:
            return mid
        if items[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
```

## 运行步骤

1. 保存为 binary_search.py
2. 运行 python binary_search.py

> 系统未执行这段代码，请自行运行核对预期输出。
"""

VIDEO_SCRIPT_MARKDOWN = """# 二分查找讲解脚本

> 这是**拍摄脚本**，不是视频文件。

**预计总时长**：约 150 秒

## 第 1 章 · 导入（约 1分0秒）

**旁白**

同学们好，今天讲二分查找。它每次把搜索区间折半，因此复杂度是对数级。

## 第 2 章 · 演示（约 1分30秒）

**旁白**

我们来看 left、right、mid 三个变量如何在有序数组上收缩。
"""


def test_courseware_audit_still_rejects_a_mind_map() -> None:
    """Documents the original defect: the courseware rule set cannot judge a map."""

    decision = AuditService().audit_courseware("二分查找", MIND_MAP_MARKDOWN, "二分查找思维导图")
    assert decision.status == "rejected"
    assert decision.reason == "courseware required sections are incomplete"


@pytest.mark.parametrize(
    ("resource_type", "content", "title"),
    [
        ("mind_map", MIND_MAP_MARKDOWN, "二分查找思维导图"),
        ("code_case", CODE_CASE_MARKDOWN, "二分查找代码实操"),
        ("video_script", VIDEO_SCRIPT_MARKDOWN, "二分查找讲解脚本"),
    ],
)
def test_structured_audit_accepts_the_real_rendering(resource_type, content, title) -> None:
    decision = AuditService().audit_structured_resource("二分查找", resource_type, content, title)

    assert decision.status == "passed", decision.reason
    assert decision.method == "rule"
    assert decision.reason == "rule_audit_passed"


def test_structured_audit_rejects_short_content() -> None:
    decision = AuditService().audit_structured_resource("二分查找", "mind_map", "# 二分查找\n", "标题")

    assert decision.status == "rejected"
    assert decision.reason == "structured content is too short"


def test_structured_audit_rejects_generation_failure_text() -> None:
    content = "无法生成该资源的思维导图。" + ("二分查找的节点说明。" * 12)

    decision = AuditService().audit_structured_resource("二分查找", "mind_map", content, "标题")

    assert decision.status == "rejected"
    assert decision.reason == "structured content contains generation failure text"


def test_structured_audit_refuses_unknown_kinds() -> None:
    decision = AuditService().audit_structured_resource(
        "二分查找", "courseware", MIND_MAP_MARKDOWN, "标题"
    )

    assert decision.status == "rejected"
    assert "not a structured kind" in decision.reason


def test_structured_resource_type_set_matches_the_generators() -> None:
    assert STRUCTURED_RESOURCE_TYPES == {"mind_map", "code_case", "video_script"}


def test_structured_audit_falls_back_to_the_semantic_auditor(monkeypatch) -> None:
    """Off-topic content must reach the LLM reviewer, not pass on a technicality."""

    from services.agent_service.app.services.audit_service import AuditDecision

    service = AuditService()
    calls: list[str] = []

    def fake_auditor(knowledge_point: str, summary: str) -> AuditDecision:
        calls.append(knowledge_point)
        return AuditDecision(True, "unavailable", "audit_unavailable", "llm")

    monkeypatch.setattr(service, "_call_auditor", fake_auditor)

    off_topic = "# 红楼梦人物关系\n\n- **贾宝玉**\n- **林黛玉**\n" + ("无关内容。" * 20)
    decision = service.audit_structured_resource("二分查找", "mind_map", off_topic, "红楼梦")

    assert calls == ["二分查找"]
    assert decision.status == "unavailable"
    assert decision.passed is True
