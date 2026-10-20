"""Durable per-provider-call accounting via the model's own callbacks."""
import os
import re
from datetime import datetime

from langchain_core.callbacks import BaseCallbackHandler
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from common.db.session import SessionLocal
from common.models.learning import KnowledgeBudgetCounter
from common.models.operations import ModelCall
from common.performance import get_current_trace


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def usage_fields(response):
    """Keep unknown distinct from zero; cache tokens are a subset of input."""
    usage = getattr(response, "usage_metadata", None) or {}
    meta = getattr(response, "response_metadata", None) or {}
    output = getattr(response, "llm_output", None) or {}
    if isinstance(response, dict):
        usage = response.get("usage") or response.get("usage_metadata") or {}
        meta = response
    token_usage = meta.get("token_usage") or output.get("token_usage") or output.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    if not isinstance(token_usage, dict):
        token_usage = {}
    incoming = _count(usage.get("input_tokens", usage.get("prompt_tokens", token_usage.get("prompt_tokens"))))
    outgoing = _count(usage.get("output_tokens", usage.get("completion_tokens", token_usage.get("completion_tokens"))))
    details = usage.get("input_token_details") or usage.get("prompt_tokens_details") or token_usage.get("prompt_tokens_details") or {}
    cached = _count(details.get("cache_read", details.get("cached_tokens")))
    if incoming is None and outgoing is None and getattr(response, "generations", None):
        # One chat call has one aggregated message; do not sum n completions'
        # identical prompt usage or count both llm_output and message metadata.
        message = getattr(response.generations[0][0], "message", None)
        if message is not None:
            return usage_fields(message)
    return {"input_tokens": incoming, "output_tokens": outgoing, "cached_input_tokens": cached,
            "usage_status": "KNOWN" if incoming is not None and outgoing is not None else "PARTIAL" if incoming is not None or outgoing is not None else "UNKNOWN",
            "response_model": str(meta.get("model_name") or output.get("model_name") or meta.get("model") or "")[:160] or None}


def call_context():
    trace = get_current_trace()
    context = {"feature": trace.task_type[:160] if trace else "unattributed", "user_id": int(trace.user_id) if trace and str(trace.user_id).isdigit() else None,
               "request_id": trace.request_id[:80] if trace else None}
    # Lazy imports avoid cycles at model-client construction time.
    from common.models.learning import AssistantTask, KnowledgeBuildTask
    from services.agent_service.app.services.assistant_execution import current_execution
    from services.agent_service.app.services.knowledge_budget import current_knowledge_task
    guard, knowledge_id = current_execution.get(), current_knowledge_task.get()
    if guard or knowledge_id:
        kind, task_id = ("assistant", guard[0]) if guard else ("knowledge", knowledge_id)
        with SessionLocal() as db:
            task = db.get(AssistantTask if guard else KnowledgeBuildTask, task_id)
            context.update(task_kind=kind, task_id=task_id, attempt=task.execution_attempt if task else None,
                user_id=(task.user_id if guard else task.actor_user_id) if task else None,
                feature=f"{kind}:{task.task_type if guard else task.operation_type}" if task else f"{kind}:unknown")
    return context


class ModelCallBudgetExceeded(RuntimeError):
    pass


def begin_call(call_id, provider, model):
    context = call_context()
    mode = os.getenv("MODEL_USAGE_MODE") or ("TEST" if os.getenv("NO_COST_TEST") == "1" else "LIVE")
    if mode not in {"LIVE", "TEST"}:
        raise ValueError("Invalid model usage mode")
    now = datetime.utcnow()
    for attempt in range(3):
        with SessionLocal() as db:
            try:
                if db.get(ModelCall, call_id):
                    return
                scopes = [(f"model-day:{mode}:{now:%Y%m%d}", os.getenv("AI_PROVIDER_DAY_CALL_LIMIT"))]
                user_limit = os.getenv("AI_PROVIDER_USER_DAY_CALL_LIMIT")
                if user_limit is not None:
                    if context["user_id"] is None:
                        raise ModelCallBudgetExceeded("User attribution required by per-user budget")
                    scopes.append((f"model-user:{mode}:{now:%Y%m%d}:{context['user_id']}", user_limit))
                for scope, limit in scopes:
                    if db.get(KnowledgeBudgetCounter, scope) is None:
                        db.add(KnowledgeBudgetCounter(scope_key=scope))
                        db.flush()
                    query = update(KnowledgeBudgetCounter).where(KnowledgeBudgetCounter.scope_key == scope)
                    if limit is not None:
                        query = query.where(KnowledgeBudgetCounter.model_calls < max(0, int(limit)))
                    reserve_output = 0
                    if os.getenv("AI_PROVIDER_DAY_OUTPUT_RESERVATION") is not None:
                        reserve_output = int(os.environ["AI_PROVIDER_MAX_OUTPUT_TOKENS"])
                        if reserve_output < 1:
                            raise ModelCallBudgetExceeded("Positive output reservation required")
                        query = query.where(KnowledgeBudgetCounter.output_tokens+reserve_output <= int(os.environ["AI_PROVIDER_DAY_OUTPUT_RESERVATION"]))
                    if db.execute(query.values(model_calls=KnowledgeBudgetCounter.model_calls+1,
                        output_tokens=KnowledgeBudgetCounter.output_tokens+reserve_output)).rowcount != 1:
                        raise ModelCallBudgetExceeded("Provider call budget exhausted")
                db.add(ModelCall(id=call_id, provider=provider[:40], model=model[:160], mode=mode,
                    status="STARTED", usage_status="UNKNOWN", started_at=now, **context))
                db.commit()  # Both durable reservation and ledger precede HTTP.
                return
            except IntegrityError:
                db.rollback()
                if attempt == 2:
                    raise


def finish_call(call_id, *, response=None, error=None):
    now = datetime.utcnow()
    fields = usage_fields(response) if response is not None else {"usage_status": "UNKNOWN"}
    with SessionLocal() as db:
        row = db.get(ModelCall, call_id)
        if not row or row.status != "STARTED":
            return
        fields.update(status="FAILED" if error else "SUCCEEDED", finished_at=now,
            elapsed_ms=max(0, (now - row.started_at).total_seconds()*1000),
            error_code=re.sub(r"[^A-Za-z0-9_]", "", type(error).__name__)[:80] if error else None)
        db.execute(update(ModelCall).where(ModelCall.id == call_id, ModelCall.status == "STARTED").values(**fields))
        db.commit()


class UsageCallback(BaseCallbackHandler):
    """Per-call UUID makes nested chains, retries and cached clients safe."""
    raise_error = True
    run_inline = True

    def __init__(self, provider, model):
        self.provider, self.model = provider, model

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        begin_call(str(run_id), self.provider, self.model)

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        begin_call(str(run_id), self.provider, self.model)

    def on_llm_end(self, response, *, run_id, **kwargs):
        finish_call(str(run_id), response=response)

    def on_llm_error(self, error, *, run_id, **kwargs):
        finish_call(str(run_id), error=error)
