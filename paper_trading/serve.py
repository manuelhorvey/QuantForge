import http.server
import logging
import os
import socketserver
from socketserver import ThreadingMixIn

from paper_trading.api.handler import Handler

logger = logging.getLogger("quantforge.serve")

DEFAULT_PORT = 5000
DEFAULT_BIND = os.environ.get("QUANTFORGE_BIND", "127.0.0.1")


class ReuseServer(ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ServingHandler(Handler, http.server.SimpleHTTPRequestHandler):
    pass


def serve(port=DEFAULT_PORT, shutdown_event=None):
    bind = DEFAULT_BIND
    if bind != "127.0.0.1":
        logger.warning(
            "⚠  Dashboard binding to %s (not localhost). "
            "Ensure API auth token is configured via QUANTFORGE_API_TOKEN or paper_trading.yaml.",
            bind,
        )
        from paper_trading.api.common import _load_auth_token

        _load_auth_token()

    httpd = ReuseServer((bind, port), ServingHandler)
    httpd.timeout = 0.5

    url = f"http://{'127.0.0.1' if bind == '0.0.0.0' else bind}:{port}"
    print(f"Dashboard: {url}")
    try:
        while not (shutdown_event and shutdown_event.is_set()):
            httpd.handle_request()
    except KeyboardInterrupt:
        logger.info("Dashboard server shutting down (SIGINT)")
    httpd.server_close()
