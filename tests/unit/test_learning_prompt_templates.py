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
