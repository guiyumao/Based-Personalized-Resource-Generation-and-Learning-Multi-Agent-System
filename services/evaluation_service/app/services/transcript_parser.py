"""Format-aware transcript extraction with explainable validation and OCR fallback."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from services.evaluation_service.app.schemas.transcript import TranscriptRow

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "student_no": ("学号", "学生编号", "编号", "学籍号", "student id", "id"),
    "student_name": ("姓名", "学生姓名", "名字", "name", "student"),
    "class_name": ("班级", "行政班", "class", "班"),
    "subject": ("科目", "学科", "课程", "subject", "course"),
    "score": ("分数", "得分", "成绩", "总分", "score", "mark", "points"),
    "max_score": ("满分", "总分值", "试卷满分", "max score", "full mark"),
    "exam_date": ("考试时间", "考试日期", "日期", "时间", "exam date", "date"),
    "chapter": ("章节", "知识点", "单元", "chapter", "topic"),
}


class TranscriptParseError(ValueError):
    """Raised when a file cannot produce a usable tabular preview."""


def parse_transcript(file_name: str, content: bytes) -> dict[str, Any]:
    """Parse a supported transcript format into a normalized preview."""

    suffix = Path(file_name).suffix.lower()
    if suffix == ".csv":
        matrix = _parse_csv(content)
        ocr_mode = False
    elif suffix == ".xlsx":
        matrix = _parse_xlsx(content)
        ocr_mode = False
    elif suffix == ".xls":
        matrix = _parse_xls(content)
        ocr_mode = False
    elif suffix == ".docx":
        matrix = _parse_docx(content)
        ocr_mode = False
    elif suffix == ".pdf":
        matrix, ocr_mode = _parse_pdf(content)
    elif suffix in {".jpg", ".jpeg", ".png"}:
        matrix = _parse_image(content)
        ocr_mode = True
    else:
        raise TranscriptParseError("暂不支持该文件格式，请上传 xlsx/xls/csv/docx/pdf/jpg/png 文件。")

    headers, rows = _find_subject_table(matrix)
    mapping = map_fields(headers)
    normalized, warnings, low_confidence = normalize_rows(headers, rows, mapping, ocr_mode=ocr_mode)
    if not normalized:
        raise TranscriptParseError("未识别到可用成绩行，请检查表格表头或使用人工录入。")
    quality = _quality_score(headers, normalized, warnings)
    return {
        "file_name": file_name,
        "file_type": suffix.lstrip(".") or "manual",
        "headers": headers,
        "rows": normalized,
        "field_mapping": mapping,
        "warnings": warnings,
        "quality_score": quality,
        "ocr_mode": ocr_mode,
        "low_confidence_cells": low_confidence,
    }


def map_fields(headers: list[str]) -> dict[str, str | None]:
    """Map semantic fields to source headers using exact and fuzzy aliases."""

    normalized_headers = {header: _clean(header) for header in headers}
    mapping: dict[str, str | None] = {}
    for field, aliases in FIELD_ALIASES.items():
        found = next((h for h, clean in normalized_headers.items() if clean in aliases), None)
        if found is None:
            found = next(
                (h for h, clean in normalized_headers.items() if any(alias in clean or clean in alias for alias in aliases)),
                None,
            )
        mapping[field] = found
    return mapping


def normalize_rows(
    headers: list[str],
    rows: list[list[str]],
    mapping: dict[str, str | None],
    *,
    ocr_mode: bool,
) -> tuple[list[TranscriptRow], list[str], list[dict[str, Any]]]:
    """Clean blank/duplicate/invalid records while retaining actionable warnings."""

    warnings: list[str] = []
    low_confidence_cells: list[dict[str, Any]] = []
    result: list[TranscriptRow] = []
    seen: set[tuple[str, str, str, float]] = set()
    score_header = mapping.get("score")
    if not score_header:
        warnings.append("未自动识别到分数列，请在预览中绑定“考试分数”。")

    for row_index, values in enumerate(rows, start=2):
        padded = values + [""] * max(0, len(headers) - len(values))
        raw = {header: str(padded[index]).strip() for index, header in enumerate(headers)}
        if not any(raw.values()):
            continue
        score_raw = raw.get(score_header or "", "")
        score = _number(score_raw)
        max_score = _number(raw.get(mapping.get("max_score") or "", "")) or 100.0
        if score is None:
            warnings.append(f"第 {row_index} 行分数无法识别，已跳过。")
            continue
        if score < 0 or score > max_score:
            warnings.append(f"第 {row_index} 行分数 {score:g} 超出 0-{max_score:g}，已跳过。")
            continue
        item = TranscriptRow(
            student_no=raw.get(mapping.get("student_no") or "", ""),
            student_name=raw.get(mapping.get("student_name") or "", ""),
            class_name=raw.get(mapping.get("class_name") or "", ""),
            subject=raw.get(mapping.get("subject") or "", ""),
            score=score,
            max_score=max_score,
            exam_date=raw.get(mapping.get("exam_date") or "", "") or None,
            chapter=raw.get(mapping.get("chapter") or "", ""),
            raw=raw,
        )
        key = (item.student_no, item.student_name, item.subject, score)
        if key in seen:
            warnings.append(f"第 {row_index} 行与已有记录重复，已过滤。")
            continue
        seen.add(key)
        if ocr_mode:
            for column, value in raw.items():
                confidence = 0.7 if value else 0.35
                item.confidence[column] = confidence
                if confidence < 0.8:
                    low_confidence_cells.append({"row": row_index, "column": column, "confidence": confidence})
        result.append(item)
    if mapping.get("student_name") is None and mapping.get("student_no") is None:
        warnings.append("未识别到姓名或学号，建议人工绑定后再分析。")
    if mapping.get("subject") is None:
        warnings.append("未识别到科目列，将按整张成绩单汇总。")
    return result, warnings, low_confidence_cells


def _parse_csv(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample.strip() else csv.excel
    return [list(row) for row in csv.reader(io.StringIO(text), dialect)]


def _parse_xml_safely(payload: bytes):
    """Parse XML from an untrusted upload without entity or DTD processing.

    Transcript uploads are user-supplied ``.xlsx``/``.docx`` files, so their inner
    XML must not pull in external entities or expand a billion-laughs payload
    (CWE-611 / CWE-776). ``defusedxml`` performs entity-safe parsing when
    available; otherwise the payload is rejected up front if it declares a DTD or
    any entity, which is what both attack classes require.
    """

    head = payload[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in head:
        raise TranscriptParseError("文件包含 XML DTD/实体声明，出于安全原因已拒绝解析。")

    try:
        from defusedxml.ElementTree import fromstring as _safe_fromstring  # type: ignore
    except ImportError:  # pragma: no cover - defusedxml is a declared dependency
        _safe_fromstring = None

    try:
        if _safe_fromstring is not None:
            return _safe_fromstring(payload)
        # Fallback only: the DTD/entity check above already rejects both attack
        # classes, so the stdlib parser is safe for the remaining documents.
        return ET.fromstring(payload)  # nosec B314
    except TranscriptParseError:
        raise
    except Exception as exc:  # defusedxml raises its own EntitiesForbidden etc.
        raise TranscriptParseError(f"文件中的 XML 结构无法解析：{exc}") from exc


def _parse_xlsx(content: bytes) -> list[list[str]]:
    try:
        from openpyxl import load_workbook  # type: ignore

        workbook = load_workbook(io.BytesIO(content), read_only=False, data_only=True)
        sheet = workbook.active
        matrix = [["" if value is None else str(value) for value in row] for row in sheet.iter_rows(values_only=True)]
        for merged_range in sheet.merged_cells.ranges:
            min_col, min_row, max_col, max_row = merged_range.bounds
            value = matrix[min_row - 1][min_col - 1] if min_row - 1 < len(matrix) and min_col - 1 < len(matrix[min_row - 1]) else ""
            for row_index in range(min_row - 1, max_row):
                while len(matrix) <= row_index:
                    matrix.append([])
                while len(matrix[row_index]) < max_col:
                    matrix[row_index].append("")
                for column_index in range(min_col - 1, max_col):
                    matrix[row_index][column_index] = value
        return matrix
    except ImportError:
        pass
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = _parse_xml_safely(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root]
        sheet_names = sorted(name for name in archive.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", name))
        if not sheet_names:
            raise TranscriptParseError("xlsx 文件没有可读取的工作表。")
        root = _parse_xml_safely(archive.read(sheet_names[0]))
        matrix: list[list[str]] = []
        for row_node in root.findall(".//{*}row"):
            cells: dict[int, str] = {}
            for cell in row_node.findall("{*}c"):
                ref = cell.attrib.get("r", "A1")
                col = _excel_column_index(re.match(r"([A-Z]+)", ref, re.I).group(1)) if re.match(r"([A-Z]+)", ref, re.I) else 0
                value = "".join(cell.findtext("{*}v", default="")) if cell.find("{*}v") is not None else ""
                if cell.attrib.get("t") == "s" and value.isdigit() and int(value) < len(shared):
                    value = shared[int(value)]
                cells[col] = value
            if cells:
                matrix.append([cells.get(i, "") for i in range(max(cells) + 1)])
        return matrix


def _parse_xls(content: bytes) -> list[list[str]]:
    try:
        import xlrd  # type: ignore
    except ImportError as exc:
        raise TranscriptParseError("解析 .xls 需要安装 xlrd，当前服务未安装该依赖。") from exc
    workbook = xlrd.open_workbook(file_contents=content)
    sheet = workbook.sheet_by_index(0)
    return [[str(sheet.cell_value(row, column)) for column in range(sheet.ncols)] for row in range(sheet.nrows)]


def _parse_docx(content: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root = _parse_xml_safely(archive.read("word/document.xml"))
    matrix = []
    for table in root.findall(".//{*}tbl"):
        for row in table.findall("{*}tr"):
            matrix.append(["".join(cell.itertext()).strip() for cell in row.findall("{*}tc")])
    return matrix


def _parse_pdf(content: bytes) -> tuple[list[list[str]], bool]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise TranscriptParseError("解析 PDF 需要安装 pypdf。") from exc
    reader = PdfReader(io.BytesIO(content))
    lines = []
    for page in reader.pages:
        lines.extend((page.extract_text() or "").splitlines())
    matrix = [[part.strip() for part in re.split(r"\s{2,}|\t|,|，", line) if part.strip()] for line in lines if line.strip()]
    if len(matrix) > 1 and any(any(_clean(token) == "姓名" for token in row) for row in matrix[:5]):
        return matrix, False
    image_matrix = _try_ocr(content, pdf=True)
    if image_matrix:
        return image_matrix, True
    raise TranscriptParseError("PDF 未提取到原生文本表格；扫描版 OCR 不可用，请安装 OCR 引擎或改传图片。")


def _parse_image(content: bytes) -> list[list[str]]:
    matrix = _try_ocr(content, pdf=False)
    if matrix:
        return matrix
    raise TranscriptParseError("图片 OCR 不可用：请安装 Pillow、pytesseract 与本机 Tesseract，或改传表格文件。")


def _try_ocr(content: bytes, *, pdf: bool) -> list[list[str]]:
    try:
        import pytesseract  # type: ignore
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps  # type: ignore
    except ImportError:
        return []
    try:
        if pdf:
            import pypdfium2 as pdfium  # type: ignore

            document = pdfium.PdfDocument(content)
            images = [document[index].render(scale=2).to_pil() for index in range(len(document))]
        else:
            images = [Image.open(io.BytesIO(content))]
        lines: list[str] = []
        for source in images:
            image = ImageOps.grayscale(source)
            image = ImageOps.autocontrast(image).filter(ImageFilter.MedianFilter(size=3))
            image = ImageEnhance.Contrast(image).enhance(1.6)
            text = pytesseract.image_to_string(image, lang="chi_sim+eng")
            lines.extend(text.splitlines())
        return [[part.strip() for part in re.split(r"\s{2,}|\t|,|，", line) if part.strip()] for line in lines if line.strip()]
    except Exception:
        return []


def _find_subject_table(matrix: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    candidates = []
    for index, row in enumerate(matrix):
        header_hits = sum(1 for cell in row if any(alias in _clean(cell) for aliases in FIELD_ALIASES.values() for alias in aliases))
        if header_hits >= 1:
            candidates.append((header_hits, index, row))
    if not candidates:
        raise TranscriptParseError("未找到疑似成绩单表头。支持姓名/学号/科目/分数/满分等关键词。")
    _, header_index, header = max(candidates, key=lambda item: item[0])
    headers = [cell.strip() or f"列{index + 1}" for index, cell in enumerate(header)]
    return headers, [row for row in matrix[header_index + 1 :] if any(str(cell).strip() for cell in row)]


def _quality_score(headers: list[str], rows: list[TranscriptRow], warnings: list[str]) -> float:
    field_score = sum(1 for field in ("student_name", "student_no", "subject", "score") if field in map_fields_for_quality(headers)) / 4
    row_score = min(1.0, len(rows) / 5)
    warning_penalty = min(0.35, len(warnings) * 0.03)
    return round(max(0.0, 0.55 * field_score + 0.45 * row_score - warning_penalty), 3)


def map_fields_for_quality(headers: list[str]) -> dict[str, str | None]:
    return map_fields(headers)


def _excel_column_index(value: str) -> int:
    result = 0
    for char in value.upper():
        result = result * 26 + ord(char) - 64
    return result - 1


def _clean(value: str) -> str:
    return re.sub(r"[\s_\-:：()（）]", "", str(value).strip().lower())


def _number(value: Any) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None
