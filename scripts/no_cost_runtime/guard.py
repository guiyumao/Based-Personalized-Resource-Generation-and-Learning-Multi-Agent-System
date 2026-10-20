"""Python no-cost test boundary; not an OS sandbox for arbitrary native code."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

_installed = False
_ports: set[int] = set()
_directory = str(Path(__file__).resolve().parent)
_original_bind = socket.socket.bind


def _check_url(url) -> None:
    parsed = urlsplit(str(url))
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme not in {"http", "https"} or not _local(parsed.hostname) or port not in _ports:
        _record("http-url", "blocked")
        raise PermissionError("NO_COST_GUARD: HTTP destination not a declared local listener")


def _record(event: str, outcome: str) -> None:
    filename = os.environ.get("NO_COST_NETWORK_LEDGER")
    if filename:
        # Never log addresses, headers, prompts, tokens, or child command lines.
        with open(filename, "a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {"pid": os.getpid(), "event": event, "outcome": outcome, "time": time.time()}
                )
                + "\n"
            )


def _local(host: object) -> bool:
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return False


def _audit(event: str, args: tuple) -> None:
    if event == "open":
        filename, mode, flags = args
        if (
            isinstance(filename, (str, bytes))
            and os.fsdecode(filename).replace("\\", "/").split("/")[-1] == ".env"
        ):
            if mode is None or "r" in mode or "+" in mode:
                _record("dotenv-read", "blocked")
                raise PermissionError("NO_COST_GUARD: developer dotenv reads forbidden")
    elif event == "socket.getaddrinfo":
        if args[0] is not None and not _local(args[0]):
            _record("dns", "blocked")
            raise PermissionError("NO_COST_GUARD: external DNS forbidden")
    elif event in {"socket.connect", "socket.sendto"}:
        address = args[1] if event == "socket.connect" else args[-1]
        if (
            not isinstance(address, tuple)
            or not _local(address[0])
            or int(address[1]) not in _ports
        ):
            _record(event, "blocked")
            raise PermissionError("NO_COST_GUARD: destination not a declared local listener")
        _record(event, "allowed-local")
    elif event == "subprocess.Popen":
        executable, _command, _cwd, child_env = args
        if Path(str(executable)).name.lower().startswith("python"):
            effective = os.environ if child_env is None else child_env
            if effective.get("NO_COST_TEST") != "1" or _directory not in effective.get(
                "PYTHONPATH", ""
            ).split(os.pathsep):
                _record("child-guard", "blocked")
                raise PermissionError("NO_COST_GUARD: Python child omitted safety environment")


def _bind(sock, address):
    if isinstance(address, tuple) and not _local(address[0]):
        raise PermissionError("NO_COST_GUARD: bind only to loopback")
    result = _original_bind(sock, address)
    if isinstance(address, tuple):
        # Declares only listeners actually owned by this guarded Python process.
        port = int(sock.getsockname()[1])
        _ports.add(port)
        os.environ["NO_COST_ALLOWED_PORTS"] = ",".join(map(str, sorted(_ports)))
    return result


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    _ports.update(
        int(value) for value in os.environ.get("NO_COST_ALLOWED_PORTS", "").split(",") if value
    )
    os.environ.update(
        NO_COST_TEST="1", APP_LOAD_DOTENV="false", RUN_LIVE_LLM="0", DEEPSEEK_LIVE_PAID_ACK="0"
    )
    for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "QWEN_API_KEY"):
        # Optional ephemeral token authenticates a declared loopback gateway;
        # never a real provider key. The gateway owns any paid authorization.
        os.environ[key] = os.environ.get("NO_COST_LOCAL_API_TOKEN", "no-cost-stub")
    for key in ("OPENAI_BASE_URL", "QWEN_API_BASE", "DEEPSEEK_API_BASE", "DEEPSEEK_SEARCH_BASE"):
        base = os.environ.get(key, "")
        if not base or not _local(urlsplit(base).hostname):
            os.environ[key] = ""
    # Preserve adapter default URL contracts for in-memory MockTransport tests;
    # the socket/HTTP guards still deny any actual external connection.
    if not os.environ.get("DEEPSEEK_SEARCH_BASE"):
        os.environ.pop("DEEPSEEK_SEARCH_BASE", None)
    for key in list(os.environ):
        if key.lower().endswith("_proxy"):
            os.environ.pop(key)
    os.environ["NO_PROXY"] = "*"
    socket.socket.bind = _bind
    sys.addaudithook(_audit)
    os.environ["NO_COST_GUARD_ACTIVE"] = "1"
    _record("guard-start", "active")
    # Some dependencies (e.g. Chroma/Pydantic Settings) independently discover
    # .env. Disable their loader before import, while direct reads still fail.
    try:
        import dotenv
        from dotenv.main import DotEnv

        dotenv.dotenv_values = lambda *args, **kwargs: {}
        dotenv.load_dotenv = lambda *args, **kwargs: False
        DotEnv.dict = lambda self: {}
        DotEnv.set_as_environment_variables = lambda self: False
    except ImportError:
        pass
    # Windows CreateProcess does not consistently expose the child's env in
    # audit events. Validate it before Popen delegates to the native API.
    import inspect
    import subprocess

    original_popen = subprocess.Popen
    signature = inspect.signature(original_popen)

    class GuardedPopen(original_popen):
        def __init__(self, args, *positional, **kwargs):
            bound = signature.bind(args, *positional, **kwargs).arguments
            executable = bound.get("executable") or (
                args[0] if isinstance(args, (list, tuple)) else str(args).split()[0]
            )
            if Path(str(executable)).name.lower().startswith("python"):
                effective = bound.get("env")
                effective = os.environ if effective is None else effective
                if effective.get("NO_COST_TEST") != "1" or _directory not in effective.get(
                    "PYTHONPATH", ""
                ).split(os.pathsep):
                    _record("child-guard", "blocked")
                    raise PermissionError("NO_COST_GUARD: Python child omitted safety environment")
            super().__init__(args, *positional, **kwargs)

    subprocess.Popen = GuardedPopen
    try:
        import httpx
    except ImportError:
        return  # socket layer remains mandatory, HTTP clients may be absent
    send = httpx.Client.send
    async_send = httpx.AsyncClient.send

    def checked_send(client, request, *args, **kwargs):
        # ASGI/MockTransport does not connect to a provider; permit TestClient.
        if type(client._transport).__module__.startswith(("httpx", "httpcore")) and not isinstance(
            client._transport, httpx.MockTransport
        ):
            _check_url(request.url)
        return send(client, request, *args, **kwargs)

    async def checked_async_send(client, request, *args, **kwargs):
        if not isinstance(client._transport, (httpx.MockTransport, httpx.ASGITransport)):
            _check_url(request.url)
        return await async_send(client, request, *args, **kwargs)

    httpx.Client.send = checked_send
    httpx.AsyncClient.send = checked_async_send
