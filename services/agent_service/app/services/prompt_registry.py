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
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
PROMPT_DIR = _PROJECT_ROOT / "prompts"

#: Prompt files reachable through the administrator UI. Path is always rebuilt
#: from this whitelist; a requested name that is not a member raises instead of
#: touching the filesystem.
#:
#: Only templates that the generation chain actually loads via
#: :func:`load_prompt_template` are listed, so an administrator edit always has
#: a real consumer. ``coordinator.md`` / ``knowledge_graph.md`` /
#: ``learner_profile.md`` / ``path_planning.md`` / ``qa.md`` are deliberately
#: excluded: they are descriptive stubs with no loader — the Coordinator and QA
#: services still embed their prompts inline — so exposing them here would let
#: an admin "edit" a template that changes nothing (the "two systems" gap in
#: section 七). Wiring those is tracked as a separate follow-up, not hidden here.
ALLOWED_PROMPTS: tuple[str, ...] = (
    "resource_gen.md",
    "exercise_gen.md",
    "evaluation_feedback.md",
    "mind_map_gen.md",
    "code_case_gen.md",
    "video_script_gen.md",
)

_PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

#: Directory holding version snapshots, relative to ``PROMPT_DIR``.
HISTORY_DIR_NAME = ".history"

#: In-process template cache keyed by filename, storing ``(mtime, content)``.
_PROMPT_CACHE: dict[str, tuple[float, str]] = {}


def load_prompt_template(filename: str) -> str:
    """Load a prompt template body, re-reading it when the file changes.

    This is the single load path used by the generation services so an
    administrator's edit (via :func:`update_prompt`) is picked up by the next
    generation task without a process restart, while still avoiding a file read
    on every call when the template is unchanged.
    """

    path = PROMPT_DIR / filename
    mtime = path.stat().st_mtime
    cached = _PROMPT_CACHE.get(filename)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    content = path.read_text(encoding="utf-8")
    _PROMPT_CACHE[filename] = (mtime, content)
    return content


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
    # Snapshot the previous body first so the administrator can restore it.
    _snapshot(name, original)
    # Normalise a trailing newline for consistent diffs; never mutate in place.
    path.write_text(content, encoding="utf-8")
    return {"name": name, "chars": len(content), "placeholders": _placeholders(content)}


def _history_dir(name: str) -> Path:
    """Resolve the version-snapshot directory for a whitelisted template."""

    _path_for(name)  # validate the name
    return PROMPT_DIR / HISTORY_DIR_NAME / name


def _version_id() -> str:
    """A sortable, filesystem-safe UTC version label with microsecond precision."""

    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + "Z"


def _snapshot(name: str, content: str | None = None) -> str | None:
    """Persist the current body of ``name`` as a version snapshot.

    Returns the new version id, or ``None`` when the live template does not
    exist (so a first-time create has nothing to snapshot).
    """

    path = _path_for(name)
    if content is None:
        if not path.is_file():
            return None
        content = path.read_text(encoding="utf-8")
    hdir = _history_dir(name)
    hdir.mkdir(parents=True, exist_ok=True)
    version = _version_id()
    (hdir / f"{version}.md").write_text(content, encoding="utf-8")
    return version


def list_prompt_versions(name: str) -> list[dict[str, object]]:
    """Enumerate version snapshots for one template, newest first."""

    hdir = _history_dir(name)
    if not hdir.is_dir():
        return []
    versions: list[dict[str, object]] = []
    for snapshot in sorted(hdir.glob("*.md"), reverse=True):
        content = snapshot.read_text(encoding="utf-8")
        versions.append(
            {
                "version": snapshot.stem,
                "chars": len(content),
                "placeholders": _placeholders(content),
            }
        )
    return versions


def read_prompt_version(name: str, version: str) -> dict[str, object]:
    """Return one version snapshot body plus its declared placeholders."""

    _path_for(name)
    if not re.fullmatch(r"[0-9TZ]+", version):
        raise LookupError(f"Unknown prompt version: {version}")
    path = _history_dir(name) / f"{version}.md"
    if not path.is_file():
        raise LookupError(f"Unknown prompt version: {version}")
    content = path.read_text(encoding="utf-8")
    return {"name": name, "version": version, "content": content, "placeholders": _placeholders(content)}


def restore_prompt(name: str, version: str) -> dict[str, object]:
    """Restore a version snapshot as the live template, snapshotting first.

    The current body is preserved as a new snapshot before the restore so no
    state is ever lost, making the operation safely reversible.
    """

    snapshot = read_prompt_version(name, version)
    _snapshot(name)
    _path_for(name).write_text(snapshot["content"], encoding="utf-8")
    return {
        "name": name,
        "chars": len(snapshot["content"]),
        "placeholders": _placeholders(snapshot["content"]),
    }
