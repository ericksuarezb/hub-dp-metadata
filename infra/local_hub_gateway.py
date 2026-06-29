from __future__ import annotations

import argparse
import http.client
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

LANDING_ROOT = Path(__file__).resolve().parents[1] / "apps" / "landing" / "site"

PROXIES = {
    "docgen.localhost": ("127.0.0.1", 8310),
    "editor.localhost": ("127.0.0.1", 4273),
    "entropy.localhost": ("127.0.0.1", 8082),
    "answer.localhost": ("127.0.0.1", 9080),
    "redash.localhost": ("127.0.0.1", 5001),
    "mail.localhost": ("127.0.0.1", 8026),
}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class HubGatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._dispatch()

    def do_HEAD(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def do_PUT(self) -> None:
        self._dispatch()

    def do_PATCH(self) -> None:
        self._dispatch()

    def do_DELETE(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        host = (self.headers.get("Host") or "").split(":", 1)[0].lower()
        target = PROXIES.get(host)
        if target:
            self._proxy_request(target)
            return
        self._serve_static()

    def _proxy_request(self, target: tuple[str, int]) -> None:
        upstream_host, upstream_port = target
        original_host = self.headers.get("Host", "")
        body = None
        length = self.headers.get("Content-Length")
        if length:
            body = self.rfile.read(int(length))

        upstream_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        upstream_headers["Host"] = original_host
        upstream_headers["X-Forwarded-Host"] = original_host
        upstream_headers["X-Forwarded-Proto"] = "http"
        upstream_headers["X-Forwarded-For"] = self.client_address[0]

        connection = http.client.HTTPConnection(upstream_host, upstream_port, timeout=30)
        try:
            connection.request(self.command, self.path, body=body, headers=upstream_headers)
            response = connection.getresponse()
            payload = response.read()
        except Exception as exc:
            self.send_error(502, f"Upstream unavailable: {exc}")
            return
        finally:
            connection.close()

        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            if key.lower() in HOP_BY_HOP_HEADERS:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _serve_static(self) -> None:
        if self.command not in {"GET", "HEAD"}:
            self.send_error(405, "Method not allowed")
            return

        raw_path = urlsplit(self.path).path
        relative = raw_path.lstrip("/") or "index.html"
        file_path = (LANDING_ROOT / relative).resolve()

        if file_path.is_dir():
            file_path = file_path / "index.html"

        if not str(file_path).startswith(str(LANDING_ROOT.resolve())) or not file_path.exists():
            self.send_error(404, "Not found")
            return

        content = file_path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local hub gateway for *.localhost routes.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=80)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), HubGatewayHandler)
    print(f"Hub gateway listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
