"""Private homework originals. Never expose the upload directory as static files."""

import hashlib
import io
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text

from common.db.session import SessionLocal
from common.models.learning import (
    Assignment,
    AssignmentSubmission,
    ClassEnrollment,
    Classroom,
    HomeworkAttachment,
)

MAX_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MIMES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".md": "text/plain",
    ".csv": "text/csv",
    ".zip": "application/zip",
}


def root_dir():
    from sqlalchemy.engine import make_url

    from common.config import get_settings

    explicit = os.environ.get("HOMEWORK_UPLOAD_ROOT")
    if explicit:
        return Path(explicit).resolve()
    database = make_url(get_settings().database_url)
    if (
        database.drivername.startswith("sqlite")
        and database.database
        and database.database != ":memory:"
    ):
        return Path(database.database).resolve().parent / "homework-files"
    return Path(__file__).resolve().parents[4] / "data/homework-files"


def descriptor(row):
    return {
        "is_pending": row.submission_id is None,
        "id": row.id,
        "file_name": row.file_name,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
    }


def current_files(db, submission_id):
    return [
        descriptor(row)
        for row in db.query(HomeworkAttachment)
        .filter_by(submission_id=submission_id, is_current=True)
        .order_by(HomeworkAttachment.id)
        .all()
    ]


def assert_can_submit(db, assignment_id, student_id):
    from common.assignment_access import can_access_assignment
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "作业不存在")
    if not can_access_assignment(db, assignment_id, student_id):
        raise HTTPException(403, "该补强作业仅面向指定学生")
    if (
        not db.query(ClassEnrollment)
        .filter_by(class_id=assignment.class_id, student_user_id=student_id)
        .first()
    ):
        raise HTTPException(403, "仅本班学生可上传作业附件")
    if (
        assignment.status != "published"
        or db.get(Classroom, assignment.class_id).status != "active"
    ):
        raise HTTPException(409, "作业或班级已关闭")
    if assignment.due_at and datetime.utcnow() > assignment.due_at:
        raise HTTPException(409, "作业已截止")
    submission = (
        db.query(AssignmentSubmission)
        .filter_by(assignment_id=assignment_id, student_user_id=student_id)
        .first()
    )
    if submission and submission.status == "reviewed":
        raise HTTPException(409, "作业已批改，不能上传新附件")
    if submission:
        from common.models.teacher_support import ReinforcementAttempt
        if db.query(ReinforcementAttempt.id).filter_by(submission_id=submission.id).first():
            raise HTTPException(409, "已提交补强练习并展示参考答案，不能追加附件")
    return assignment


def validate_file(name, data):
    name = re.sub(r"[\x00-\x1f\x7f]", "", PureWindowsPath(name or "").name).strip()[:240]
    ext = Path(name).suffix.lower()
    if ext not in MIMES:
        raise HTTPException(415, "不支持此文件格式，请使用照片、PDF、Office文档、文本或ZIP")
    if not data:
        raise HTTPException(422, "不能上传空文件")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "单个附件不能超过20MB")
    valid = True
    if ext in {".jpg", ".jpeg"}:
        valid = data.startswith(b"\xff\xd8\xff")
    elif ext == ".png":
        valid = data.startswith(b"\x89PNG\r\n\x1a\n")
    elif ext == ".gif":
        valid = data.startswith((b"GIF87a", b"GIF89a"))
    elif ext == ".bmp":
        valid = data.startswith(b"BM")
    elif ext == ".webp":
        valid = data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    elif ext in {".heic", ".heif"}:
        valid = data[4:8] == b"ftyp" and data[8:12] in {
            b"heic",
            b"heix",
            b"hevc",
            b"hevx",
            b"mif1",
            b"msf1",
        }
    elif ext == ".pdf":
        valid = b"%PDF-" in data[:1024]
    elif ext in {".doc", ".xls", ".ppt"}:
        valid = data.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
    elif ext in {".docx", ".xlsx", ".pptx", ".zip"}:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if len(names) > 2000:
                    raise HTTPException(415, "压缩文件条目过多，请拆分上传")
                required = {
                    ".docx": "word/document.xml",
                    ".xlsx": "xl/workbook.xml",
                    ".pptx": "ppt/presentation.xml",
                }.get(ext)
                valid = required is None or (required in names and "[Content_Types].xml" in names)
        except (zipfile.BadZipFile, ValueError):
            valid = False
    else:
        valid = b"\x00" not in data[:8192]
    if not valid:
        raise HTTPException(415, "文件内容与扩展名不符，或文件已损坏")
    return name, MIMES[ext], ext


def save_file(assignment_id, student_id, name, data):
    name, mime, ext = validate_file(name, data)
    digest = hashlib.sha256(data).hexdigest()
    with SessionLocal() as db:
        if db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        assert_can_submit(db, assignment_id, student_id)
        pending = (
            db.query(HomeworkAttachment)
            .filter_by(assignment_id=assignment_id, student_user_id=student_id, submission_id=None)
            .all()
        )
        duplicate = next((r for r in pending if r.sha256 == digest and r.file_name == name), None)
        if duplicate:
            return descriptor(duplicate)
        if len(pending) >= 10 or sum(r.size_bytes for r in pending) + len(data) > MAX_TOTAL_BYTES:
            raise HTTPException(413, "待提交附件最多10个，总大小不能超过100MB，请移除不需要的文件")
        key = uuid4().hex + ext
        directory = root_dir()
        directory.mkdir(parents=True, exist_ok=True)
        file_path = directory / key
        try:
            with file_path.open("xb") as stream:
                stream.write(data)
            row = HomeworkAttachment(
                assignment_id=assignment_id,
                student_user_id=student_id,
                file_name=name,
                storage_key=key,
                content_type=mime,
                size_bytes=len(data),
                sha256=digest,
                is_current=False,
            )
            db.add(row)
            db.flush()
            info = descriptor(row)
            db.commit()
            return info
        except BaseException:
            file_path.unlink(missing_ok=True)
            raise


def readable_file(db, file_id, user):
    row = db.get(HomeworkAttachment, file_id)
    if not row:
        raise HTTPException(404, "附件不存在")
    assignment = db.get(Assignment, row.assignment_id)
    owner = user.id == row.student_user_id and user.role == "student"
    teacher = (
        row.submission_id is not None
        and assignment
        and assignment.teacher_user_id == user.id
        and user.role == "teacher"
    )
    if not owner and not teacher and user.role != "admin":
        raise HTTPException(403, "无权读取此作业附件")
    target = (root_dir() / row.storage_key).resolve()
    if not target.is_relative_to(root_dir().resolve()) or not target.is_file():
        raise HTTPException(404, "附件文件不存在")
    return row, target
