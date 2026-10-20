"""This task's explicit authorization: <=6 Chat, <=6000 reserved output, zero tools."""
import argparse
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--authorized-six-chat-6000-output",action="store_true")
    parser.add_argument("--run-root",required=True,type=Path)
    parser.add_argument("--resume-from",type=Path)
    parser.add_argument("--output-per-call",type=int,choices=[1000,2000],default=1000)
    args=parser.parse_args()
    if not args.authorized_six_chat_6000_output or os.getenv("NO_COST_TEST")=="1":
        parser.error("Explicit authorization and separate parent runtime required")
    root=args.run_root.resolve()
    root.mkdir(parents=True,exist_ok=False)
    prior_calls=prior_output=prior_known=0
    if args.resume_from:
        previous=json.loads((args.resume_from/"LIVE_SUMMARY.json").read_text(encoding="utf-8"))
        prior_calls=previous["actual_chat_attempts"]
        prior_output=previous["output_reservation"]
        prior_known=previous["known_output_tokens"]
    from common.config import get_settings
    from scripts.run_no_cost_tests import isolated_environment
    key=get_settings().deepseek_api_key
    if not key:
        raise RuntimeError("DeepSeek credential is not configured")
    local_token=secrets.token_urlsafe(32)
    lock=threading.Lock()
    requests=[]
    class Gateway(BaseHTTPRequestHandler):
        def log_message(self,*_):
            pass
        def do_POST(self):
            if self.path!="/v1/chat/completions" or self.headers.get("Authorization")!="Bearer "+local_token:
                self.reply(403,b'{"error":{"message":"outside authorized scope"}}')
                return
            body=json.loads(self.rfile.read(min(200000,int(self.headers.get("Content-Length","0")))))
            with lock:
                if prior_calls+len(requests)>=6 or prior_output+(len(requests)+1)*args.output_per_call>6000:
                    self.reply(429,b'{"error":{"message":"authorized call limit exhausted"}}')
                    return
                # Reserve 1000 for every request, including ambiguous failures.
                row={"attempt":prior_calls+len(requests)+1,"path":self.path,"model":"deepseek-chat","reserved_output":args.output_per_call,"status":"STARTED"}
                requests.append(row)
                with (root/"gateway-ledger.jsonl").open("a",encoding="utf-8") as stream:
                    stream.write(json.dumps(row)+"\n")
            body.update(model="deepseek-chat",max_tokens=args.output_per_call,stream=False)
            body.pop("max_completion_tokens",None)
            request=urllib.request.Request("https://api.deepseek.com/v1/chat/completions",data=json.dumps(body).encode(),
                headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
            try:
                with urllib.request.urlopen(request,timeout=90) as response:
                    status,payload=response.status,response.read(2*1024*1024)
                data=json.loads(payload)
                row.update(status=status,response_model=data.get("model"),usage=data.get("usage"))
            except urllib.error.HTTPError as exc:
                status,payload=exc.code,exc.read(10000)
                row.update(status=status)
            except Exception as exc:
                status,payload=502,b'{"error":{"message":"upstream transport failed"}}'
                row.update(status=status,error_type=type(exc).__name__)
            with lock:
                with (root/"gateway-ledger.jsonl").open("a",encoding="utf-8") as stream:
                    stream.write(json.dumps(row)+"\n")
            self.reply(status,payload)
        def reply(self,status,payload):
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    server=ThreadingHTTPServer(("127.0.0.1",0),Gateway)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    env=isolated_environment(root/"business",[server.server_port])
    if args.resume_from:
        source=sqlite3.connect(f"file:{(args.resume_from/'business/runtime.sqlite').resolve().as_posix()}?mode=ro",uri=True)
        destination=sqlite3.connect(root/'business/runtime.sqlite')
        source.backup(destination)
        source.close();destination.close()
    env.update(DEEPSEEK_API_KEY=local_token,NO_COST_LOCAL_API_TOKEN=local_token,DEEPSEEK_API_BASE=f"http://127.0.0.1:{server.server_port}/v1",DEEPSEEK_MODEL="deepseek-chat",
        MODEL_USAGE_MODE="LIVE",AI_PROVIDER_DAY_CALL_LIMIT="6",AI_PROVIDER_DAY_OUTPUT_RESERVATION="6000",AI_PROVIDER_MAX_OUTPUT_TOKENS=str(args.output_per_call),
        MAX_TOTAL_RETRIES="0",RESOURCE_COURSEWARE_VARIANT_COUNT="1",LLM_LIGHT_MODEL="",LIVE_OUTPUT=str(root))
    try:
        with (root/"business.log").open("w",encoding="utf-8") as log:
            result=subprocess.run([sys.executable,"tests/e2e/live_operations_business.py"],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=420)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
        key=""
        summary={"authorized_chat":6,"authorized_output":6000,"actual_chat_attempts":prior_calls+len(requests),"output_reservation":prior_output+len(requests)*args.output_per_call,
            "known_output_tokens":prior_known+sum(int((row.get("usage") or {}).get("completion_tokens",0)) for row in requests),
            "prior_authorization_attempts":prior_calls,
            "search_fetch_calls":0,"source":"LIVE_AUTHORIZED_VIA_LOCAL_GATEWAY","requests":requests,"billing_verified":False}
        summary["business_exit_code"]=result.returncode if "result" in locals() else None
        summary["passed"]=summary["business_exit_code"]==0
        (root/"LIVE_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({key:summary[key] for key in ("passed","actual_chat_attempts","known_output_tokens","search_fetch_calls","business_exit_code")}))


if __name__=="__main__":
    main()
