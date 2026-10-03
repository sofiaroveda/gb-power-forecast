"""Preview the website locally: python tools/serve.py  (then open http://localhost:8000)
or python tools/serve.py 8001 to use another port.

Like `python -m http.server`, but tells the browser not to keep old copies of files,
so every edit shows up on a normal refresh.
"""

import functools
import http.server
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    handler = functools.partial(NoCacheHandler, directory=str(SITE))
    print(f"Serving {SITE} at http://localhost:{PORT} (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("", PORT), handler).serve_forever()
