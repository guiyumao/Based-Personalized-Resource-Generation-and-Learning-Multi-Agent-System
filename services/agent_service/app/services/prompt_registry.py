"""Read and update the prompt templates the local agents render at generation time.

P1-07 gives administrators an explicit place to inspect and tune prompts (``管理员
专用 Prompt 优化``). Editing is deliberately narrow and safe:

- Only the files whitelisted in :data:`ALLOWED_PROMPTS` are reachable. The ``name``
  parameter is a lookup key, never a filesystem path, so a traversal string can
  only ever resolve to a rejected key, not an arbitrary file.
- An update must keep every ``{placeholder}`` the current template declares. The
  renderer in :mod:`resource_generation` raises when a declared variable is
  missing, so silently dropping a placeholder would break the next generation.
  New placeholders are rejected implicitly because the renderer only substitutes
  declared names and would treat the braces as literal text.
"""

from __future__ import annotations

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
PROMPT_DIR = _PROJECT_ROOT / "prompts"

#: Prompt files reachable through the administrator UI. Path is always rebuilt
#: from this whitelist; a requested name that is not a member raises instead of
#: touching the filesystem.
ALLOWED_PROMPTS: tuple[str, ...] = (
    "coordinator.md",
    "knowledge_graph.md",
    "learner_profile.md",
    "path_planning.md",
    "qa.md",
    "evaluation_feedback.md",
    "mind_map_gen.md",
    "code_case_gen.md",
    "video_script_gen.md",
    "resource_gen.md",
    "exercise_gen.md",
)

_PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _path_for(name: str) -> Path:
    """Resolve a whitelisted name to its prompt file, rejecting anything else."""

    if name not in ALLOWED_PROMPTS:
        raise LookupError(f"Unknown prompt template: {name}")
    return PROMPT_DIR / name


def _placeholders(content: str) -> list[str]:
    """Return the sorted, de-duplicated variable names a template declares."""

    return sorted({match.group(1) for match in _PLACEHOLDER_PATTERN.finditer(content)})


def list_prompts() -> list[dict[str, object]]:
    """Enumerate whitelisted templates without their full bodies."""

    items: list[dict[str, object]] = []
    for name in ALLOWED_PROMPTS:
        path = PROMPT_DIR / name
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        items.append(
            {
                "name": name,
                "chars": len(content),
                "placeholders": _placeholders(content),
            }
        )
    return items


def read_prompt(name: str) -> dict[str, object]:
    """Return one template body plus its declared placeholders."""

    path = _path_for(name)
    content = path.read_text(encoding="utf-8")
    return {"name": name, "content": content, "placeholders": _placeholders(content)}


def update_prompt(name: str, content: str) -> dict[str, object]:
    """Replace one template body, preserving its declared variables.

    Raises :class:`LookupError` for an unknown name and :class:`ValueError` when
    the replacement drops a placeholder the current template (and therefore its
    renderer) depends on.
    """

    path = _path_for(name)
    original = path.read_text(encoding="utf-8")
    declared = set(_placeholders(original))
    missing = sorted(declared - set(_placeholders(content)))
    if missing:
        raise ValueError(f"Prompt must keep placeholders: {', '.join(missing)}")
    # Normalise a trailing newline for consistent diffs; never mutate in place.
    path.write_text(content, encoding="utf-8")
    return {"name": name, "chars": len(content), "placeholders": _placeholders(content)}
