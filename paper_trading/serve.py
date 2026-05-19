import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper_trading.state_store import StateStore

_STORE = StateStore(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_PATH = _STORE.state_path
TRADE_JOURNAL_PATH = _STORE.trade_journal_path
EQUITY_HISTORY_PATH = _STORE.equity_history_path
DEFAULT_PORT = 5000

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), 'frontend')
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'live', 'engine.log')

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css",
    ".js": "application/javascript",
}

STATIC_ROUTES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/style.css": "style.css",
    "/script.js": "script.js",
}


def serve(port=DEFAULT_PORT, shutdown_event=None):
    import http.server
    import socketserver

    class Handler(http.server.SimpleHTTPRequestHandler):
        def serve_static(self, filename, content_type):
            filepath = os.path.join(FRONTEND_DIR, filename)
            try:
                with open(filepath, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(data)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()

        def do_GET(self):
            path = self.path.split('?')[0]
            if path in STATIC_ROUTES:
                filename = STATIC_ROUTES[path]
                ext = os.path.splitext(filename)[1]
                content_type = MIME_TYPES.get(ext, 'text/html; charset=utf-8')
                self.serve_static(filename, content_type)
            elif path == '/state.json':
                try:
                    with open(STATE_PATH, 'r') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Cache-Control', 'no-cache')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(data.encode('utf-8'))
                except FileNotFoundError:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'engine_status': {'initialized': True, 'last_update': None, 'start_time': None},
                        'portfolio': {'total_value': 0, 'total_return': 0, 'days_running': 0,
                                      'start_date': '', 'last_update': None, 'capital': 100000,
                                       'allocations': {'BTC': 0.20, 'NZDJPY': 0.15, 'CADJPY': 0.13, 'USDCAD': 0.10, 'GC': 0.20, 'EURAUD': 0.22},
                                      'deployment_cleared': True},
                        'assets': {}, 'halt_conditions': {'drawdown': -0.08, 'monthly_pf': 0.7, 'signal_drought': 30, 'prob_drift': 0.15},
                    }, indent=2).encode('utf-8'))
            elif path == '/trades.json':
                trades = []
                try:
                    import pandas as pd
                    if os.path.exists(TRADE_JOURNAL_PATH):
                        df = pd.read_parquet(TRADE_JOURNAL_PATH)
                        if len(df) > 0:
                            df = df.sort_values('exit_date', ascending=False).head(10)
                            trades = json.loads(df.to_json(orient='records', default_handler=str))
                except Exception:
                    pass
                if not trades:
                    try:
                        with open(STATE_PATH, 'r') as f:
                            sd = json.load(f)
                        for aname, adata in sd.get('assets', {}).items():
                            for t in adata.get('metrics', {}).get('trade_log', []):
                                trades.append(t)
                        trades = sorted(trades, key=lambda x: x.get('exit_date', ''), reverse=True)[:10]
                    except Exception:
                        pass
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(trades, default=str).encode('utf-8'))
            elif path == '/equity_history.json':
                try:
                    with open(EQUITY_HISTORY_PATH, 'r') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Cache-Control', 'no-cache')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(data.encode('utf-8'))
                except FileNotFoundError:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'[]')
            elif path == '/logs':
                try:
                    with open(LOG_PATH, 'r') as f:
                        lines = f.readlines()
                    boundary = None
                    for i in range(len(lines) - 1, -1, -1):
                        if 'Server stopped.' in lines[i]:
                            boundary = i + 1
                            break
                    if boundary is not None:
                        tail = ''.join(lines[boundary:][-200:])
                    else:
                        tail = ''.join(lines[-200:])
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.send_header('Cache-Control', 'no-cache')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(tail.encode('utf-8'))
                except FileNotFoundError:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.send_header('Cache-Control', 'no-cache')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'[no log file yet]')
            else:
                self.send_response(404)
                self.end_headers()

    class ReuseServer(socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ReuseServer(('127.0.0.1', port), Handler)
    httpd.timeout = 0.5

    print(f'Dashboard: http://127.0.0.1:{port}')
    try:
        while not (shutdown_event and shutdown_event.is_set()):
            httpd.handle_request()
    except KeyboardInterrupt:
        pass
    httpd.server_close()


if __name__ == '__main__':
    serve(port=int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT)
