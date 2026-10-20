"""Transcript upload, correction, analysis and report interaction APIs."""

from __future__ import annotations

import hashlib
import io
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from common.db.session import get_db
from common.dependencies import get_current_user, require_role
from common.models.learning import TranscriptAnalysis, TranscriptImport, User
from common.schemas.response import ApiResponse
from services.evaluation_service.app.schemas.transcript import (
    TranscriptAnalyzeRequest,
    TranscriptChatRequest,
    TranscriptParseResponse,
)
from services.evaluation_service.app.services.transcript_analysis import TranscriptAnalysisService
from services.evaluation_service.app.services.transcript_parser import (
    TranscriptParseError,
    parse_transcript,
)

router = APIRouter(prefix="/transcripts")


@router.post("/parse", response_model=ApiResponse[TranscriptParseResponse])
async def parse_transcript_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[TranscriptParseResponse]:
    """Parse a transcript without starting analysis; callers can correct the preview first."""
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 20MB。")
    try:
        parsed = parse_transcript(file.filename or "transcript", content)
    except TranscriptParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    parsed = TranscriptAnalysisService(db).store_preview(current_user.id, parsed, hashlib.sha256(content).hexdigest())
    return ApiResponse(data=TranscriptParseResponse(**parsed), message="成绩单解析完成，请校正后提交分析。")


@router.post("/analyze")
def analyze_transcript(
    payload: TranscriptAnalyzeRequest,
    current_user: User = Depends(require_role("student", "teacher", "admin")),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, object]]:
    """Run serial diagnosis and parallel resource/exercise recommendation agents."""
    if payload.scope == "class" and current_user.role == "student":
        raise HTTPException(status_code=403, detail="只有教师或管理员可以生成班级分析。")
    if payload.import_id is not None:
        imported = db.get(TranscriptImport, payload.import_id)
        if imported is None or imported.owner_user_id != current_user.id:
            raise HTTPException(status_code=404, detail="成绩单导入记录不存在或无权访问。")
    try:
        result = TranscriptAnalysisService(db).persist_and_analyze(
            current_user.id, payload, sync_profile=current_user.role == "student"
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    message = "成绩单分析完成，结果已同步至学情画像。" if payload.scope == "student" and current_user.role == "student" else "成绩单分析完成。"
    return ApiResponse(data=result, message=message)


@router.get("/history")
def transcript_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[dict[str, object]]]:
    """List recent analyses owned by the current account."""
    return ApiResponse(data=TranscriptAnalysisService(db).history(current_user.id), message="历史分析已加载。")


@router.get("/analysis/{analysis_id}")
def get_transcript_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, object]]:
    try:
        result = TranscriptAnalysisService(db).get_analysis(current_user.id, analysis_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=result, message="分析详情已加载。")


@router.post("/chat")
def transcript_chat(
    payload: TranscriptChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Answer a follow-up using the persisted structured report as context."""
    try:
        result = TranscriptAnalysisService(db).get_analysis(current_user.id, payload.analysis_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    weak = "、".join(result["student_profile"]["weak_subjects"]) or "当前薄弱科目"
    answer = (
        f"基于这份成绩单，建议优先处理 {weak}。你问到“{payload.question}”，当前报告能确认的是："
        f"整体均分为 {result['score_statistics']['overall_average']} 分，薄弱点诊断属于成绩单级推断；"
        "如果补充题目/章节得分，我可以把建议细化到知识点。"
    )
    return ApiResponse(data={"answer": answer, "model": "transcript_master_agent-fallback", "created_at": datetime.utcnow().isoformat()}, message="已基于报告回答。")


@router.post("/analysis/{analysis_id}/share")
def create_share_link(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    analysis = db.query(TranscriptAnalysis).filter(
        TranscriptAnalysis.id == analysis_id,
        TranscriptAnalysis.owner_user_id == current_user.id,
    ).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="分析不存在或无权分享。")
    if not analysis.share_token:
        import secrets

        analysis.share_token = secrets.token_urlsafe(24)
        db.commit()
    return ApiResponse(data={"share_token": analysis.share_token, "path": f"/evaluation/transcripts/shared/{analysis.share_token}"}, message="分享链接已生成。")


@router.get("/shared/{share_token}")
def get_shared_report(share_token: str, db: Session = Depends(get_db)) -> ApiResponse[dict[str, object]]:
    try:
        result = TranscriptAnalysisService(db).get_shared_analysis(share_token)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=result, message="分享报告已加载。")


@router.get("/analysis/{analysis_id}/export")
def export_transcript_report(
    analysis_id: int,
    format: str = Query(default="markdown", pattern="^(markdown|html|docx|pdf)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        result = TranscriptAnalysisService(db).get_analysis(current_user.id, analysis_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    report_text = result["report_text"]
    if format == "markdown":
        return Response(report_text, media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="transcript-{analysis_id}.md"'})
    if format == "html":
        body = "<html><meta charset='utf-8'><body><pre>" + report_text.replace("&", "&amp;").replace("<", "&lt;") + "</pre></body></html>"
        return Response(body, media_type="text/html", headers={"Content-Disposition": f'attachment; filename="transcript-{analysis_id}.html"'})
    if format == "docx":
        try:
            from docx import Document  # type: ignore
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="Word 导出依赖未安装。") from exc
        document = Document()
        for line in report_text.splitlines():
            document.add_paragraph(line.lstrip("# "))
        buffer = io.BytesIO()
        document.save(buffer)
        return Response(buffer.getvalue(), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="transcript-{analysis_id}.docx"'})
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.pdfbase import pdfmetrics  # type: ignore
        from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="PDF 导出依赖未安装。") from exc
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    font_name = "Helvetica"
    for font_path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"):
        try:
            pdfmetrics.registerFont(TTFont("TranscriptCJK", font_path, subfontIndex=0))
            font_name = "TranscriptCJK"
            break
        except (FileNotFoundError, OSError, IndexError):
            continue
    pdf.setFont(font_name, 10)
    y = 800
    for line in report_text.splitlines():
        pdf.drawString(40, y, line[:110])
        y -= 16
        if y < 40:
            pdf.showPage()
            y = 800
    pdf.save()
    return Response(buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="transcript-{analysis_id}.pdf"'})
