import gzip
import json
import os
from urllib.parse import parse_qsl, urlsplit

from paper_trading.api.common import MIME_TYPES, cache_get, get_index_html, route_cache_key, try_serve_file
from paper_trading.api.routes import GET_ROUTES, GET_ROUTES_PREFIX, POST_ROUTES


class Handler:
    def _send_json(self, data: str, status: int = 200) -> None:
        body = data.encode("utf-8")
        accept_gzip = self.headers.get("Accept-Encoding", "")
        if "gzip" in accept_gzip and len(body) > 512:
            body = gzip.compress(body)
            ct = "application/json"
            self.send_response(status)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Encoding", "gzip")
        else:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if getattr(self, "_send_body", True):
            self.wfile.write(body)

    def _send_text(self, data: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if getattr(self, "_send_body", True):
            self.wfile.write(data.encode("utf-8"))

    @staticmethod
    def _parse_query(query_string: str) -> dict[str, str]:
        return dict(parse_qsl(query_string, keep_blank_values=True))

    def do_HEAD(self):  # noqa: N802
        self._send_body = False
        self.do_GET()

    def _serve_index(self) -> bool:
        idx_path = get_index_html()
        try:
            with open(idx_path, "rb") as f:
                data = f.read()
            ext = os.path.splitext(idx_path)[1]
            ct = MIME_TYPES.get(ext, "text/html; charset=utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return True
        except (FileNotFoundError, PermissionError):
            return False

    def do_GET(self):  # noqa: N802
        parsed = urlsplit(self.path)
        path = parsed.path
        query = self._parse_query(parsed.query)

        if path in ("/", "/index.html"):
            if self._serve_index():
                return
            self.send_response(404)
            self.end_headers()
            return

        if path.startswith("/assets/") or path.startswith("/favicon.ico"):
            if try_serve_file(path, self):
                return
            self.send_response(404)
            self.end_headers()
            return

        if path in GET_ROUTES:
            cached = None
            fn, is_text = GET_ROUTES[path]
            if not is_text:
                cached = cache_get(route_cache_key(path, query))
            if cached is not None:
                self._send_json(cached)
                return
            result = fn(path, query)
            if is_text:
                self._send_text(result)
            else:
                self._send_json(result)
            return

        for prefix, fn, is_text in GET_ROUTES_PREFIX:
            if path.startswith(prefix) and path.endswith(".json"):
                result = fn(path, query)
                if isinstance(result, tuple):
                    data, status = result
                    self._send_json(data, status)
                elif is_text:
                    self._send_text(result)
                else:
                    self._send_json(result)
                return

        # SPA routing fallback: serve index.html for extension-less routes (e.g. /dashboard)
        if not os.path.splitext(path)[1] and self._serve_index():
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b""
        path = self.path.split("?")[0]
        fn = POST_ROUTES.get(path)
        if fn is not None:
            data, status = fn(body)
            self._send_json(data, status)
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode())
