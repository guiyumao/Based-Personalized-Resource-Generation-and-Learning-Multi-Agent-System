"""Authenticated upload, preview, download and pending-file removal."""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text

from common.db.session import SessionLocal
from common.dependencies import get_current_user, require_role
from common.models.learning import HomeworkAttachment, User
from common.schemas.response import ApiResponse
from services.teacher_service.app.schemas.teacher import HomeworkFileItem
from services.teacher_service.app.services.homework_files import MAX_BYTES, readable_file, save_file

router = APIRouter()


@router.post(
    "/students/me/homework/{assignment_id}/attachments",
    response_model=ApiResponse[HomeworkFileItem],
    status_code=201,
)
async def upload(
    assignment_id: int, file: UploadFile = File(...), user: User = Depends(require_role("student"))
):
    try:
        data = await file.read(MAX_BYTES + 1)
        return ApiResponse(data=save_file(assignment_id, user.id, file.filename, data))
    finally:
        await file.close()


@router.get("/homework/attachments/{file_id}")
def download(file_id: int, user: User = Depends(get_current_user)):
    with SessionLocal() as db:
        row, target = readable_file(db, file_id, user)
        return FileResponse(
            target,
            media_type=row.content_type,
            filename=row.file_name,
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
        )


@router.get("/homework/attachments/{file_id}/preview")
def text_preview(file_id: int, user: User = Depends(get_current_user)):
    with SessionLocal() as db:
        row, target = readable_file(db, file_id, user)
        ext = Path(row.file_name).suffix.lower()
        try:
            if ext == ".docx":
                with zipfile.ZipFile(target) as archive:
                    if archive.getinfo("word/document.xml").file_size > 2 * 1024 * 1024:
                        raise HTTPException(413, "文档正文过大，请下载原文件查看")
                    document = ET.fromstring(archive.read("word/document.xml"))
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    text = "\n".join("".join(p.itertext()) for p in document.findall(".//w:p", ns))
            elif ext in {".txt", ".md", ".csv"}:
                raw = target.read_bytes()[:200_000]
                try:
                    text = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = raw.decode("gb18030", errors="replace")
            else:
                raise HTTPException(415, "此格式请下载原文件查看")
        except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
            raise HTTPException(422, "文档无法预览，请下载原文件查看") from exc
        return {"file_name": row.file_name, "text": text[:50_000], "truncated": len(text) > 50_000}


@router.delete("/students/me/homework/attachments/{file_id}")
def remove_pending(file_id: int, user: User = Depends(require_role("student"))):
    with SessionLocal() as db:
        if db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        row = db.query(HomeworkAttachment).filter_by(id=file_id).with_for_update().first()
        if not row or row.student_user_id != user.id:
            raise HTTPException(404, "附件不存在")
        if row.submission_id is not None:
            raise HTTPException(409, "已提交附件不能删除，可在重新提交前从本次附件列表中移除")
        _, target = readable_file(db, file_id, user)
        db.delete(row)
        db.commit()
        target.unlink(missing_ok=True)
        return {"deleted": True}
