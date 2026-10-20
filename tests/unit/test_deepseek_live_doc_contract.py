"""Keep the DeepSeek acceptance docs aligned with the actual source.

These are documentation-contract tests, not model tests. They fail when a known
wrong configuration name, a forced-non-JSON test recipe, or an over-strong
cancellation/billing promise is copied back into the runbook.
"""

from __future__ import annotations

from pathlib import Path

PLAN = Path("docs/testing/deepseek-live-test-plan.md")
PROMPT = Path("docs/testing/deepseek-live-test-prompt.md")
AUDIT = Path("docs/testing/deepseek-live-source-audit.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_docs_do_not_reference_nonexistent_timeout_or_retry_names() -> None:
    runbook = _text(PLAN) + _text(PROMPT)
    assert "LLM_TOTAL_TIMEOUT_SECONDS" not in runbook
    assert "LLM_MAX_TOTAL_RETRIES" not in runbook
    assert "MAX_TOTAL_RETRIES" in runbook
    # The audit may quote the wrong names only to say they do not exist.
    assert "不存在" in _text(AUDIT)


def test_docs_state_the_real_timeout_clamp() -> None:
    combined = _text(PLAN) + _text(PROMPT) + _text(AUDIT)
    assert "max(3" in combined or "钳到 3" in combined


def test_docs_do_not_require_capturing_cancel_requested() -> None:
    assert "不强制捕获" in _text(PLAN) or "不强制捕获" in _text(PROMPT)
    assert "必须观测到 HTTP 200 与 CANCEL_REQUESTED" not in _text(PROMPT)
    assert "远端停止后续调用" not in _text(PLAN)


def test_docs_do_not_use_forced_prose_as_failure_recipe() -> None:
    plan = _text(PLAN)
    prompt = _text(PROMPT)
    assert "强制散文" not in plan
    assert "禁止用提示词逼模型输出错误" in plan or "禁止" in prompt
    assert "本地 HTTP 桩" in plan
    assert "test_deepseek_failure_semantics" in plan


def test_docs_separate_suggestion_budget_from_authorization() -> None:
    plan = _text(PLAN)
    assert "建议预算不是授权" in plan
    assert "不是费用授权" in plan


def test_docs_flag_the_exercise_fallback_and_audit_unavailable() -> None:
    plan = _text(PLAN)
    assert "deterministic_fallback" in plan
    assert "unavailable" in plan
    assert "不是审计通过" in plan
    assert "不是审核通过" in plan or "审核未执行" in plan


def test_docs_flag_search_fetch_gateway_and_fake_ip_blocker() -> None:
    plan = _text(PLAN)
    assert "DEEPSEEK_SEARCH_BASE" in plan
    assert "fake-IP" in plan or "198.18" in plan
    assert "经网关" in plan


def test_docs_require_a_second_paid_calls_gate() -> None:
    prompt = _text(PROMPT)
    plan = _text(PLAN)
    assert "DEEPSEEK_LIVE_PAID_ACK" in prompt
    assert "DEEPSEEK_LIVE_PAID_ACK" in plan
    assert "会删除变量" in prompt or "会删除变量" in plan
