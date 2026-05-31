from pathlib import Path

from paper_trading.api import common, routes
from paper_trading.api.handler import Handler


class FakeResponse:
    def __init__(self):
        self.status = None
        self.headers = []
        self.body = bytearray()
        self.wfile = self

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)


def test_try_serve_file_rejects_asset_path_traversal(tmp_path, monkeypatch):
    root = tmp_path / "dist"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(common, "DASHBOARD_DIST", str(root))
    monkeypatch.setattr(common, "FRONTEND_DIR", str(root))

    resp = FakeResponse()

    assert common.try_serve_file("/assets/../secret.txt", resp) is False
    assert resp.body == b""


def test_try_serve_file_serves_files_within_static_root(tmp_path, monkeypatch):
    root = tmp_path / "dist"
    asset_dir = root / "assets"
    asset_dir.mkdir(parents=True)
    asset = asset_dir / "app.js"
    asset.write_text("console.log('ok')", encoding="utf-8")
    monkeypatch.setattr(common, "DASHBOARD_DIST", str(root))
    monkeypatch.setattr(common, "FRONTEND_DIR", str(Path(tmp_path) / "frontend"))

    resp = FakeResponse()

    assert common.try_serve_file("/assets/app.js", resp) is True
    assert resp.status == 200
    assert bytes(resp.body) == b"console.log('ok')"


def test_parse_query_decodes_url_encoded_values():
    assert Handler._parse_query("asset=EURUSD%3DX&limit=25&empty=") == {
        "asset": "EURUSD=X",
        "limit": "25",
        "empty": "",
    }


def test_bounded_int_query_clamps_and_defaults():
    assert common.bounded_int_query({"limit": "999"}, "limit", default=10, minimum=1, maximum=200) == 200
    assert common.bounded_int_query({"limit": "-5"}, "limit", default=10, minimum=1, maximum=200) == 1
    assert common.bounded_int_query({"limit": "bad"}, "limit", default=10, minimum=1, maximum=200) == 10


def test_trade_route_cache_is_query_aware(monkeypatch):
    common._CACHE.clear()
    monkeypatch.setattr(
        routes._STORE,
        "read_trades",
        lambda limit: [{"asset": "EURUSD", "entry_date": "2026-01-01", "exit_date": "2026-01-02"}][:limit],
    )
    monkeypatch.setattr(routes._STORE, "load_snapshot", lambda: None)

    routes.handle_trades("/trades.json", {"limit": "1"})

    assert common.cache_get("/trades.json") is None
    assert common.cache_get("/trades.json?limit=1") is not None
