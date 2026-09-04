#!/usr/bin/env python3
"""
Static file server for product-research reports, plus a /export.pdf endpoint that
renders the current report to a real (vector) PDF via headless Chrome and returns
it as a download.

    python3 serve-report.py <directory> [port]

The report's "Save as PDF" button calls /export.pdf and downloads the result.
If this server isn't running (plain http.server), the button falls back to the
browser print dialog automatically.
"""
import os, re, sys, glob, shutil, tempfile, subprocess, urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

def chrome_candidates():
    """Chrome/Chromium locations, most-likely first, across macOS / Linux / Windows."""
    names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
             "microsoft-edge", "brave-browser", "chrome"]
    found = [shutil.which(n) for n in names]
    mac = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Chromium.app/Contents/MacOS/Chromium",
           "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
           "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    win = []
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            win += [os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                    os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")]
    linux = ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
             "/snap/bin/chromium", "/usr/bin/microsoft-edge"]
    return [p for p in (mac + win + linux + found) if p]

def find_chrome():
    for p in chrome_candidates():
        if p and os.path.exists(p):
            return p
    return None

SAFE = re.compile(r"^[A-Za-z0-9._-]+$")

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if "/export.pdf" in (self.path or ""):
            sys.stderr.write("  [pdf] %s\n" % (fmt % args))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/export.pdf":
            return self.export_pdf(urllib.parse.parse_qs(parsed.query))
        return SimpleHTTPRequestHandler.do_GET(self)

    def export_pdf(self, q):
        page = (q.get("page") or ["report.html"])[0]
        name = (q.get("name") or ["report"])[0]
        # never let a query string escape the served directory
        page = os.path.basename(page)
        if not SAFE.match(page) or not page.endswith(".html"):
            return self.fail(400, "bad page parameter")
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "report"
        if not os.path.exists(os.path.join(os.getcwd(), page)):
            return self.fail(404, "no such page: %s" % page)

        chrome = find_chrome()
        if not chrome:
            return self.fail(503, "no Chrome/Chromium found for PDF rendering")

        url = "http://127.0.0.1:%d/%s" % (self.server.server_address[1], page)
        tmpdir = tempfile.mkdtemp(prefix="reportpdf-")
        out = os.path.join(tmpdir, "out.pdf")
        # NOTE: do NOT pass --user-data-dir here. When the user's own Chrome is
        # already running, a fresh profile dir makes headless hang on first-run
        # setup (verified: minimal flags 3s, with --user-data-dir >25s timeout).
        cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox",
               "--no-pdf-header-footer", "--virtual-time-budget=8000",
               "--print-to-pdf=" + out, url]
        try:
            subprocess.run(cmd, timeout=60,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not os.path.exists(out) or os.path.getsize(out) == 0:
                return self.fail(500, "Chrome produced no PDF")
            data = open(out, "rb").read()
        except subprocess.TimeoutExpired:
            return self.fail(504, "PDF render timed out")
        except Exception as e:
            return self.fail(500, "render failed: %s" % e)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", 'attachment; filename="%s.pdf"' % name)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def fail(self, code, msg):
        body = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    directory = os.path.abspath(os.path.expanduser(sys.argv[1]))
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 7950
    if not os.path.isdir(directory):
        print("not a directory:", directory); sys.exit(1)
    os.chdir(directory)
    pages = [os.path.basename(p) for p in glob.glob("*.html")]
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("serving %s on http://localhost:%d" % (directory, port), flush=True)
    print("  pages: %s" % (", ".join(pages) or "(none)"), flush=True)
    print("  chrome: %s" % (find_chrome() or
           "NOT FOUND - Save as PDF will fall back to the browser print dialog"), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")

if __name__ == "__main__":
    main()
