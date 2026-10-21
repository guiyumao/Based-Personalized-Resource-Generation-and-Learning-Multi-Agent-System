"""Two explicitly budgeted targeted repairs of observed academic explanations."""
import json
import os
from pathlib import Path

from common.db.session import SessionLocal
from common.models.learning import Resource
from common.performance import performance_trace
from common.resource_version import resource_version
from services.agent_service.app.services.resource_generation import ResourceGenerationService

assert os.getenv("MODEL_USAGE_MODE") == "LIVE"
output = Path(os.environ["LIVE_OUTPUT"])
repairs = [
    (3, "case", "纠正原案例错误：原代码始终保留独立指针p指向后继，因此先执行pre->next=s并不必然丢失p。请明确区分：若后续s->next=p且p保留，两个赋值顺序都能正确链接；真正错误是覆盖pre->next后再用s->next=pre->next导致自环。保留完整输入、三个中间步骤、核验和插入头部/空表边界。不要声称任何赋值交换顺序都必然断链。"),
    (4, "principles", "修正开平方的符号依据：sqrt(4a^2)=2|a|，不能由4a^2>0推断2a>0。先严格写出±sqrt(Delta)/(2|a|)，再解释当a<0时正负分支交换，因此解集可统一写成(-b±sqrt(Delta))/(2a)。保留a非零、判别式和完整配方步骤，给出a为负的检验例。"),
]
results = []
for resource_id, chapter, instruction in repairs:
    with SessionLocal() as db:
        original = db.get(Resource, resource_id)
        version = resource_version(original)
        before = json.loads(original.structured_json)
    with performance_trace(service_name="teaching-live-repair", user_id=1, task_type="courseware_revision") as trace:
        trace.set_context(deadline_seconds=180, retry_budget=0)
        response = ResourceGenerationService().regenerate_chapter(1, 1000+resource_id,
            resource_id, version, chapter, revision_instruction=instruction)
    with SessionLocal() as db:
        revised = db.get(Resource, response["id"])
        after = json.loads(revised.structured_json)
        for previous in before["chapters"]:
            if previous["key"] != chapter:
                assert previous["body"] == next(c["body"] for c in after["chapters"] if c["key"] == previous["key"])
        original = db.get(Resource, resource_id)
        original.knowledge_review_required = True
        original.audit_reason = "学科抽查发现解释需要修订；新版本资源 " + str(revised.id)
        db.commit()
        (output/f"courseware-{resource_id}.md").write_text(revised.content, encoding="utf-8")
        (output/f"courseware-{resource_id}.json").write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append({"original": resource_id, "new_resource": revised.id, "chapter": chapter,
                        "other_chapters_unchanged": True, "characters": len(revised.content), "instruction": instruction})
(output/"semantic-repair-result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
