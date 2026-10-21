"""Read-only dashboard aggregation over existing ledgers. No inference of billing."""
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import func

from common.models.learning import AssistantTask, KnowledgeBudgetCounter, KnowledgeBuildTask
from common.models.operations import ModelCall

TASK_STATES = {
    "SUCCEEDED": "success", "COMPLETED": "success", "FAILED": "failed",
    "RUNNING": "running", "CANCEL_REQUESTED": "running", "PENDING": "waiting",
    "QUEUED": "waiting", "CANCELLED": "cancelled", "CANCELED": "cancelled",
}


def calendar_range(start: date | None, end: date | None, days: int = 7):
    if (start is None) != (end is None):
        raise HTTPException(422, "Both start and end are required")
    end = end or datetime.utcnow().date()
    start = start or end - timedelta(days=days - 1)
    if end < start or (end - start).days >= 90 or end > datetime.utcnow().date():
        raise HTTPException(422, "Choose 1 to 90 UTC calendar days, ending no later than today")
    return datetime.combine(start, time.min), datetime.combine(end + timedelta(days=1), time.min)


def task_groups(db, start, end):
    result = []
    for kind, model, operation in (("assistant", AssistantTask, AssistantTask.task_type),
                                    ("knowledge", KnowledgeBuildTask, KnowledgeBuildTask.operation_type)):
        # Count task identities once. Attempts and child agent stages are never joined here.
        for task_type, status, count in db.query(operation, model.status, func.count(model.id)).filter(
                model.created_at >= start, model.created_at < end).group_by(operation, model.status).all():
            result.append({"kind": kind, "operation": task_type, "status": status,
                           "state": TASK_STATES.get(status, "other"), "count": count})
    return result


def completion(groups):
    success = sum(row["count"] for row in groups if row["state"] == "success")
    failed = sum(row["count"] for row in groups if row["state"] == "failed")
    return {"success": success, "failed": failed, "denominator": success + failed,
            "rate": success / (success + failed) * 100 if success + failed else None}


def statistics(db, start, end, mode):
    from services.agent_service.app.api.routes.model_usage import usage_summary
    now = datetime.utcnow()
    query = db.query(ModelCall).filter(ModelCall.mode == mode, ModelCall.started_at >= start,
                                       ModelCall.started_at < end)
    dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((end-start).days)]
    day_rows = query.with_entities(func.date(ModelCall.started_at), ModelCall.provider, ModelCall.model,
        func.count(ModelCall.id), func.sum(ModelCall.input_tokens), func.sum(ModelCall.output_tokens)).group_by(
            func.date(ModelCall.started_at), ModelCall.provider, ModelCall.model).all()
    # The existing DeepSeek tool gateway uses this provider tag, not a model-name heuristic.
    models = sorted({row[2] for row in day_rows if row[1] != 'deepseek-tools'})
    tool_names = sorted({row[2] for row in day_rows if row[1] == 'deepseek-tools'})
    lookup = {}
    for day, provider, model, count, incoming, outgoing in day_rows:
        key = (str(day), 'tools' if provider == 'deepseek-tools' else 'models', model)
        previous = lookup.get(key, (0, 0, 0))
        lookup[key] = tuple(a+b for a, b in zip(previous, (count, incoming or 0, outgoing or 0), strict=True))
    def series(names, category):
        return [{'name': m, 'data': [lookup.get((d, category, m), (0, 0, 0))[0] for d in dates]} for m in names]
    model_series, tool_series = series(models, 'models'), series(tool_names, 'tools')
    daily = [{"date": day,
              "calls": sum(value[0] for (d, _, _), value in lookup.items() if d == day),
              "input": sum(value[1] for (d, category, _), value in lookup.items() if d == day and category == 'models'),
              "output": sum(value[2] for (d, category, _), value in lookup.items() if d == day and category == 'models')}
             for day in dates]
    distribution = [{'name': row['name'], 'value': sum(row['data'])} for row in model_series]
    tool_distribution = [{'name': row['name'], 'value': sum(row['data'])} for row in tool_series]
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_counts = db.query(ModelCall.provider, func.count(ModelCall.id)).filter(ModelCall.mode == mode,
        ModelCall.started_at >= today, ModelCall.started_at < now).group_by(ModelCall.provider).all()
    today_calls = sum(count for _, count in today_counts)
    yesterday_calls = db.query(ModelCall).filter(ModelCall.mode == mode,
        ModelCall.started_at >= today-timedelta(days=1), ModelCall.started_at < now-timedelta(days=1)).count()
    groups = task_groups(db, start, end)
    by_day = {day: [] for day in dates}
    for model in (AssistantTask, KnowledgeBuildTask):
        for day, status, count in db.query(func.date(model.created_at), model.status, func.count(model.id)).filter(
                model.created_at >= start, model.created_at < end).group_by(func.date(model.created_at), model.status).all():
            by_day[str(day)].append({'state': TASK_STATES.get(status, 'other'), 'count': count})
    current = completion(groups)
    previous = completion(task_groups(db, start - (end-start), start))
    current["change_points"] = (current["rate"]-previous["rate"]
                                if current["rate"] is not None and previous["rate"] is not None else None)
    current["previous"] = previous
    # These are reservations, NOT completed tool requests; deliberately kept separate.
    scopes = [f"day:{day.replace('-', '')}" for day in dates]
    tools = {row.scope_key: row for row in db.query(KnowledgeBudgetCounter).filter(
        KnowledgeBudgetCounter.scope_key.in_(scopes)).all()}
    return {"timezone": "UTC", "start": start.date(), "end": (end-timedelta(days=1)).date(),
        "as_of": now, "mode": mode, "summary": usage_summary(query), "daily": daily,
        "model_summary": usage_summary(query.filter(ModelCall.provider != 'deepseek-tools')),
        "tool_summary": usage_summary(query.filter(ModelCall.provider == 'deepseek-tools')),
        "model_series": model_series, "tool_series": tool_series, "tool_distribution": tool_distribution,
        "distribution": distribution, "today": {"calls": today_calls,
            "models": sum(count for provider, count in today_counts if provider != 'deepseek-tools'),
            "tools": sum(count for provider, count in today_counts if provider == 'deepseek-tools'),
            "yesterday_same_time": yesterday_calls,
            "change_percent": (today_calls-yesterday_calls)/yesterday_calls*100 if yesterday_calls else None},
        "tasks": groups, "completion": current,
        "task_daily": [completion(by_day[d]) for d in dates],
        "tool_reservations": [{"date": d,
            "search": tools[f"day:{d.replace('-', '')}"].search_calls if f"day:{d.replace('-', '')}" in tools else 0,
            "fetch": tools[f"day:{d.replace('-', '')}"].fetch_calls if f"day:{d.replace('-', '')}" in tools else 0} for d in dates],
        "tool_basis": "DeepSeek tool gateway ledger (provider=deepseek-tools); attempts include failed calls. Reservations are separate and cross-environment.",
        "budget_history_basis": "Only current limit is known; historical limits and monetary costs are not inferred"}
