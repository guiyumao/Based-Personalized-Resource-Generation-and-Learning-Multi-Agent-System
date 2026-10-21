"""Generation prompts must be available regardless of the service working directory."""

from services.agent_service.app.services import (
    exercise_generation,
    prompt_registry,
    resource_generation,
)


def test_learning_prompts_load_outside_repository_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # The shared loader resolves prompts against an absolute PROMPT_DIR, so a
    # working-directory change must not affect it. Clear the in-process cache so
    # this test actually re-reads the files from the new CWD.
    prompt_registry._PROMPT_CACHE.clear()

    courseware = resource_generation._load_prompt_template("resource_gen.md")
    exercises = exercise_generation._load_prompt_template("exercise_gen.md")

    assert "Markdown" in courseware and "LaTeX" in courseware
    assert "JSON" in exercises and "LaTeX" in exercises


def test_actual_courseware_chain_uses_current_depth_prompt(monkeypatch):
    import json

    from langchain_core.runnables import RunnableLambda
    service = resource_generation.ResourceGenerationService()
    captured = []
    monkeypatch.setattr(service.llm_factory, "build_chat_model", lambda **kwargs: RunnableLambda(lambda value: "unused"))
    def invoke(chain, variables, **kwargs):
        captured.extend(chain.first.format_messages(**variables))
        return "当前章正文"
    monkeypatch.setattr(resource_generation, "traced_invoke", invoke)
    service.prompt_template = "stale cached prompt"
    service._invoke_llm({"chapter_instruction": json.dumps({"主题": "冒泡排序", "当前章节": "核心原理"}, ensure_ascii=False)})
    assert "teaching-depth-20261021" in captured[0].content
    assert "循环不变量" in captured[0].content and "空表合法位置插入可以成功" in captured[0].content
    assert "stale cached prompt" not in captured[0].content
    assert "核心原理" in captured[1].content


def test_actual_exercise_chain_uses_depth_and_scope(monkeypatch):
    import json

    from langchain_core.runnables import RunnableLambda

    from common.schemas.agent import ExerciseGenerationRequest
    from services.agent_service.app.services.personalization import LearnerPersonalizationSnapshot
    service = exercise_generation.ExerciseGenerationService()
    captured = []
    monkeypatch.setattr(service.knowledge_base, "get_article", lambda *args: None)
    monkeypatch.setattr(service, "_build_retrieval_text", lambda *args: "")
    monkeypatch.setattr(service.llm_factory, "build_chat_model", lambda **kwargs: RunnableLambda(lambda value: "unused"))
    def invoke(chain, variables, **kwargs):
        captured.extend(chain.first.format_messages(**variables))
        return json.dumps({"summary": "测试", "exercises": [{"exercise_id": 1, "knowledge_point": "链表", "question_type": "short_answer", "difficulty": "foundation", "prompt": "在空链表的第1个合法位置插入节点，画出头指针变化。", "options": [], "answer": "头指针指向新节点，新节点next为空。", "analysis": "先检查合法位置，再创建节点并连接头指针，核验只有一个可达节点。"}]}, ensure_ascii=False)
    monkeypatch.setattr(exercise_generation, "traced_invoke", invoke)
    service.prompt_template = "stale cached prompt"
    request = ExerciseGenerationRequest(user_id=1, knowledge_point="链表", knowledge_point_id="459", subject="数据结构", chapter="线性表", exercise_count=3, question_type_counts={"short_answer": 3})
    snapshot = LearnerPersonalizationSnapshot({}, None, [], 0, None)
    result = service._try_generate_with_llm(request, snapshot, {}, set())
    assert result and captured
    assert "exercise-depth-20261021" in captured[0].content
    assert "不强制个性化" in captured[0].content and "先独立求解/验算" in captured[0].content
    assert "数据结构" in captured[1].content and "线性表" in captured[1].content and "459" in captured[1].content
