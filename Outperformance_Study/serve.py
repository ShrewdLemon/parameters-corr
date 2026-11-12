"""Serve the dashboard on the local network: python3 serve.py [port], then open http://<this machine's IP>:<port>/.

Every response says Cache-Control: no-cache, so browsers re-check files (a cheap 304 when unchanged) and nobody
on the network keeps an old copy after the dashboard is rebuilt.
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "dashboard"


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8700
    server = ThreadingHTTPServer(("0.0.0.0", port), partial(Handler, directory=str(ROOT)))
    print(f"Serving {ROOT} on port {port} (all network interfaces)")
    server.serve_forever()


if __name__ == "__main__":
    main()
