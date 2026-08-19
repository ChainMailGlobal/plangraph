"""PlanGraph demo server.

Serves demo/index.html and proxies /query to the HydraDB HTTP API so the
browser never fights CORS. Stdlib only.

Usage:
    python src/ingest.py <some.pdf>          # build the graph first
    python demo/serve.py                     # then open http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from hydra import Hydra  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
H = Hydra()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def do_POST(self):
        if self.path != "/query":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        try:
            rows = H.rows(body.get("cypher", ""))
            out = {"rows": rows}
        except Exception as e:
            out = {"error": str(e)}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print("PlanGraph demo on http://127.0.0.1:%d  (HydraDB at %s)" % (port, H.url))
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
