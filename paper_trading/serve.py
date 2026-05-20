import sys, os, json
from dataclasses import asdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper_trading.state_store import StateStore
from paper_trading.risk_governance import get_latest as _get_risk_latest
from paper_trading.health_score import get_latest as _get_health_latest, compute_all as _compute_health_all

_STORE = StateStore(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_PORT = 5000
BASE = os.path.dirname(os.path.abspath(__file__))

DASHBOARD_DIST = os.path.join(BASE, 'dashboard', 'dist')
FRONTEND_DIR = os.path.join(BASE, 'frontend')
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'live', 'engine.log')
CONFIDENCE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'live', 'confidence_buckets.parquet')

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css",
    ".js": "application/javascript",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".json": "application/json",
}

VOL_BASELINES = {
    "BTC": 0.038705, "GC": 0.009129,
    "NZDJPY": 0.006581, "CADJPY": 0.005989,
    "USDCAD": 0.004463, "EURAUD": 0.005026,
    "AUDJPY": 0.006759, "GBPJPY": 0.006138,
    "USDJPY": 0.004498, "USDCHF": 0.004307,
    "GBPUSD": 0.005595,
}

STATIC_ROUTES_VANILLA = {
    "/": "index.html",
    "/index.html": "index.html",
    "/style.css": "style.css",
    "/script.js": "script.js",
}


def get_index_html():
    dist = os.path.join(DASHBOARD_DIST, 'index.html')
    if os.path.exists(dist):
        return os.path.join(DASHBOARD_DIST, 'index.html')
    return os.path.join(FRONTEND_DIR, 'index.html')


def try_serve_file(path, resp):
    """Try to serve a static file from dist/ or frontend/ by exact path."""
    clean = path.split('?')[0].lstrip('/')
    candidates = []
    if DASHBOARD_DIST:
        candidates.append(os.path.join(DASHBOARD_DIST, clean))
    if FRONTEND_DIR:
        candidates.append(os.path.join(FRONTEND_DIR, clean))
    for fp in candidates:
        if os.path.exists(fp) and os.path.isfile(fp):
            ext = os.path.splitext(fp)[1]
            ct = MIME_TYPES.get(ext, 'application/octet-stream')
            try:
                with open(fp, 'rb') as f:
                    data = f.read()
                resp.send_response(200)
                resp.send_header('Content-Type', ct)
                resp.send_header('Cache-Control', 'no-cache')
                resp.end_headers()
                resp.wfile.write(data)
                return True
            except Exception:
                pass
    return False


def serve(port=DEFAULT_PORT, shutdown_event=None):
    import http.server
    import socketserver

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split('?')[0]

            # Serve root and index.html from React build or vanilla fallback
            if path in ('/', '/index.html'):
                idx_path = get_index_html()
                try:
                    with open(idx_path, 'rb') as f:
                        data = f.read()
                    ext = os.path.splitext(idx_path)[1]
                    ct = MIME_TYPES.get(ext, 'text/html; charset=utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', ct)
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    self.wfile.write(data)
                except FileNotFoundError:
                    self.send_response(404)
                    self.end_headers()
                return

            # Try static file from dist/ or frontend/
            if path.startswith('/assets/') or path.startswith('/favicon.ico'):
                if try_serve_file(path, self):
                    return
                self.send_response(404)
                self.end_headers()
                return

            # API endpoints
            if path == '/state.json':
                snapshot = _STORE.load_snapshot()
                if snapshot is not None:
                    data = json.dumps(asdict(snapshot), indent=2, default=str)
                else:
                    data = json.dumps({
                        'engine_status': {'initialized': True, 'last_update': None, 'start_time': None},
                        'portfolio': {'total_value': 0, 'total_return': 0, 'days_running': 0,
                                      'start_date': '', 'last_update': None, 'capital': 100000,
                                       'allocations': {'BTC': 0.14, 'NZDJPY': 0.11, 'CADJPY': 0.10, 'USDCAD': 0.07, 'GC': 0.15, 'EURAUD': 0.17, 'AUDJPY': 0.07, 'GBPJPY': 0.06, 'USDJPY': 0.05, 'USDCHF': 0.04, 'GBPUSD': 0.04},
                                      'deployment_cleared': True},
                        'assets': {}, 'halt_conditions': {'drawdown': -0.08, 'monthly_pf': 0.7, 'signal_drought': 30, 'prob_drift': 0.15},
                    }, indent=2)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
            elif path == '/trades.json':
                trades = _STORE.read_trades(10)
                if not trades:
                    snapshot = _STORE.load_snapshot()
                    if snapshot and snapshot.assets:
                        for aname, adata in snapshot.assets.items():
                            for t in adata.get('metrics', {}).get('trade_log', []):
                                trades.append(t)
                        trades = sorted(trades, key=lambda x: x.get('exit_date', ''), reverse=True)[:10]
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(trades, default=str).encode('utf-8'))
            elif path == '/equity_history.json':
                history = _STORE.read_equity_history()
                data = json.dumps(history, default=str)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
            elif path == '/confidence.json':
                snapshot = _STORE.load_snapshot()
                if snapshot and snapshot.assets:
                    live = {}
                    for name, asset in snapshot.assets.items():
                        sig = asset.get('last_signal', {})
                        conf = sig.get('confidence', 0)
                        bucket = f"{int(conf // 10) * 10}-{int(conf // 10) * 10 + 10}"
                        live.setdefault(name, {})
                        live[name][bucket] = live[name].get(bucket, 0) + 1
                    historical = []
                    try:
                        if os.path.exists(CONFIDENCE_PATH):
                            import pandas as pd
                            df = pd.read_parquet(CONFIDENCE_PATH)
                            historical = json.loads(df.to_json(orient='records', default_handler=str))
                    except Exception:
                        pass
                    data = json.dumps({'live': live, 'historical': historical}, indent=2, default=str)
                else:
                    data = json.dumps({'live': {}, 'historical': []})
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
            elif path == '/volatility.json':
                snapshot = _STORE.load_snapshot()
                regimes = []
                if snapshot and snapshot.assets:
                    for name, asset in sorted(snapshot.assets.items()):
                        training_vol = VOL_BASELINES.get(name)
                        pos = asset.get('metrics', {}).get('position', {})
                        current_vol = pos.get('current_vol') if pos else None
                        if training_vol is not None and current_vol is not None:
                            ratio = current_vol / training_vol
                            if 0.80 <= ratio <= 1.20:
                                status = 'green'
                            elif (0.70 <= ratio < 0.80) or (1.20 < ratio <= 1.30):
                                status = 'amber'
                            else:
                                status = 'red'
                            regimes.append({
                                'asset': name,
                                'training_vol': training_vol,
                                'current_vol': current_vol,
                                'ratio': round(ratio, 4),
                                'status': status,
                            })
                data = json.dumps(regimes, indent=2, default=str)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
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
            elif path == '/risk.json':
                data = json.dumps(_get_risk_latest(), indent=2, default=str)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
            elif path.startswith('/risk/') and path.endswith('.json'):
                asset = path[len('/risk/'):-len('.json')]
                signal = _get_risk_latest(asset)
                if signal is not None:
                    data = json.dumps(signal, indent=2, default=str)
                    self.send_response(200)
                else:
                    data = json.dumps({'error': f'No risk signal for {asset}', 'asset': asset})
                    self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
            elif path == '/shadow-actions':
                snapshot = _STORE.load_snapshot()
                actions = getattr(snapshot, 'shadow_actions', None) if snapshot else None
                data = json.dumps(actions or {}, indent=2, default=str)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
            elif path.startswith('/shadow-actions/') and path.endswith('.json'):
                asset = path[len('/shadow-actions/'):-len('.json')]
                snapshot = _STORE.load_snapshot()
                actions = getattr(snapshot, 'shadow_actions', None) if snapshot else None
                action = (actions or {}).get(asset)
                if action is not None:
                    data = json.dumps(action, indent=2, default=str)
                    self.send_response(200)
                else:
                    data = json.dumps({'error': f'No shadow action for {asset}', 'asset': asset})
                    self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
            elif path == '/health.json':
                data = json.dumps(_compute_health_all(), indent=2, default=str)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
            elif path.startswith('/health/') and path.endswith('.json'):
                asset = path[len('/health/'):-len('.json')]
                signal = _get_health_latest(asset)
                if signal is not None:
                    data = json.dumps(signal, indent=2, default=str)
                    self.send_response(200)
                else:
                    data = json.dumps({'error': f'No health score for {asset}', 'asset': asset})
                    self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
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
