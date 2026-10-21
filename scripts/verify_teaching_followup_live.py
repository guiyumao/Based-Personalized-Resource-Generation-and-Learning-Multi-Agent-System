"""Read existing own courseware on current 5175; no generation or model calls."""
import json,subprocess,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common.security.auth import create_access_token
root=Path("artifacts/teaching-no-flowchart-20261021/current-browser")
root.mkdir(parents=True,exist_ok=False)
def count():
 with sqlite3.connect("artifacts/local-start-20261019/runtime.sqlite") as db:
  return {"model_calls":db.execute("select count(*) from model_calls").fetchone()[0],"answers":db.execute("select count(*) from answer_records").fetchone()[0]}
before=count()
result=subprocess.run(["node","tests/e2e/run-teaching-followup-live.mjs",str(root)],input=json.dumps({"token":create_access_token("6")}),text=True,capture_output=True,timeout=180)
# The temporary owner token is transferred via stdin only, never logged or persisted.
after=count()
(root/"runtime-counts.json").write_text(json.dumps({"before":before,"after":after,"same":before==after}),encoding="utf-8")
print(json.dumps({"exit_code":result.returncode,"counts_unchanged":before==after,"result_path":str(root/"result.json")}))
if result.returncode:
 print(result.stderr[-3000:])
raise SystemExit(result.returncode)
