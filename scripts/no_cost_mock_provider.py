"""Deterministic local Chat/Search/Fetch simulator, never an upstream proxy."""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ANSWER = "本地模拟验收标记 NC-QA-001：TCP 使用序号、确认和超时重传保证可靠传输。接收方按序交付数据；发送方在未收到确认时重传。此内容来自本地测试服务，不能用于真实模型质量验收。"
COURSEWARE = "# TCP 可靠传输：本地模拟课件\n\n" + "\n\n".join(
    f"## {heading}\n本地模拟内容 NC-RESOURCE-001。TCP 利用序号、确认和重传机制处理丢失数据。课堂案例 XZ-TCP-042：发送41、42、43段，42丢失后重传，接收方按序交付。学习时先观察报文序号，再判断确认与重传行为。本次未读取历史画像，不能推断学习者掌握程度。"
    for heading in [
        "课程导入",
        "学习目标",
        "你的当前学习情况",
        "知识讲解",
        "重点难点突破",
        "示例讲解",
        "课堂小结",
        "学完后自测",
        "拓展延伸",
    ]
)


def content_for(messages: list[dict]) -> str:
    text = "\n".join(str(item.get("content", "")) for item in messages)
    if '"verdict"' in text or '"verdict":' in text or "verdict" in text and "PASS" in text:
        return json.dumps({"verdict": "PASS", "reason": "local mock structural fixture"})
    if "题目数量：" in text:
        match = re.search(r"题目数量：(\d+)", text)
        count = int(match.group(1)) if match else 3
        return json.dumps(
            {
                "summary": "本地模拟TCP练习",
                "exercises": [
                    {
                        "exercise_id": index + 1,
                        "knowledge_point": "TCP",
                        "question_type": "choice",
                        "difficulty": "foundation",
                        "prompt": f"第{index + 1}题：在课堂数据段案例中，TCP丢失数据后采用什么机制恢复？",
                        "options": ["A. 超时重传", "B. 永久丢弃", "C. 关闭确认", "D. 无序交付"],
                        "answer": "A",
                        "analysis": "TCP发送方利用确认与超时检测丢失的数据段并重新发送，接收方按序交付；其他选项不能保证可靠传输。",
                    }
                    for index in range(count)
                ],
            },
            ensure_ascii=False,
        )
    if "真正可学习的 Markdown 课件" in text:
        return COURSEWARE
    if "study_suggestions" in text and '"answer"' in text:
        return json.dumps(
            {
                "answer": ANSWER,
                "study_suggestions": ["画出序号与确认的对应关系", "比较丢包前后的报文顺序"],
            },
            ensure_ascii=False,
        )
    if "思维导图" in text and "root_id" in text:
        return json.dumps(
            {
                "title": "TCP思维导图",
                "knowledge_point": "TCP",
                "root_id": "root",
                "nodes": [
                    {"id": "root", "label": "TCP", "parent_id": None, "level": 0, "detail": "核心"},
                    {
                        "id": "n1",
                        "label": "确认与重传",
                        "parent_id": "root",
                        "level": 1,
                        "detail": "可靠传输",
                    },
                ],
                "edges": [{"source": "root", "target": "n1", "label": "机制"}],
                "mermaid_source": "",
            },
            ensure_ascii=False,
        )
    if "prereqs" in text:
        return '{"prereqs":[],"recs":[]}'
    return ANSWER


class MockProvider:
    def __init__(self, ledger: Path):
        self.ledger = ledger
        self.lock = threading.Lock()
        self.calls = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                messages = body.get("messages", [])
                with owner.lock:
                    owner.calls += 1
                    with ledger.open("a", encoding="utf-8") as stream:
                        stream.write(
                            json.dumps(
                                {
                                    "attempt": owner.calls,
                                    "time": time.time(),
                                    "path": self.path,
                                    "stream": bool(body.get("stream")),
                                    "message_count": len(messages),
                                    "source": "local_mock",
                                    "authorization_present": bool(
                                        self.headers.get("Authorization")
                                    ),
                                }
                            )
                            + "\n"
                        )
                if self.path.endswith("/tools/search"):
                    result = {
                        "results": [
                            {
                                "title": "Local TCP fixture",
                                "url": "https://example.edu/tcp",
                                "snippet": "Local source fixture",
                            }
                        ]
                    }
                elif self.path.endswith("/tools/fetch"):
                    result = {
                        "title": "Local TCP fixture",
                        "content": "# TCP\nLocal mock source evidence.",
                    }
                else:
                    content = content_for(messages)
                    if body.get("stream"):
                        chunks = []
                        for index in range(0, len(content), 10):
                            chunks.append(
                                {
                                    "id": "local-mock",
                                    "object": "chat.completion.chunk",
                                    "model": "no-cost-stub",
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {"content": content[index : index + 10]},
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                            )
                        chunks.append(
                            {
                                "id": "local-mock",
                                "object": "chat.completion.chunk",
                                "model": "no-cost-stub",
                                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                            }
                        )
                        payload = (
                            "".join(
                                "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
                                for chunk in chunks
                            )
                            + "data: [DONE]\n\n"
                        ).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Content-Length", str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                        return
                    result = {
                        "id": "local-mock",
                        "object": "chat.completion",
                        "model": "no-cost-stub",
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": content},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                    }
                payload = json.dumps(result, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_port}/v1"

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
