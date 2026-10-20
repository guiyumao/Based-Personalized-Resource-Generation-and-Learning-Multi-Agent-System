"""Deterministic local PPTX/SVG/WAV production inside the existing assistant worker."""
import hashlib
import io
import os
import re
import subprocess
import tempfile
import wave
from html import escape
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from common.knowledge_paths import KNOWLEDGE_ROOT, PROJECT_ROOT
from common.learning_context import validate_context
from common.models.media import ResourceArtifact
from services.agent_service.app.services.assistant_execution import ensure_write_allowed

FORMATS = {"pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "pptx"),
           "animation": ("image/svg+xml", "svg"), "audio": ("audio/wav", "wav")}
ARTIFACT_ROOT = KNOWLEDGE_ROOT / "resource_artifacts"


def render_pptx(title, content):
    from pptx import Presentation
    from pptx.util import Pt
    presentation = Presentation()
    lines = [re.sub(r"^[#*\-\s]+", "", text).strip() for text in content.splitlines() if text.strip()][:200]
    for offset in range(0, max(1, len(lines)), 6):
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = str(title or "学习课件")[:100] if offset == 0 else f"{title or '学习课件'} · {offset//6+1}"
        frame = slide.placeholders[1].text_frame
        frame.clear()
        for index, text in enumerate(lines[offset:offset+6]):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            paragraph.text = text[:800]
            paragraph.font.size = Pt(20)
    output = io.BytesIO()
    presentation.save(output)
    # Validate real round-trip before allowing persistence.
    assert len(Presentation(io.BytesIO(output.getvalue())).slides) > 0
    return output.getvalue()


def render_animation(title, content):
    steps = [line.lstrip("# -*").strip()[:70] for line in content.splitlines() if line.strip()][:6]
    if not steps:
        raise ValueError("Animation source is empty")
    rows = [f'<text x="35" y="45" font-size="24">{escape(str(title or "知识步骤演示")[:70])}</text>']
    duration = len(steps)*2
    for index, text in enumerate(steps):
        # SVG SMIL only, no script, foreignObject, links or remote assets.
        rows.append(f'<g><rect x="20" y="{75+index*75}" width="860" height="58" rx="10" fill="#dce8ff">'
            f'<animate attributeName="opacity" values="0.25;1;0.25" dur="{duration}s" begin="{index*2}s" repeatCount="indefinite"/></rect>'
            f'<text x="35" y="{112+index*75}" font-size="19">{index+1}. {escape(text)}</text></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 {100+len(steps)*75}" role="img" aria-label="知识步骤动画">'
        '<rect width="100%" height="100%" fill="white"/>' + "".join(rows) + '</svg>').encode()


def render_audio(content):
    if os.name != "nt":
        raise ValueError("BLOCKED: Windows local speech engine is unavailable")
    text = re.sub(r"[#*`>\[\]]", "", content).strip()[:1600]
    if not text:
        raise ValueError("Audio source is empty")
    with tempfile.TemporaryDirectory(prefix="learning-tts-") as directory:
        source, output = Path(directory)/"text.txt", Path(directory)/"speech.wav"
        source.write_text(text, encoding="utf-8")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(PROJECT_ROOT/"scripts/render_local_speech.ps1"),
            "-TextPath", str(source), "-OutputPath", str(output)], capture_output=True, timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or not output.is_file():
            raise ValueError("BLOCKED: local speech engine did not produce audio")
        with wave.open(str(output)) as audio:
            if audio.getnframes() == 0 or audio.getframerate() <= 0:
                raise ValueError("Local speech produced an invalid WAV")
        return output.read_bytes()


def produce_artifact(db, task):
    context_id, kind = task.request_json.get("learning_context_id"), task.request_json.get("artifact_kind")
    if kind not in FORMATS:
        raise ValueError("Unsupported artifact type")
    context, _, _, _, _, resource = validate_context(db, task.user_id, context_id)
    if resource is None:
        raise ValueError("Select a resource before creating an artifact")
    existing = db.query(ResourceArtifact).filter_by(context_id=context_id, kind=kind).first()
    if existing:
        verified_path(existing)
        return result_card(existing)
    title, content = resource.title, resource.content
    db.rollback()  # No long SQL transaction during local rendering.
    payload = render_pptx(title, content) if kind == "pptx" else render_animation(title, content) if kind == "animation" else render_audio(content)
    ensure_write_allowed(db)
    context, _, _, _, _, resource = validate_context(db, task.user_id, context_id)
    existing = db.query(ResourceArtifact).filter_by(context_id=context_id, kind=kind).first()
    if existing:
        return result_card(existing)
    artifact_id = str(uuid4())
    relative = f"{task.user_id}/{artifact_id}.{FORMATS[kind][1]}"
    target = (ARTIFACT_ROOT/relative).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    row = ResourceArtifact(id=artifact_id, user_id=task.user_id, resource_id=resource.id, context_id=context_id,
        resource_version=context.resource_version, kind=kind, relative_path=relative, sha256=hashlib.sha256(payload).hexdigest(), size=len(payload))
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        raise
    return result_card(row)


def result_card(row):
    return {"content": f"已生成并保存{row.kind}学习产物。", "cards": [{"type": "artifact", "artifact_id": row.id,
        "kind": row.kind, "learning_context_id": row.context_id}], "artifact_id": row.id}


def verified_path(row):
    path = (ARTIFACT_ROOT/row.relative_path).resolve()
    if not path.is_relative_to(ARTIFACT_ROOT.resolve()) or not path.is_file():
        raise HTTPException(404, "Artifact file unavailable")
    if hashlib.sha256(path.read_bytes()).hexdigest() != row.sha256:
        raise HTTPException(409, "Artifact integrity check failed")
    return path
