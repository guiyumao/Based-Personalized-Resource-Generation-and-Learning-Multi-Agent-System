"""Backend-enforced call/token reservations before outbound provider requests."""

import os
from contextvars import ContextVar
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from common.db.session import SessionLocal
from common.models.learning import KnowledgeBudgetCounter, KnowledgeBuildTask

current_knowledge_task: ContextVar[int | None] = ContextVar("current_knowledge_task", default=None)


class KnowledgeBudgetExceeded(RuntimeError):
    pass


def reserve_usage(kind: str, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
    if kind not in {"search", "fetch", "model"}:
        raise ValueError("Unknown knowledge budget category")
    now = datetime.utcnow()
    task_id = current_knowledge_task.get()
    scopes = [(f"day:{now:%Y%m%d}", 100), (f"month:{now:%Y%m}", 1000)]
    with SessionLocal() as db:
        cursor, visited = task_id, set()
        while cursor and cursor not in visited and len(visited) < 8:
            visited.add(cursor)
            task = db.get(KnowledgeBuildTask, cursor)
            limit = 2 if kind != "model" else 1
            if task and task.operation_type == "MAINTENANCE_RUN":
                policy = (task.requirements_json or {}).get("policy", {})
                limit = int(policy.get(f"max_{kind}_calls", 0))
            scopes.append((f"task:{cursor}", limit))
            cursor = task.parent_task_id if task else None
    rate = int(os.getenv(f"KNOWLEDGE_{kind.upper()}_COST_MICROS", "0"))
    cost = rate + input_tokens * int(os.getenv("KNOWLEDGE_INPUT_TOKEN_COST_MICROS", "0")) + output_tokens * int(os.getenv("KNOWLEDGE_OUTPUT_TOKEN_COST_MICROS", "0"))
    column = f"{kind}_calls"
    for attempt in range(3):
        with SessionLocal() as db:
            try:
                for scope, default_limit in scopes:
                    if db.get(KnowledgeBudgetCounter, scope) is None:
                        db.add(KnowledgeBudgetCounter(scope_key=scope)); db.flush()
                    period = scope.split(":", 1)[0].upper()
                    limit = min(default_limit, int(os.getenv(f"KNOWLEDGE_{kind.upper()}_{period}_LIMIT", str(default_limit))))
                    row = KnowledgeBudgetCounter
                    result = db.execute(update(row).where(
                        row.scope_key == scope, getattr(row, column) < limit,
                        row.input_tokens + input_tokens <= int(os.getenv(f"KNOWLEDGE_INPUT_{period}_TOKENS", str(default_limit * 20000))),
                        row.output_tokens + output_tokens <= int(os.getenv(f"KNOWLEDGE_OUTPUT_{period}_TOKENS", str(default_limit * 6000))),
                        row.reserved_cost_micros + cost <= int(os.getenv(f"KNOWLEDGE_{period}_COST_MICROS", str(10 ** 12))),
                    ).values({column: getattr(row, column) + 1, "input_tokens": row.input_tokens + input_tokens,
                              "output_tokens": row.output_tokens + output_tokens, "reserved_cost_micros": row.reserved_cost_micros + cost}))
                    if result.rowcount != 1:
                        raise KnowledgeBudgetExceeded(f"{period} {kind} budget exhausted")
                db.commit()
                return
            except IntegrityError:
                db.rollback()
                if attempt == 2:
                    raise


def task_usage(task_id: int) -> dict:
    with SessionLocal() as db:
        row = db.get(KnowledgeBudgetCounter, f"task:{task_id}")
        return {name: getattr(row, name) if row else 0 for name in
                ("search_calls", "fetch_calls", "model_calls", "input_tokens", "output_tokens", "reserved_cost_micros")}
