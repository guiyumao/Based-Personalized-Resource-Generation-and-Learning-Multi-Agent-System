"""Summarize this execution's evidence, preserving historical unauthorized status."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "artifacts/deepseek-phase-v3-20261019"
LIVE = ROOT / "artifacts/deepseek-authorized-20261019-v1"
OLD = ROOT / "artifacts/deepseek-live-20261019-173354"
OUT = ROOT / "reports/global-testing/deepseek-phase-v3-20261019"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    def write(name, text):
        (OUT / name).write_text(text, encoding="utf-8")

    def dump(name, data):
        write(name, json.dumps(data, ensure_ascii=False, indent=2))

    live = json.loads((LIVE / "LIVE_SUMMARY.json").read_text(encoding="utf-8"))
    requests = [
        json.loads(line) for line in (LIVE / "request-ledger.jsonl").read_text().splitlines()
    ]
    local_e2e = json.loads(
        (LOCAL / "local-e2e-v3/local-e2e-report.json").read_text(encoding="utf-8")
    )
    junit_files = [
        LOCAL / "final-safety/results.xml",
        LOCAL / "provider-v2/results.xml",
        LOCAL / "workers-v2/results.xml",
        LOCAL / "content-knowledge/results.xml",
    ]
    nodes = {}
    groups = []
    for filename in junit_files:
        cases = list(ET.parse(filename).getroot().iter("testcase"))
        passed = failed = skipped = 0
        for case in cases:
            state = (
                "FAIL"
                if case.find("failure") is not None or case.find("error") is not None
                else "NOT_RUN"
                if case.find("skipped") is not None
                else "PASS_MOCK"
            )
            nodes[case.get("classname", "") + "::" + case.get("name", "")] = state
            passed += state == "PASS_MOCK"
            failed += state == "FAIL"
            skipped += state == "NOT_RUN"
        groups.append(
            {
                "file": str(filename.relative_to(ROOT)),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
            }
        )
    inherited = []
    for name in [
        "README.md",
        "DEEPSEEK_LIVE_SUMMARY.md",
        "defect-register.md",
        "test-matrix.csv",
        "environment.json",
        "source-manifest.json",
        "request-ledger.jsonl",
        "command-log.jsonl",
        "evidence/incident-unauthorized-live.md",
        "evidence/live-gate.log",
        "evidence/task-chain.log",
    ]:
        path = OLD / name
        inherited.append(
            {
                "path": str(path.relative_to(ROOT)),
                "exists": path.exists(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
            }
        )
    dump("inherited-evidence.json", inherited)
    changed = [
        "common/config.py",
        "tests/conftest.py",
        "scripts/run_no_cost_tests.py",
        "scripts/no_cost_runtime/guard.py",
        "scripts/no_cost_runtime/sitecustomize.py",
        "scripts/no_cost_mock_provider.py",
        "scripts/verify_no_cost_e2e.py",
        "scripts/verify_authorized_deepseek.py",
        "scripts/verify_live_business.py",
        "scripts/report_deepseek_phase_v3.py",
        "tests/integration/test_no_cost_isolation.py",
        "tests/integration/test_authorized_gateway_budget.py",
        "tests/integration/test_deepseek_failure_semantics.py",
        "tests/e2e/run-no-cost.mjs",
        "tests/e2e/run-live-authorized.mjs",
        "docs/testing/deepseek-live-test-prompt.md",
    ]
    dump(
        "source-manifest.json",
        [
            {"path": path, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
            for path in changed
        ],
    )
    # Diff only files touched this phase, preserving all earlier dirty changes.
    diff = subprocess.run(
        ["git", "diff", "--", *changed],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    write("tracked-changes.diff", diff.stdout)
    dump(
        "execution-summary.json",
        {
            "groups": groups,
            "unique_test_nodes": len(nodes),
            "live": live,
            "live_prompt_tokens": sum(
                (r.get("usage") or {}).get("prompt_tokens", 0) for r in requests
            ),
            "live_output_tokens": sum(
                (r.get("usage") or {}).get("completion_tokens", 0) for r in requests
            ),
            "local_browser": local_e2e.get("browser"),
            "note": "Local/mock, live-authorized and historical unauthorized evidence are separate.",
        },
    )

    write(
        "INC01_INCIDENT_REVIEW.md",
        "# INC-01复盘\n\n历史事故不关闭、不删除：PowerShell空赋值移除了环境变量，项目dotenv回退加载开发密钥；普通live标志被误当成执行授权。历史至少4次真实生成、6个测试成功仍标PASS_UNAUTHORIZED，不计本轮正式通过。\n\n本轮没有读取开发.env或原密钥。git check-ignore确认.env被忽略，git ls-files及按.env路径的git log未发现该路径被跟踪/提交；这不能证明其他路径或旧日志从未泄露。子服务仅接收随机本地网关令牌，真实密钥由getpass无回显输入，只保留在受控网关进程内存，未写环境、配置、命令行或报告。用户在对话中提供了密钥，建议撤销换新，不擅自轮换。\n\n普通pytest与子进程隔离已加强；这不是对任意恶意Python/native代码的OS级沙箱。原始证据SHA256见inherited-evidence.json。后续用户明确授权的真实调用单独记录，不能倒推为INC-01已获授权。",
    )
    write(
        "INC01_BILLING_RECONCILIATION.md",
        "# INC-01账单核对\n\n历史事件窗口：2026-10-19 22:21:37–22:22:26 Asia/Shanghai，对应14:21:37–14:22:26 UTC。建议查询前后15分钟：22:06:37–22:37:26本地／14:06:37–14:37:26 UTC，按供应商结算粒度和延迟调整。\n\n已知下界至少4次生成，请求模型deepseek-chat；旧事件响应模型、请求ID、usage和金额均UNKNOWN。不能以本轮已知usage估算或回填旧事件。请从控制台核对时间/密钥标识/请求ID/请求及响应模型/成功失败/输入输出及缓存Token/金额/币种，离线匹配旧日志时间和ledger；没有授权访问账单，本轮未登录控制台。\n\n本轮新授权调用的ID与usage在artifacts/deepseek-authorized-20261019-v1/request-ledger.jsonl；金额仍未知，需独立对账。",
    )
    write(
        "ZERO_COST_TEST_ISOLATION_REPORT.md",
        "# 无费用隔离\n\n已实施：common.config支持关闭dotenv；普通tests/conftest在项目导入前自动bootstrap隔离；专用运行器采用宿主环境白名单、新SQLite/目录/JWT、空Provider基址和测试哨兵；第三方dotenv返回空值，直接读取.env被拒。\n\nHTTPX同步/异步URL检查+socket DNS/connect/sendto审计，只允许显式端口或当前受控Python实际创建的loopback监听器；代理变量移除且NO_PROXY=*。Python子进程必须继承guard环境，Windows另加Popen验证。sitecustomize安装异常以78退出，不能吞异常后继续执行。两个live标志、缓存重载、fake-IP、未声明本机代理、Worker导入、重试与缺失guard子进程均已测试。\n\nfinal-safety为16 passed，普通直接pytest另有13 passed。第一轮暴露Windows子进程校验和Chroma自读.env问题，失败保留，修复后复验通过。Node/浏览器通过精确本机origin路由限制、无真实Provider密钥及Vite独立envDir保护，不声称已建立OS防火墙。真实授权入口是独立父网关，子业务仍只能连接本机。",
    )
    chains = []
    for path in (ROOT / "services").rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(
                r"build_chat_model\(|build_for_task\(|reserve_usage\(|search_sources\(|fetch_source\(",
                line,
            ):
                chains.append(
                    {"file": str(path.relative_to(ROOT)), "line": index, "call": line.strip()}
                )
    dump("call-sites.json", chains)
    write(
        "DEEPSEEK_CALL_CHAIN_AUDIT.md",
        "# 模型调用链\n\ncall-sites.json枚举当前模型工厂、Search/Fetch及预算调用位置。QA、聊天、课件、练习、结构化资源、路径、画像、报告、协调器及Worker均有独立入口，不能只检查一个API。知识规划/综合与Search/Fetch有knowledge_budget预留；普通聊天/资源/评价和图谱不自动享受该保护。同步/后台及重试边界见既有source-audit和Worker实现，本轮未修改生产调用链。\n\n图谱依赖实际为POST /graph/dependencies；匿名模型调用及个人资源元数据泄露仍是前轮确认的OPEN业务问题，补丁在global-audit-resume-20261019/patches，未因真实调用授权而自动应用。",
    )
    write(
        "MODEL_COST_CONTROL_AUDIT.md",
        "# 成本控制\n\n用户随后明确授权Chat≤30次、Search/Fetch合计≤6次、总输出≤60000 Token。独立网关在每次出站前加锁预留计数和输出上限；SDK/业务重试也必须经过同一网关，固定上游api.deepseek.com与请求模型deepseek-chat。响应usage缺失或在途状态不明确时保守计入全部预留，金额不记零。\n\n本轮实际5 Chat+1 Search，输出3506 Token，均在限额内。网关测试覆盖30次、第31次阻断、Search/Fetch六次、第七次阻断、输出预留超限先阻断及日志不含测试密钥。专用运行器是测试治理，未补齐生产全业务预算、跨网关持久预算或账单回填。已发远程请求无法承诺立即停止计费。",
    )
    write(
        "PROVIDER_RELIABILITY_REPORT.md",
        "# Provider可靠性\n\nprovider-v2：34 passed，涵盖本地真实HTTP客户端正常JSON、非JSON、空响应、非法JSON、缺choices、429/500/502/503、连接失败、断连、SSE中断及实际3秒钳制；包含计数网关、Search/Fetch和文档契约回归。Worker组合67 passed，包含真实进程终止与执行权围栏。\n\n真实授权调用5个Chat均HTTP200；请求deepseek-chat，响应deepseek-flash。没有故意用真实服务制造429、断网或超时，因此故障场景仍仅PASS_MOCK。普通SDKmax_retries=0不等于业务层不会追加调用，全部按实际ledger统计。",
    )
    samples = []
    for name, kind in [
        ("live-courseware.md", "courseware"),
        ("live-exercise-result.json", "exercise"),
        ("live-qa-response.json", "qa"),
    ]:
        path = LIVE / name
        if path.exists():
            samples.append(
                {
                    "subject": "计算机网络",
                    "knowledge_point": "TCP",
                    "type": kind,
                    "source": "LIVE_AUTHORIZED_VIA_LOCAL_GATEWAY",
                    "content_file": str(path.relative_to(ROOT)),
                    "fact_accuracy_review": None,
                    "teaching_suitability_review": None,
                    "human_score": None,
                }
            )
    dump("human-review-samples.json", samples)
    write(
        "AI_CONTENT_QUALITY_AUDIT.md",
        "# 内容与fallback\n\n真实课件3619字符、3道题及QA样本留存，人工评审字段在human-review-samples.json，未做专家准确性验收。真实exercise结果未出现deterministic_fallback；本地结构化/持久化/审核/资源/知识/成绩测试52 passed。\n\n生产练习失败仍可能返回规则fallback且audit_status=passed，该业务语义未改，D-06继续OPEN。通过Schema不等于知识正确；audit unavailable不计审核通过；usage估算不计真实供应商账单。INC-01样本未转为正式live通过。",
    )
    write(
        "LOCAL_END_TO_END_TEST_REPORT.md",
        "# 本地与真实链路分开验收\n\n本地模拟阶段：六服务、独立Worker、隔离SQLite、Vite和真实Chromium；QA登录/提问/刷新读回、课件任务/幂等重放/展示/DOCX、3题非fallback任务、CSV上传解析/分析均通过，browser-report无pageErrors。证据local-e2e-v3，外部模型明确LOCAL_MOCK。\n\n用户随后要求真实调用并确认预算：真实课件/3题Worker任务、幂等重放、DOCX导出、浏览器登录/真实QA/刷新读回/资源列表均通过，证据deepseek-authorized-20261019-v1。应用经本地记录网关访问真实官方API，不能称应用官方直连。\n\n知识候选审核/发布/版本逻辑在隔离单元测试通过，但本轮没有全新真实Chroma发布→检索的浏览器闭环。取消/超时/崩溃由故障与Worker测试覆盖，没有在本轮收费请求上重复注入。",
    )
    write(
        "SEARCH_FETCH_CONTRACT_AND_SECURITY_REPORT.md",
        "# Search/Fetch\n\nDEEPSEEK_SEARCH_BASE独立于Chat基址；默认源码路径为/v1/tools/search和/v1/tools/fetch。每次出站尝试前预留，408/429/5xx/超时按现有两次尝试处理；公网URL及解析地址限制保留。本地MockTransport校验官方默认URL、网关覆盖、重试/超时及SSRF。\n\n本轮真实Search HTTP200并取得IETF RFC5681等来源，实际1次。Fetch在项目URL/公网校验处ValueError: Invalid source URL，无真实Fetch出站，记录BLOCKED而非PASS。受控子进程禁止外部DNS以及原环境fake-IP均不能通过放宽SSRF解决。\n\n本轮只读官方文档访问失败/超时，逐字段当前官方契约仍CONTRACT_UNVERIFIED；Search实际响应成功仅证明当前已用字段可工作，不证明全契约或Fetch可用。",
    )
    defects = (OLD / "defect-register.md").read_text(encoding="utf-8")
    defect_lines = [line for line in defects.splitlines() if re.match(r"\| D-\d+", line)]
    updates = {
        "D-05": "测试网关覆盖本轮；生产统一预算仍OPEN",
        "D-06": "真实本轮非fallback通过；生产fallback语义仍OPEN",
        "D-10": "Fetch仍BLOCKED，未绕过SSRF",
        "D-12": "官方文档当前逐字段核对仍UNVERIFIED",
        "D-13": "测试默认dotenv/网络/子进程独立防护已实施并回归",
        "D-16": "新授权Chat获得usage；生产估算逻辑未改",
        "D-18": "新授权网关记录请求/响应模型、ID、usage；客户端全局标记未改",
        "D-19": "INC-01账单仍UNKNOWN；后续新授权调用独立记录",
    }
    write(
        "DEFECT_FIX_PLAN_AND_REGRESSION.md",
        "# 19项问题与修复\n\n原始19条不删除、不都视为代码缺陷：文档、测试、事故、环境和生产风险分列。\n\n"
        + "\n".join(defect_lines)
        + "\n\n## 本轮状态更新\n\n"
        + "\n".join(f"- {key}：{value}" for key, value in updates.items())
        + "\n\n已实施只涉及测试隔离、运行工具、配置关闭dotenv开关与文档。图谱权限/成本、迁移、生产fallback及知识业务规则未修改；依据用户附件第10.2节保留待决补丁。撤回本轮具体增量即可回滚测试工具，不回滚其他未提交改动；新证据与INC-01应保留。",
    )
    old_rows = list(csv.DictReader((OLD / "test-matrix.csv").open(encoding="utf-8-sig")))
    mapping = {
        "DS-01": "smoke",
        "DS-05": "courseware",
        "DS-06": "exercise",
        "DS-09": "qa",
        "DS-20": "search",
    }
    rows = []
    lookup = {r["id"]: r for r in old_rows}
    for number in range(1, 31):
        identity = f"DS-{number:02}"
        old = lookup.get(identity, {})
        state = old.get("status", "NOT_RUN")
        notes = old.get("notes", "原矩阵未找到定义，不能补造通过")
        evidence = str((OLD / "test-matrix.csv").relative_to(ROOT))
        if identity in mapping:
            state = "PASS_LIVE_AUTHORIZED"
            notes = "本轮授权范围已执行；" + mapping[identity] + "，不代表整模块所有子场景通过"
            evidence = str((LIVE / "request-ledger.jsonl").relative_to(ROOT))
        elif identity in {"DS-21", "DS-22"}:
            state = "BLOCKED"
            notes = "Fetch未通过安全校验；未执行完整来源发布链"
        elif identity in {"DS-23", "DS-24", "DS-25", "DS-26", "DS-27", "DS-28", "DS-29"}:
            state = "PASS_MOCK"
            notes = "本地受控/Worker证据；不声称真实远端取消、计费或故障语义通过"
            evidence = str(LOCAL.relative_to(ROOT))
        rows.append(
            {
                "id": identity,
                "status": state,
                "historical_status": old.get("status", "NOT_RUN"),
                "evidence": evidence,
                "notes": notes,
            }
        )
    with (OUT / "DEEPSEEK_V3_TEST_MATRIX.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["id", "status", "historical_status", "evidence", "notes"]
        )
        writer.writeheader()
        writer.writerows(rows)
    summary = f"""# DeepSeek集成安全与全链路测试V3验收报告

生成：{datetime.now(UTC).isoformat()}（UTC）。本轮先按无费用约束实施隔离，随后用户明确要求真实调用并授权Chat≤30、Search/Fetch≤6、总输出≤60000。

## 已完成

- 测试默认安全：普通pytest导入前隔离；dotenv、第三方dotenv、凭证继承、HTTP/Socket、Python子进程均有防护。误开两个live标志仍不能出网。
- 最终安全/预算16 passed，Provider34 passed，Worker67 passed，内容/知识/成绩52 passed；合计169次，通过节点去重{len(nodes)}。模拟与真实结果分列，旧INC-01通过数不累加。
- 真实浏览器本地模拟链路通过；后续真实DeepSeek课件3619字符、3道题非fallback、Worker持久化/重放、DOCX、浏览器QA刷新读回及课件列表通过。
- 真实请求：5 Chat+1 Search，输入{sum((r.get("usage") or {}).get("prompt_tokens", 0) for r in requests)} Token、输出3506 Token。全部HTTP200。请求模型deepseek-chat，响应模型deepseek-flash；经本地记录网关访问api.deepseek.com，不是应用直连证明。金额UNKNOWN。
- 真正的Fetch请求0次：现有安全检查阻断，仍BLOCKED。没有放宽SSRF。

## 验收边界

核心Chat/课件/练习/Search授权实测已通过所列场景；不能宣布DS-01至DS-30全绿，也不能宣布全站上线验收通过。结构化三类资源仍保留历史PASS_UNAUTHORIZED，没有借本轮授权追认旧事故。知识真实发布/检索、全站全部权限与浏览器、专家内容质量均未完整验收。

## 仍需处理

INC-01发生于dotenv回退+测试授权门不足，账单仍UNKNOWN；新授权事件独立保存。Python防护不覆盖任意恶意native代码或OS层网络；未来付费只能使用专用受控入口。生产统一成本控制、图谱匿名付费及个人草稿泄露、SQLite历史降级、fallback语义均未获本轮生产修改授权，补丁/方案保留，公网部署仍No-Go。

## 交付与下一步

本目录12份报告、DS矩阵、来源指纹、人审样本和历史证据清单；原始日志在artifacts/deepseek-phase-v3-20261019，真实ledger及产物在artifacts/deepseek-authorized-20261019-v1。真实密钥仅getpass读入内存，子API只有本地网关随机令牌。无需再提供相同密钥；若要修复生产风险，最少还需明确批准具体补丁范围；若要继续Fetch，需提供不弱化SSRF的正常公网DNS/受控执行环境。账单核对需脱敏控制台导出。
"""
    write("DEEPSEEK_V3_GLOBAL_SUMMARY.md", summary)
    print(
        json.dumps(
            {
                "reports": str(OUT),
                "groups": groups,
                "unique_nodes": len(nodes),
                "live_chat": live["chat_attempts"],
                "live_tools": live["search_fetch_attempts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
