"""Local-only demo API. Not a public authenticated or cash-register service."""
from __future__ import annotations
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from sim.ledger import Ledger


def make_server(root: Path, database: Path, port=8765):
    bundle = json.loads((root / "proto/demo.json").read_text(encoding="utf-8"))
    database.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(database)
    for item in bundle["families"].values():
        ledger.assign(item["goal"])
    ledger.db.execute("CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL)")
    ledger.db.execute("INSERT OR IGNORE INTO settings VALUES (1,1)")
    ledger.db.commit()
    ledger.close()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, code, data, content_type="application/json; charset=utf-8"):
            body = data.encode() if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def local_request(self):
            accepted = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in accepted:
                raise ValueError("Localhost Host header required")
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{host}" for host in accepted}:
                raise ValueError("Cross-origin requests are not allowed")

        def enabled(self, ledger):
            return bool(ledger.db.execute("SELECT enabled FROM settings WHERE id=1").fetchone()[0])

        def do_GET(self):
            ledger = None
            try:
                self.local_request()
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    return self.respond(200, (root / "proto/index.html").read_text(encoding="utf-8"), "text/html; charset=utf-8")
                if parsed.path == "/health":
                    return self.respond(200, {"status": "ok", "data": "synthetic"})
                ledger = Ledger(database)
                if parsed.path == "/api/bootstrap":
                    return self.respond(200, {"bundle": bundle, "enabled": self.enabled(ledger)})
                if parsed.path == "/api/state":
                    family = parse_qs(parsed.query).get("family", [""])[0]
                    return self.respond(200, {"state": ledger.state(family), "enabled": self.enabled(ledger)})
                self.respond(404, {"error": "Not found"})
            except (ValueError, KeyError, TypeError) as error:
                self.respond(400, {"error": str(error)})
            finally:
                if ledger:
                    ledger.close()

        def do_POST(self):
            ledger = None
            try:
                self.local_request()
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("application/json required")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 200000:
                    raise ValueError("Body must be between 1 and 200000 bytes")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("JSON object required")
                ledger = Ledger(database)
                if self.path == "/api/receipt":
                    if not self.enabled(ledger):
                        return self.respond(409, {"error": "Приём чеков на паузе. Возвраты доступны."})
                    return self.respond(200, ledger.submit(payload))
                if self.path == "/api/cancel":
                    return self.respond(200, ledger.cancel(payload["family_id"], payload["receipt_id"]))
                if self.path == "/api/rollout":
                    if type(payload.get("enabled")) is not bool:
                        raise ValueError("enabled must be boolean")
                    with ledger.db:
                        ledger.db.execute("UPDATE settings SET enabled=? WHERE id=1", (int(payload["enabled"]),))
                    return self.respond(200, {"enabled": self.enabled(ledger)})
                self.respond(404, {"error": "Not found"})
            except (ValueError, KeyError, TypeError) as error:
                self.respond(400, {"error": str(error)})
            finally:
                if ledger:
                    ledger.close()

    return HTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.root, args.db or args.root / "results/demo.sqlite3", args.port)
    print(f"Synthetic local demo: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
