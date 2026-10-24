"""M4-only network fixture, not the normal product entry point.

Run this under scripts/loopback-only.sb. The OS denies server non-loopback I/O.
An extra test-only CSP confines the page's subresources/connects to its local
origin, while a positive control proves that external image loading is blocked.
No uploaded content, filenames, query strings or request bodies are logged.
This is scoped application isolation, not a claim that the entire Mac is offline.
"""
from __future__ import annotations

import errno
import json
from pathlib import Path
import runpy
import socket
import sys
from threading import Lock
from time import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "m4-network-events.jsonl"
LOCK = Lock()
PORT = 8502
CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "font-src 'self' data:; connect-src 'self' ws://127.0.0.1:8502; "
    "worker-src 'self' blob:; frame-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; report-uri /_m4/csp"
)


def event(kind, **fields):
    with LOCK:
        with EVIDENCE.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": time(), "event": kind, **fields}) + "\n")


def audit(event_name, args):
    if event_name == "socket.connect":
        address = args[1]
        # Only endpoint classification, never raw arguments or Unix paths.
        host = address[0] if isinstance(address, tuple) else None
        event("socket_connect", loopback=host in ("127.0.0.1", "::1"),
              endpoint_kind="ip" if host is not None else "unix")
    elif event_name == "socket.getaddrinfo":
        event("dns_lookup", loopback=args[0] in ("127.0.0.1", "localhost", "::1"))


def assert_os_isolation():
    # Numeric TEST-NET address avoids DNS and carries no application data.
    for family, target in [(socket.AF_INET, ("192.0.2.1", 443)),
                           (socket.AF_INET6, ("2001:db8::1", 443))]:
        with socket.socket(family) as connection:
            connection.settimeout(1)
            try:
                connection.connect(target)
            except OSError as exc:
                if exc.errno not in (errno.EPERM, errno.EACCES):
                    raise RuntimeError("Expected OS policy denial, not a timeout or routing failure") from None
                event("os_deny_probe", family="ipv4" if family == socket.AF_INET else "ipv6",
                      errno=exc.errno, passed=True)
            else:
                raise RuntimeError("External networking was unexpectedly permitted")
    event("server_probe_complete")


class NetworkFixture:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path = scope["path"]
        category = ("static" if path.startswith("/static/") else
                    "upload" if path.startswith("/_stcore/upload_file") else
                    "download" if path.startswith("/media/") else
                    "websocket" if scope["type"] == "websocket" else
                    "probe" if path.startswith("/_m4/") else "page_or_control")
        event("inbound", category=category, protocol=scope["type"])

        async def safe_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [*message.get("headers", []),
                                      (b"content-security-policy", CSP.encode()),
                                      (b"cache-control", b"no-store")]
                event("response", category=category, status=message["status"])
            await send(message)

        if scope["type"] == "http" and path == "/_m4/csp":
            body = bytearray()
            while True:
                part = await receive()
                body.extend(part.get("body", b""))
                if len(body) > 8192 or not part.get("more_body"):
                    break
            try:
                report = json.loads(body).get("csp-report", {})
                blocked = urlsplit(report.get("blocked-uri", ""))
                document = urlsplit(report.get("document-uri", ""))
                event("csp_violation", directive=report.get("effective-directive", "unknown"),
                      external_origin=blocked.scheme in ("http", "https", "ws", "wss")
                      and blocked.hostname not in ("127.0.0.1", "localhost"),
                      positive_control=document.path == "/_m4/probe")
            except (ValueError, TypeError):
                event("csp_report_invalid")
            await safe_send({"type": "http.response.start", "status": 204, "headers": []})
            return await safe_send({"type": "http.response.body", "body": b""})
        if scope["type"] == "http" and path == "/_m4/probe":
            body = b'''<!doctype html><html><meta charset="utf-8"><title>M4 offline positive control</title>
<h1>Network isolation positive control</h1><p id="status">Testing external image denial...</p>
<img src="https://example.com/sheetcheck-offline-probe.png" alt="Blocked external probe"
onerror="document.getElementById('status').textContent='PASS: external image blocked by policy'"
onload="document.getElementById('status').textContent='FAIL: external image loaded'">
<p><a href="/">Continue to local SheetCheck</a></p></html>'''
            await safe_send({"type": "http.response.start", "status": 200,
                             "headers": [(b"content-type", b"text/html; charset=utf-8")]})
            return await safe_send({"type": "http.response.body", "body": body})
        return await self.app(scope, receive, safe_send)


if __name__ == "__main__":
    sys.addaudithook(audit)
    event("acceptance_start", port=PORT, scope="server OS deny + page CSP", csp=CSP)
    assert_os_isolation()
    from streamlit.web.server.starlette import starlette_server
    original = starlette_server.create_starlette_app
    starlette_server.create_starlette_app = lambda runtime: NetworkFixture(original(runtime))
    sys.argv = ["streamlit", "run", str(ROOT / "app.py"), "--server.address", "127.0.0.1",
                "--server.port", str(PORT), "--browser.serverAddress", "127.0.0.1"]
    runpy.run_module("streamlit", run_name="__main__")
