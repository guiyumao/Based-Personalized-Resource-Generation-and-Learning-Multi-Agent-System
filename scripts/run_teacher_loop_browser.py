"""Run real cross-role UI acceptance and restart the isolated API mid-workflow."""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_no_cost_tests import isolated_environment

root = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/teacher-loop-browser").resolve()
root.mkdir(parents=True, exist_ok=False)
env = isolated_environment(root, [18226])
env.update(JWT_SECRET_KEY="teacher-loop-isolated-test", CORS_ALLOW_ORIGINS="http://127.0.0.1:15196")
if "--files" in sys.argv:
    import io
    from PIL import Image, ImageDraw
    from docx import Document
    from pypdf import PdfWriter

    fixtures = root / "fixtures"
    fixtures.mkdir()
    image = Image.new("RGB", (320, 160), "white")
    ImageDraw.Draw(image).text((30, 60), "x = 2, verified", fill="black")
    image.save(fixtures / "手写解答.png")
    document = Document()
    document.add_paragraph("作业原文：SQL事务分析与证明。")
    document.save(fixtures / "作业文档.docx")
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    with (fixtures / "推导.pdf").open("wb") as stream:
        writer.write(stream)
children, handles = [], []


def start(command, environ, cwd, log):
    handle = (root / log).open("w", encoding="utf-8")
    handles.append(handle)
    p = subprocess.Popen(command, env=environ, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT)
    children.append(p)
    return p


def ready(url, process):
    for _ in range(160):
        if process.poll() is not None:
            raise RuntimeError("Service exited: " + url)
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("Service unavailable: " + url)


def api(log):
    p = start(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "teacher_loop_server:app",
            "--app-dir",
            "tests/e2e",
            "--host",
            "127.0.0.1",
            "--port",
            "18226",
            "--lifespan",
            "off",
        ],
        env,
        None,
        log,
    )
    ready("http://127.0.0.1:18226/teacher-api/health", p)
    return p


try:
    backend = api("api.log")
    front = {**os.environ, "VITE_SAKURAFRP_SAME_ORIGIN": "false"}
    for name, service in [
        ("USER", "user"),
        ("TEACHER", "teacher"),
        ("AGENT", "agent"),
        ("RESOURCE", "agent"),
        ("EVALUATION", "evaluation"),
        ("SYSTEM", "teacher"),
    ]:
        front[f"VITE_{name}_API_BASE_URL"] = f"http://127.0.0.1:18226/{service}-api"
    p = start(
        [
            "node",
            "node_modules/vite/bin/vite.js",
            "--host",
            "127.0.0.1",
            "--port",
            "15196",
            "--strictPort",
        ],
        front,
        "web-app",
        "vite.log",
    )
    ready("http://127.0.0.1:15196", p)
    browser = start(
        ["node", "tests/e2e/run-teacher-loop.mjs", str(root), *sys.argv[2:]],
        os.environ.copy(),
        None,
        "browser.log",
    )
    restarted = False
    deadline = time.monotonic() + 240
    while browser.poll() is None:
        if time.monotonic() > deadline:
            raise RuntimeError("Browser timed out")
        if (root / "restart-request").exists() and not restarted:
            backend.terminate()
            backend.wait(timeout=15)
            backend = api("api-restarted.log")
            (root / "restart-complete").write_text("ok", encoding="utf-8")
            restarted = True
        time.sleep(0.3)
    print((root / "browser.log").read_text(encoding="utf-8"))
    if browser.returncode:
        raise RuntimeError("Browser failed")
    # Verify cross-role foreign keys and persisted score directly, then clean only this disposable DB.
    import sqlite3

    db_path = env["DATABASE_URL"].split("///", 1)[1]
    assert Path(db_path).resolve().is_relative_to(root), (
        "Cleanup must stay in the isolated run directory"
    )
    with sqlite3.connect(db_path) as db:
        evidence = db.execute(
            "SELECT c.id,c.teacher_user_id,e.student_user_id,a.id,s.id,s.student_user_id,s.score,s.teacher_comment,s.status FROM classrooms c JOIN class_enrollments e ON e.class_id=c.id JOIN assignments a ON a.class_id=c.id JOIN assignment_submissions s ON s.assignment_id=a.id"
        ).fetchall()
        assert evidence and evidence[0][2] == evidence[0][5] and evidence[0][6] == 94
        (root / "sql-evidence.json").write_text(
            json.dumps(
                {
                    "relations": evidence,
                    "restarted": restarted,
                    "model_calls": db.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0],
                }
            ),
            encoding="utf-8",
        )
        assert db.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 0
        for (key,) in db.execute("SELECT storage_key FROM homework_attachments").fetchall():
            target = (Path(db_path).parent / "homework-files" / key).resolve()
            assert target.is_relative_to(root)
            target.unlink(missing_ok=True)
        db.execute("PRAGMA foreign_keys=OFF")
        tables = [
            x[0]
            for x in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            db.execute('DELETE FROM "' + table.replace('"', '""') + '"')
        db.commit()
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        (root / "cleanup.json").write_text(
            json.dumps(
                {
                    "remaining_test_users": 0,
                    "remaining_test_classes": db.execute(
                        "SELECT COUNT(*) FROM classrooms"
                    ).fetchone()[0],
                    "shared_database_touched": False,
                }
            ),
            encoding="utf-8",
        )
finally:
    for p in reversed(children):
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    for handle in handles:
        handle.close()
