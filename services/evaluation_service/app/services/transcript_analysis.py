"""Transcript analysis orchestrator and deterministic small-agent fallbacks.

The orchestrator keeps the same contract a model-backed deployment uses: one
dispatcher, three dependent agents, then two parallel recommendation agents.
When no LLM credential is configured, each agent uses transparent statistics so
the UI still receives a useful and auditable result.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from statistics import mean, pvariance
from typing import Any

from sqlalchemy.orm import Session

from common.models.learning import (
    AuditLog,
    Resource,
    TranscriptAnalysis,
    TranscriptImport,
    TranscriptScore,
    UserProfile,
)
from services.evaluation_service.app.schemas.transcript import (
    TranscriptAnalyzeRequest,
    TranscriptRow,
)


class TranscriptAnalysisService:
    """Persist transcript data and execute the five specialized agents."""

    def __init__(self, db: Session):
        self.db = db

    def store_preview(self, owner_user_id: int, parsed: dict[str, Any], content_hash: str) -> dict[str, Any]:
        """Persist a parsed preview so the correction screen can submit an import id."""

        existing = self.db.query(TranscriptImport).filter(
            TranscriptImport.owner_user_id == owner_user_id,
            TranscriptImport.content_hash == content_hash,
        ).first()
        if existing is not None:
            parsed["import_id"] = existing.id
            return parsed
        imported = TranscriptImport(
            owner_user_id=owner_user_id,
            file_name=parsed["file_name"],
            file_type=parsed["file_type"],
            content_hash=content_hash,
            quality_score=parsed["quality_score"],
            field_mapping_json=parsed["field_mapping"],
            normalized_rows_json=[row.model_dump() for row in parsed["rows"]],
            warnings_json=parsed["warnings"],
        )
        self.db.add(imported)
        self.db.add(AuditLog(level="info", event="transcript_parse", message=f"user={owner_user_id} file={parsed['file_name']} hash={content_hash}"[:1000], actor_user_id=owner_user_id))
        self.db.commit()
        parsed["import_id"] = imported.id
        return parsed

    def persist_and_analyze(self, owner_user_id: int, payload: TranscriptAnalyzeRequest, *, sync_profile: bool = True) -> dict[str, Any]:
        rows = [row for row in payload.rows if row.score is not None]
        if not rows:
            raise ValueError("没有可分析的有效成绩记录。")
        selected = self._select_rows(rows, payload)
        normalized = [row.model_dump() for row in rows]
        content_hash = hashlib.sha256(
            json.dumps({
                "owner_user_id": owner_user_id,
                "rows": normalized,
                "scope": payload.scope,
                "target_student_no": (payload.target_student_no or "").strip(),
                "target_student_name": (payload.target_student_name or "").strip(),
            }, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        cached = self.db.query(TranscriptAnalysis).filter(
            TranscriptAnalysis.owner_user_id == owner_user_id,
            TranscriptAnalysis.cache_key == content_hash,
        ).first()
        if cached is not None:
            return self._response(cached, cache_hit=True)

        imported = self.db.get(TranscriptImport, payload.import_id) if payload.import_id else None
        if imported is None:
            imported = TranscriptImport(
                owner_user_id=owner_user_id,
                file_name=payload.file_name,
                file_type=payload.file_type,
                content_hash=content_hash,
                quality_score=self._quality(rows),
                field_mapping_json=payload.field_mapping,
                normalized_rows_json=normalized,
                warnings_json=[],
            )
            self.db.add(imported)
            self.db.flush()
        else:
            imported.normalized_rows_json = normalized
            imported.field_mapping_json = payload.field_mapping

        # A personal analysis belongs only to the selected student. Keep the
        # original corrected sheet in the import preview, without assigning
        # other students' scores to the account's learning history.
        for row in selected if payload.scope == "student" else rows:
            self.db.add(
                TranscriptScore(
                    import_id=imported.id,
                    student_user_id=owner_user_id if payload.scope == "student" else None,
                    student_no=row.student_no,
                    student_name=row.student_name,
                    class_name=row.class_name or payload.class_name or "",
                    subject=row.subject,
                    score=row.score or 0,
                    max_score=row.max_score,
                    exam_date=row.exam_date or payload.exam_date,
                    chapter=row.chapter,
                    question_scores_json=row.question_scores,
                    confidence_json=row.confidence,
                    raw_json=row.raw,
                )
            )
        self.db.flush()

        result = TranscriptAnalysisOrchestrator(self.db).run(
            selected,
            scope=payload.scope,
            quality=self._quality(selected),
            owner_user_id=owner_user_id,
        )
        report_text = build_report_text(result)
        analysis = TranscriptAnalysis(
            import_id=imported.id,
            owner_user_id=owner_user_id,
            scope=payload.scope,
            cache_key=content_hash,
            share_token=secrets.token_urlsafe(24),
            status="completed",
            result_json=result,
            report_text=report_text,
            data_quality=result["data_quality"],
        )
        self.db.add(analysis)
        self.db.flush()
        if payload.scope == "student" and sync_profile:
            self._sync_profile(owner_user_id, result, analysis.id)
        self.db.add(AuditLog(level="info", event="transcript_analysis", message=f"user={owner_user_id} analysis_scope={payload.scope} import_id={imported.id}"[:1000], actor_user_id=owner_user_id))
        self.db.commit()
        return self._response(analysis, cache_hit=False)

    def _select_rows(self, rows: list[TranscriptRow], payload: TranscriptAnalyzeRequest) -> list[TranscriptRow]:
        if payload.scope == "class":
            return rows
        target_no = (payload.target_student_no or "").strip()
        target_name = (payload.target_student_name or "").strip()
        if target_no or target_name:
            selected = [row for row in rows
                        if (not target_no or row.student_no.strip() == target_no)
                        and (not target_name or row.student_name.strip() == target_name)]
            if not selected:
                raise ValueError("所选学生在成绩单中没有有效成绩记录。")
            if not target_no and len({row.student_no.strip() for row in selected if row.student_no.strip()}) > 1:
                raise ValueError("存在同名学生，请同时指定学号。")
            return selected
        identities = {(row.student_no.strip(), row.student_name.strip()) for row in rows}
        if len(identities) > 1:
            raise ValueError("成绩单包含多名或身份不完整的学生，请先选择个人分析对象。")
        return rows

    def _quality(self, rows: list[TranscriptRow]) -> float:
        if not rows:
            return 0.0
        complete = sum(bool(row.student_name or row.student_no) and bool(row.subject) for row in rows)
        return round(complete / len(rows), 3)

    def _sync_profile(self, user_id: int, result: dict[str, Any], analysis_id: int) -> None:
        profile = self.db.get(UserProfile, user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id, mastery_json={}, learning_style="", cognitive_abilities={}, habits={})
            self.db.add(profile)
        # A grade-based pattern is not a self-reported learning modality.
        # Keep the existing preference and store the diagnosis separately.
        profile.mastery_json = {
            **(profile.mastery_json or {}),
            "transcript": {
                "analysis_id": analysis_id,
                "weak_subjects": result["student_profile"]["weak_subjects"],
                "mastery_by_subject": result["score_statistics"]["subject_statistics"],
            },
        }
        profile.profile_analysis = {
            **(profile.profile_analysis or {}),
            "transcript_learning_style": result["student_profile"]["learning_style"],
            "transcript_weak_points": result["weakness_diagnosis"]["weak_points"][:8],
            "transcript_updated_at": datetime.utcnow().isoformat(),
            "stale": True,
        }

    def _response(self, analysis: TranscriptAnalysis, *, cache_hit: bool) -> dict[str, Any]:
        return {
            "analysis_id": analysis.id,
            "import_id": analysis.import_id,
            "status": analysis.status,
            "cache_hit": cache_hit,
            "scope": analysis.scope,
            "data_quality": analysis.data_quality,
            "report_text": analysis.report_text,
            **analysis.result_json,
        }

    def get_analysis(self, owner_user_id: int, analysis_id: int) -> dict[str, Any]:
        analysis = self.db.query(TranscriptAnalysis).filter(
            TranscriptAnalysis.id == analysis_id,
            TranscriptAnalysis.owner_user_id == owner_user_id,
        ).first()
        if analysis is None:
            raise LookupError("成绩单分析不存在或无权访问。")
        return self._response(analysis, cache_hit=False)

    def get_shared_analysis(self, share_token: str) -> dict[str, Any]:
        analysis = self.db.query(TranscriptAnalysis).filter(TranscriptAnalysis.share_token == share_token).first()
        if analysis is None:
            raise LookupError("分享链接不存在或已失效。")
        return self._response(analysis, cache_hit=False)

    def history(self, owner_user_id: int) -> list[dict[str, Any]]:
        items = self.db.query(TranscriptAnalysis).filter(
            TranscriptAnalysis.owner_user_id == owner_user_id,
        ).order_by(TranscriptAnalysis.created_at.desc()).limit(30).all()
        return [
            {
                "id": item.id,
                "import_id": item.import_id,
                "file_name": self.db.get(TranscriptImport, item.import_id).file_name if self.db.get(TranscriptImport, item.import_id) else "",
                "scope": item.scope,
                "status": item.status,
                "data_quality": item.data_quality,
                "created_at": item.created_at.isoformat() if item.created_at else "",
                "summary": item.result_json.get("report", {}).get("summary", ""),
            }
            for item in items
        ]


class TranscriptAnalysisOrchestrator:
    """Dispatcher that models the required serial-then-parallel agent graph."""

    def __init__(self, db: Session | None = None):
        self.db = db

    def run(self, rows: list[TranscriptRow], *, scope: str, quality: float, owner_user_id: int) -> dict[str, Any]:
        statistics_result = self._statistics_agent(rows)
        profile = self._profile_agent(statistics_result)
        weakness = self._weakness_agent(statistics_result, profile)
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="transcript-agent") as pool:
            resources_future = pool.submit(self._resource_agent, weakness, profile)
            exercises_future = pool.submit(self._exercise_agent, weakness, profile)
            resources = resources_future.result()
            exercises = exercises_future.result()
        quality_label = "sufficient" if quality >= 0.5 and len(rows) >= 2 else "limited"
        result = {
            "orchestration": {
                "dispatcher": "transcript_master_agent",
                "serial_agents": ["score_statistics_agent", "student_profile_agent", "weakness_diagnosis_agent"],
                "parallel_agents": ["learning_resource_agent", "exercise_recommendation_agent"],
                "fallback": "deterministic-statistics" if quality_label == "limited" else "deterministic-with-resource-catalog",
                "owner_user_id": owner_user_id,
            },
            "data_quality": quality_label,
            "score_statistics": statistics_result,
            "student_profile": profile,
            "weakness_diagnosis": weakness,
            "resource_recommendations": resources,
            "exercise_recommendations": exercises,
            "report": self._report(statistics_result, profile, weakness, resources, exercises, scope, quality_label),
        }
        if scope == "class":
            grouped: dict[tuple[str, str], list[TranscriptRow]] = defaultdict(list)
            for row in rows:
                grouped[(row.student_no, row.student_name)].append(row)
            result["student_reports"] = [
                self.run(student_rows, scope="student", quality=quality, owner_user_id=owner_user_id)
                for student_rows in grouped.values()
                if student_rows
            ]
        return result

    def _statistics_agent(self, rows: list[TranscriptRow]) -> dict[str, Any]:
        subjects: dict[str, list[TranscriptRow]] = defaultdict(list)
        students: dict[str, list[TranscriptRow]] = defaultdict(list)
        for row in rows:
            subjects[row.subject or "未分科"].append(row)
            students[row.student_no or row.student_name or "当前学生"].append(row)
        subject_statistics: dict[str, Any] = {}
        for subject, items in subjects.items():
            percentages = [self._percent(item) for item in items]
            subject_statistics[subject] = {
                "average": round(mean(percentages), 1),
                "highest": round(max(percentages), 1),
                "lowest": round(min(percentages), 1),
                "variance": round(pvariance(percentages), 2) if len(percentages) > 1 else 0,
                "standard_deviation": round(math.sqrt(pvariance(percentages)), 2) if len(percentages) > 1 else 0,
                "pass_rate": round(sum(value >= 60 for value in percentages) / len(percentages) * 100, 1),
                "excellent_rate": round(sum(value >= 85 for value in percentages) / len(percentages) * 100, 1),
                "score_bands": {
                    "0-59": sum(value < 60 for value in percentages),
                    "60-72": sum(60 <= value <= 72 for value in percentages),
                    "73-85": sum(73 <= value <= 85 for value in percentages),
                    "86-100": sum(value > 85 for value in percentages),
                },
            }
        student_statistics = []
        for student, items in students.items():
            total = sum(self._percent(item) for item in items)
            student_statistics.append({
                "student_key": student,
                "student_name": items[0].student_name,
                "student_no": items[0].student_no,
                "scores": [{"subject": item.subject or "未分科", "score": round(self._percent(item), 1)} for item in items],
                "total_score": round(total, 1),
                "average_score": round(total / len(items), 1),
            })
        student_statistics.sort(key=lambda item: item["total_score"], reverse=True)
        for index, item in enumerate(student_statistics, start=1):
            item["rank"] = index
            item["rank_band"] = self._rank_band(index, len(student_statistics))
        return {
            "record_count": len(rows),
            "subject_statistics": subject_statistics,
            "students": student_statistics,
            "overall_average": round(mean([self._percent(row) for row in rows]), 1),
            "exam_dates": sorted({row.exam_date for row in rows if row.exam_date}),
        }

    def _profile_agent(self, stats: dict[str, Any]) -> dict[str, Any]:
        subjects = stats["subject_statistics"]
        ordered = sorted(subjects.items(), key=lambda item: item[1]["average"])
        weak = [name for name, _ in ordered[:3]]
        strong = [name for name, _ in reversed(ordered[-3:])] if ordered else []
        average = stats["overall_average"]
        spread = (subjects[strong[0]]["average"] - subjects[weak[0]]["average"]) if strong and weak else 0
        if spread >= 20:
            style = "偏科型"
        elif average < 60:
            style = "基础薄弱型"
        elif average >= 85 and any(item["standard_deviation"] > 12 for item in subjects.values()):
            style = "拔高瓶颈型"
        else:
            style = "粗心失误型"
        return {
            "learning_style": style,
            "strong_subjects": strong,
            "weak_subjects": weak,
            "loss_reason_distribution": self._loss_reasons(stats),
            "evidence": "由科目均分、及格率和分数离散度统计推断；无大题得分时仅供参考。",
        }

    def _weakness_agent(self, stats: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        points = []
        for priority, subject in enumerate(profile["weak_subjects"], start=1):
            subject_stats = stats["subject_statistics"][subject]
            mastery = round(subject_stats["average"], 1)
            points.append({
                "knowledge_point": f"{subject}基础与核心考点",
                "chapter": "章节级诊断（成绩单未提供大题/章节分）",
                "mastery": mastery,
                "loss_contribution": round(100 - mastery, 1),
                "priority": priority,
                "importance_tag": "基础必考点" if mastery < 60 else "高频考点",
                "confidence": 0.62 if not subject_stats else 0.78,
            })
        return {
            "granularity": "chapter" if points else "subject",
            "confidence_note": "仅有科目总分，未提供大题得分，已降级为章节级薄弱点。",
            "weak_points": points,
        }

    def _resource_agent(self, weakness: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        resources = []
        for point in weakness["weak_points"]:
            match = None
            if self.db is not None:
                token = point["knowledge_point"].split("基础")[0]
                match = self.db.query(Resource).filter(Resource.content.like(f"%{token}%")).first()
            resources.append({
                "name": match.title if match and match.title else f"{point['knowledge_point']}核心讲解",
                "knowledge_point": point["knowledge_point"],
                "resource_type": "知识点讲解",
                "difficulty": "基础" if point["mastery"] < 60 else "进阶",
                "minutes": 25 if point["mastery"] < 60 else 35,
                "source": "system_resource" if match else "可由大模型生成",
            })
        plan = [
            {"day": day, "focus": (resources[(day - 1) % len(resources)]["knowledge_point"] if resources else "错题回顾"), "goal": "完成讲解、1组基础题并记录1条错因", "minutes": 30}
            for day in range(1, 8)
        ]
        return {"resources": resources, "seven_day_plan": plan}

    def _exercise_agent(self, weakness: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        items = []
        for point in weakness["weak_points"]:
            kp = point["knowledge_point"]
            items.extend([
                {"tier": "基础巩固", "ratio": 0.6, "question": f"请用自己的话说明{kp}的核心概念，并举一个例子。", "answer": "能说清定义、条件和一个正确例子。", "analysis": "先检查概念边界，再用例子验证。", "knowledge_point": kp, "minutes": 5},
                {"tier": "能力提升", "ratio": 0.3, "question": f"结合一个新情境，判断{kp}的解题步骤并说明理由。", "answer": "步骤完整且理由与条件对应。", "analysis": "关注审题条件与迁移过程。", "knowledge_point": kp, "minutes": 8},
                {"tier": "拓展拔高", "ratio": 0.1, "question": f"设计一道{kp}的变式题，并写出关键突破口。", "answer": "变式改变条件但保留核心规律。", "analysis": "通过变式检验是否真正掌握。", "knowledge_point": kp, "minutes": 12},
            ])
        return {"distribution": {"foundation": 0.6, "improvement": 0.3, "advanced": 0.1}, "items": items, "source": "可由大模型生成"}

    def _report(self, stats: dict[str, Any], profile: dict[str, Any], weakness: dict[str, Any], resources: dict[str, Any], exercises: dict[str, Any], scope: str, quality: str) -> dict[str, Any]:
        weak_text = "、".join(profile["weak_subjects"]) or "暂无明确薄弱科目"
        return {
            "title": "个性化学情分析与学习方案报告",
            "summary": f"本次共分析 {stats['record_count']} 条成绩记录，整体均分 {stats['overall_average']} 分；优先关注 {weak_text}。" + (" 当前数据较少，结论仅供参考。" if quality == "limited" else ""),
            "scope": scope,
            "strengths": [f"{name}均分 {stats['subject_statistics'][name]['average']} 分" for name in profile["strong_subjects"]],
            "weaknesses": [f"{point['knowledge_point']}掌握度 {point['mastery']} 分" for point in weakness["weak_points"]],
            "next_actions": ["按7天学习路径完成基础讲解与巩固题", "每次练习后记录具体失分原因", "下一次成绩单导入后对比趋势"],
            "quality_note": weakness["confidence_note"] if quality == "limited" else "结论基于当前成绩单与系统资源/题库匹配结果。",
        }

    def _loss_reasons(self, stats: dict[str, Any]) -> dict[str, float]:
        deviation = sum(item["standard_deviation"] for item in stats["subject_statistics"].values())
        if deviation > 20:
            return {"计算失误": 35, "审题错误": 30, "概念不清": 20, "知识遗忘": 15}
        if stats["overall_average"] < 60:
            return {"概念不清": 45, "知识遗忘": 30, "审题错误": 15, "计算失误": 10}
        return {"计算失误": 35, "审题错误": 30, "知识遗忘": 20, "概念不清": 15}

    @staticmethod
    def _percent(row: TranscriptRow) -> float:
        return row.score / max(row.max_score, 1) * 100 if row.score is not None else 0

    @staticmethod
    def _rank_band(rank: int, total: int) -> str:
        percentile = rank / max(total, 1)
        return "前10%" if percentile <= 0.1 else "前30%" if percentile <= 0.3 else "中段" if percentile <= 0.7 else "后30%"


def build_report_text(result: dict[str, Any]) -> str:
    report = result["report"]
    lines = [f"# {report['title']}", "", report["summary"], "", "## 学情诊断", f"学习风格：{result['student_profile']['learning_style']}", f"优势科目：{'、'.join(result['student_profile']['strong_subjects']) or '暂无'}", f"薄弱科目：{'、'.join(result['student_profile']['weak_subjects']) or '暂无'}", "", "## 薄弱知识点", *[f"- {item['knowledge_point']}：掌握度 {item['mastery']}，优先级 {item['priority']}" for item in result["weakness_diagnosis"]["weak_points"]], "", "## 7天学习路径", *[f"- 第{item['day']}天：{item['focus']}（{item['minutes']}分钟）" for item in result["resource_recommendations"]["seven_day_plan"]], "", "## 后续建议", *[f"- {item}" for item in report["next_actions"]]]
    return "\n".join(lines)

