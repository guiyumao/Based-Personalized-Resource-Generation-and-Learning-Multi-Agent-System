"""Run Python tests/tools without developer dotenv, paid credentials or remote sockets.

Example: python scripts/run_no_cost_tests.py --run-root artifacts/no-cost-run -- -m pytest tests/unit -q
Only the named local ports and listeners created in guarded Python processes
are reachable. Python children inherit the guard; this is not an OS firewall.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/no_cost_runtime"


def isolated_environment(run_root: Path, ports: list[int] | None = None) -> dict[str, str]:
    run_root = run_root.resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    # Allowlist host essentials instead of inheriting every secret/proxy setting.
    essentials = {
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATH",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "HOMEDRIVE",
        "HOMEPATH",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in essentials}
    env.update(
        NO_COST_TEST="1",
        APP_LOAD_DOTENV="false",
        NO_COST_ALLOWED_PORTS=",".join(map(str, ports or [])),
        NO_COST_NETWORK_LEDGER=str(run_root / "network-ledger.jsonl"),
        PYTHONPATH=str(GUARD) + os.pathsep + str(ROOT),
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        DATABASE_URL="sqlite+pysqlite:///" + (run_root / "runtime.sqlite").as_posix(),
        JWT_SECRET_KEY=secrets.token_urlsafe(40),
        JWT_ALGORITHM="HS256",
        ENVIRONMENT="test",
        DEBUG="false",
        KNOWLEDGE_RUNTIME_ROOT=str(run_root),
        CHROMA_PERSIST_DIRECTORY=str(run_root / "chroma"),
        CHROMA_MODE="persistent",
        AI_PERFORMANCE_LOG_PATH=str(run_root / "ai-performance.jsonl"),
        RUN_LIVE_LLM="0",
        DEEPSEEK_LIVE_PAID_ACK="0",
        RUN_EXTERNAL_SERVICES="0",
        LLM_PREWARM_ENABLED="false",
        NEO4J_ENABLED="false",
        GRAPH_LLM_ENRICH_ENABLED="false",
        DEFAULT_ADMIN_USERNAME="",
        DEFAULT_ADMIN_PASSWORD="",
        DEFAULT_ADMIN_EMAIL="",
        DEEPSEEK_API_KEY="",
        OPENAI_API_KEY="",
        QWEN_API_KEY="",
        DEEPSEEK_API_BASE="",
        OPENAI_BASE_URL="",
        QWEN_API_BASE="",
        DEEPSEEK_SEARCH_BASE="",
        NO_PROXY="*",
    )
    return env


def bootstrap_pytest() -> None:
    """Make direct pytest invocations safe before shared fixtures import config.

    Paid runs intentionally need a separate, reviewed execution mechanism; two
    inherited live flags do not opt this normal test suite into paid traffic.
    """
    if os.environ.get("NO_COST_GUARD_ACTIVE") == "1":
        return
    import tempfile

    run_root = Path(tempfile.mkdtemp(prefix="learning-no-cost-"))
    environment = isolated_environment(run_root)
    os.environ.clear()
    os.environ.update(environment)
    sys.path.insert(0, str(GUARD))
    from guard import install

    install()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--allow-port", type=int, action="append", default=[])
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("provide Python arguments after --")
    if any(flag in command[:1] for flag in ("-S", "-I", "-E")):
        parser.error("interpreter flags disabling the startup guard are forbidden")
    if any(not 1 <= port <= 65535 for port in args.allow_port) or args.timeout < 1:
        parser.error("invalid port or timeout")
    directory = args.run_root.resolve()
    env = isolated_environment(directory, args.allow_port)
    # New evidence only: do not overwrite a previous invocation's log.
    log = directory / "command.log"
    started = datetime.now(UTC).isoformat()
    before = time.monotonic()
    with log.open("x", encoding="utf-8") as stream:
        process = subprocess.Popen(
            [sys.executable, *command], cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT
        )
        try:
            code = process.wait(timeout=args.timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=15,
                )
            else:
                process.kill()
            code = process.wait(timeout=10)
    manifest = dict(
        started=started,
        seconds=round(time.monotonic() - before, 3),
        pid=process.pid,
        exit_code=code,
        timeout=timed_out,
        python=sys.executable,
        command=command,
        allowed_ports=args.allow_port,
        dotenv=False,
        real_provider_credentials=False,
        log=str(log),
    )
    (directory / "command.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 124 if timed_out else code


if __name__ == "__main__":
    raise SystemExit(main())
