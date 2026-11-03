#!/usr/bin/env python3
"""Local dev server: serves the site AND a fake stats API, no AWS needed.

    python scripts/dev_server.py            # http://localhost:8000
    python scripts/dev_server.py --port 9000

The default config.js (statsApiUrl: "/api/") already points at the fake API,
so the quiz -> stats flow works end to end. Counts live in memory and reset on
restart. It mirrors the real setup: POST /api/result {"cert": id}, GET /api/stats.
"""
import argparse
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CERT_IDS = list(json.loads((ROOT / "data" / "tree.json").read_text(encoding="utf-8"))["certs"])
COUNTS = {c: 0 for c in CERT_IDS}
LOCK = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def _json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):  # CORS preflight, like the Function URL does
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/api/stats":
            with LOCK:
                ordered = sorted(COUNTS.items(), key=lambda kv: (-kv[1], CERT_IDS.index(kv[0])))
                total = sum(COUNTS.values())
            return self._json(200, {"total": total, "counts": [{"cert": c, "count": n} for c, n in ordered]})
        if path.startswith("/api"):
            return self._json(404, {"error": "not found"})
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0].rstrip("/") != "/api/result":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1024:
            return self._json(413, {"error": "body too large"})
        try:
            cert = json.loads(self.rfile.read(length) or b"{}").get("cert")
        except (ValueError, AttributeError):
            return self._json(400, {"error": "body must be JSON like {\"cert\": \"saa\"}"})
        if cert not in COUNTS:
            return self._json(400, {"error": "unknown cert id"})
        with LOCK:
            COUNTS[cert] += 1
        return self._json(200, {"ok": True})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(ROOT)))
    print(f"Site:      http://localhost:{args.port}/")
    print(f"Stats:     http://localhost:{args.port}/stats.html")
    print(f"Fake API:  http://localhost:{args.port}/api/stats")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
