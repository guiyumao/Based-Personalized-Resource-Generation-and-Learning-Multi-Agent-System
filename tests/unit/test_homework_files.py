"""Real multipart originals, attachment-only submission, preview and ownership checks."""

import io
from uuid import uuid4

import pytest
from docx import Document
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

from common.db.session import SessionLocal
from common.models.learning import User
from common.security.auth import create_access_token
from services.teacher_service.app.main import app
from services.teacher_service.app.services.homework_files import MAX_BYTES, validate_file


def originals():
    image = io.BytesIO()
    Image.new("RGB", (12, 12), "white").save(image, format="PNG")
    doc = Document()
    doc.add_paragraph("作业原文：SQL事务分析与证明。")
    word = io.BytesIO()
    doc.save(word)
    pdf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    return [
        ("手写答案.png", image.getvalue(), "image/png"),
        (
            "作业文档.docx",
            word.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("推导.pdf", pdf.getvalue(), "application/pdf"),
    ]


@pytest.fixture
def context():
    with SessionLocal() as db:
        users = [
            User(
                username="files-" + uuid4().hex[:10],
                role=role,
                password_hash="disabled",
                is_active=True,
            )
            for role in ["teacher", "student", "student", "teacher"]
        ]
        db.add_all(users)
        db.commit()
        ids = [u.id for u in users]
    client = TestClient(app)

    def call(who, method, url, status=200, **kwargs):
        result = client.request(
            method,
            "/teacher" + url,
            headers={"Authorization": "Bearer " + create_access_token(str(ids[who]))},
            **kwargs,
        )
        assert result.status_code == status, result.text
        return result

    cls = call(0, "POST", "/classes", json={"name": "附件验收班", "subject": "数学"}).json()["data"]
    for who in [1, 2]:
        call(who, "POST", "/students/me/classes/join", json={"invite_code": cls["invite_code"]})
    assignment = call(
        0,
        "POST",
        "/homework/assign",
        json={"class_id": cls["id"], "title": "附件作业", "description": "支持原文件"},
    ).json()["data"]
    yield call, assignment
    client.close()


def test_attachment_only_roundtrip_teacher_previews_and_downloads(context):
    call, assignment = context
    files = []
    payloads = originals()
    for name, data, mime in payloads:
        file = call(
            1,
            "POST",
            f"/students/me/homework/{assignment['id']}/attachments",
            201,
            files={"file": (name, data, mime)},
        ).json()["data"]
        assert file["file_name"] == name and file["size_bytes"] == len(data)
        assert call(1, "GET", f"/homework/attachments/{file['id']}").content == data
        call(0, "GET", f"/homework/attachments/{file['id']}", 403)
        call(2, "GET", f"/homework/attachments/{file['id']}", 403)
        files.append(file)
    submitted = call(
        1,
        "POST",
        f"/students/me/homework/{assignment['id']}/submit",
        json={"content": "", "attachment_ids": [f["id"] for f in files]},
    ).json()["data"]
    assert submitted["content"] == "" and len(submitted["attachments"]) == 3
    teacher = call(0, "GET", f"/homework/{assignment['id']}/submissions").json()["data"][0]
    assert teacher["attachments"] == submitted["attachments"]
    for file, (_, data, _) in zip(files, payloads, strict=True):
        response = call(0, "GET", f"/homework/attachments/{file['id']}")
        assert response.content == data
        call(3, "GET", f"/homework/attachments/{file['id']}", 403)
    preview = call(0, "GET", f"/homework/attachments/{files[1]['id']}/preview").json()
    assert "SQL事务分析" in preview["text"]
    call(2, "GET", f"/homework/attachments/{files[1]['id']}/preview", 403)
    call(
        2,
        "POST",
        f"/students/me/homework/{assignment['id']}/submit",
        403,
        json={"attachment_ids": [files[0]["id"]]},
    )
    call(1, "DELETE", f"/students/me/homework/attachments/{files[0]['id']}", 409)
    revised = call(
        1,
        "POST",
        f"/students/me/homework/{assignment['id']}/submit",
        json={"content": "补充说明", "attachment_ids": [files[1]["id"]]},
    ).json()["data"]
    assert len(revised["attachments"]) == 1 and len(revised["history"][0]["attachments"]) == 3
    call(
        0, "GET", f"/homework/attachments/{files[0]['id']}"
    )  # Historic originals remain available.
    call(
        0, "POST", f"/homework/{submitted['id']}/review", json={"score": 95, "comment": "附件完整"}
    )
    name, data, mime = originals()[0]
    call(
        1,
        "POST",
        f"/students/me/homework/{assignment['id']}/attachments",
        409,
        files={"file": (name, data, mime)},
    )


def test_pending_remove_persistence_and_format_validation(context):
    call, assignment = context
    name, data, mime = originals()[0]
    file = call(
        1,
        "POST",
        f"/students/me/homework/{assignment['id']}/attachments",
        201,
        files={"file": ("../../" + name, data, mime)},
    ).json()["data"]
    assert file["file_name"] == name
    duplicate = call(
        1,
        "POST",
        f"/students/me/homework/{assignment['id']}/attachments",
        201,
        files={"file": (name, data, mime)},
    ).json()["data"]
    assert duplicate["id"] == file["id"]
    homework = call(1, "GET", "/students/me/homework").json()["data"]
    assert (
        next(a for a in homework if a["id"] == assignment["id"])["pending_attachments"][0]["id"]
        == file["id"]
    )
    call(1, "DELETE", f"/students/me/homework/attachments/{file['id']}")
    call(1, "GET", f"/homework/attachments/{file['id']}", 404)
    for filename, body, status in [
        ("程序.exe", b"exe", 415),
        ("伪造.png", b"<html>bad</html>", 415),
        ("空.pdf", b"", 422),
    ]:
        call(
            1,
            "POST",
            f"/students/me/homework/{assignment['id']}/attachments",
            status,
            files={"file": (filename, body, "application/octet-stream")},
        )
    with pytest.raises(HTTPException) as caught:
        validate_file("过大.txt", b"a" * (MAX_BYTES + 1))
    assert caught.value.status_code == 413
    call(1, "POST", f"/students/me/homework/{assignment['id']}/submit", 422, json={"content": ""})
