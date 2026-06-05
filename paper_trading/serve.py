import http.server
import logging
import socketserver
from socketserver import ThreadingMixIn

from paper_trading.api.handler import Handler

logger = logging.getLogger("quantforge.serve")

DEFAULT_PORT = 5000


class ReuseServer(ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ServingHandler(Handler, http.server.SimpleHTTPRequestHandler):
    pass


def serve(port=DEFAULT_PORT, shutdown_event=None):
    httpd = ReuseServer(("127.0.0.1", port), ServingHandler)
    httpd.timeout = 0.5

    print(f"Dashboard: http://127.0.0.1:{port}")
    try:
        while not (shutdown_event and shutdown_event.is_set()):
            httpd.handle_request()
    except KeyboardInterrupt:
        logger.info("Dashboard server shutting down (SIGINT)")
    httpd.server_close()
