"""Preview the built dashboard the way GitHub Pages serves it: a missing path gets the site's
404.html (with status 404), which is how the SKU drill-down pages load (see dashboard/svelte.config.js).

    cp -r dashboard/build .preview/Wholesale-inventory-analytics
    uv run python scripts/serve_pages_preview.py .preview /Wholesale-inventory-analytics
    # then open http://localhost:4173/Wholesale-inventory-analytics/
"""

import http.server
import sys
from functools import partial
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
SITE = sys.argv[2]  # e.g. /Wholesale-inventory-analytics


class Handler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        path = Path(self.translate_path(self.path))
        if path.is_dir():
            path = path / "index.html"
        if not path.exists():
            body = (ROOT / SITE.strip("/") / "404.html").read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        return super().send_head()


http.server.ThreadingHTTPServer(
    ("127.0.0.1", 4173), partial(Handler, directory=str(ROOT))
).serve_forever()
