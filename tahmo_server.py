#!/usr/bin/env python3
"""
TAHMO live dashboard launcher (hardened).

The TAHMO APIs don't send permissive CORS headers, so a browser blocks a plain
double-clicked HTML file from fetching them. This tiny server (Python standard
library only -- no pip installs) serves the dashboard AND relays the three API
calls from the same origin, which the browser accepts.

Run it:
    python tahmo_server.py
...then your browser opens http://localhost:8000 automatically. Leave the window
open while you use the dashboard. Ctrl+C to stop.

Options:
    python tahmo_server.py 8080         # use a different port
    python tahmo_server.py --insecure   # skip SSL certificate verification
                                        # (use if you get CERTIFICATE_VERIFY_FAILED)

Corporate proxy? Set these BEFORE running (Windows CMD example):
    set HTTPS_PROXY=http://your.proxy:port
    set HTTP_PROXY=http://your.proxy:port
"""
import http.server, socketserver, urllib.request, urllib.error
import json, os, sys, ssl, time, threading, webbrowser

# ---- args ----
args = sys.argv[1:]
INSECURE = "--insecure" in args
args = [a for a in args if a != "--insecure"]
PORT = int(args[0]) if args else 8000

HERE = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(HERE, "tahmo_live.html")

ENDPOINTS = {
    "/api/open":     "https://tickets.tahmo.org/api/issues?status=open",
    "/api/pending":  "https://tickets.tahmo.org/api/issues?status=pending",
    "/api/stations": "https://datahub.tahmo.org/custom/stations/status",
}
CACHE_TTL = 120
_cache = {}

# ---- SSL context: verify by default, allow --insecure fallback ----
if INSECURE:
    SSL_CTX = ssl.create_default_context()
    SSL_CTX.check_hostname = False
    SSL_CTX.verify_mode = ssl.CERT_NONE
    print("[!] --insecure: SSL certificate verification is DISABLED.")
else:
    SSL_CTX = ssl.create_default_context()
    # Try to use the 'certifi' bundle if it happens to be installed (helps on
    # machines whose system cert store Python can't read). Ignored if absent.
    try:
        import certifi
        SSL_CTX.load_verify_locations(certifi.where())
    except Exception:
        pass


def upstream(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TAHMO-Live/1.1"})
    with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as r:
        return r.read()


def diagnose(url, err):
    """Turn a raw fetch error into a plain-language explanation + fix."""
    s = str(err)
    if "CERTIFICATE_VERIFY_FAILED" in s or isinstance(err, ssl.SSLError):
        return ("SSL certificate verification failed. Your machine can't validate "
                "TAHMO's certificate (common on Windows / office networks).\n"
                "    FIX: stop the server (Ctrl+C) and restart it with:\n"
                "         python tahmo_server.py --insecure")
    if isinstance(err, urllib.error.HTTPError):
        return f"The API returned HTTP {err.code} for {url} (the API itself, not your setup)."
    if "proxy" in s.lower() or "forbidden" in s.lower() or "407" in s:
        return ("Looks like a corporate proxy/firewall is blocking the request.\n"
                "    FIX: set HTTPS_PROXY / HTTP_PROXY env vars, then restart. See top of this file.")
    if "timed out" in s.lower() or "timeout" in s.lower():
        return ("The request timed out -- the network couldn't reach TAHMO.\n"
                "    Check your internet/VPN, then retry.")
    if "Name or service not known" in s or "getaddrinfo" in s or "nodename" in s:
        return ("DNS lookup failed -- your machine couldn't resolve the TAHMO address.\n"
                "    Check your internet connection / DNS / VPN.")
    return f"Could not fetch {url}\n    Raw error: {s}"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path in ("/", "/index.html", "/tahmo_live.html"):
            try:
                with open(HTML_FILE, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(500, b"tahmo_live.html not found next to this script. "
                                b"Keep both files in the same folder.",
                           "text/plain; charset=utf-8")
            return

        if path in ENDPOINTS:
            now = time.time()
            ts, data = _cache.get(path, (0, None))
            if data is None or now - ts > CACHE_TTL:
                try:
                    data = upstream(ENDPOINTS[path])
                    _cache[path] = (now, data)
                except Exception as e:
                    msg = diagnose(ENDPOINTS[path], e)
                    # Print the real diagnosis to the terminal...
                    print("\n[FETCH ERROR] " + path)
                    print("    " + msg.replace("\n", "\n    "))
                    if data is None:
                        # ...and return it to the browser so the banner is useful.
                        self._send(502, json.dumps({"error": msg}).encode(),
                                   "application/json")
                        return
            self._send(200, data, "application/json; charset=utf-8")
            return

        self._send(404, b"Not found", "text/plain; charset=utf-8")


def preflight():
    """Test all endpoints once at startup and print a clear verdict."""
    print("Checking connection to TAHMO APIs...")
    ok = True
    for path, url in ENDPOINTS.items():
        try:
            n = len(upstream(url))
            print(f"  OK   {path}  ({n:,} bytes)")
        except Exception as e:
            ok = False
            print(f"  FAIL {path}")
            print("       " + diagnose(url, e).replace("\n", "\n       "))
    print("All endpoints reachable.\n" if ok else
          "\nOne or more endpoints failed above -- read the FIX line(s).\n"
          "The server will still start so you can retry with the suggested fix.\n")
    return ok


def main():
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        print(f"[!] Could not bind port {PORT}: {e}")
        print(f"    Another program may be using it. Try: python tahmo_server.py {PORT+1}")
        sys.exit(1)
    with httpd:
        url = f"http://localhost:{PORT}/"
        print(f"TAHMO live dashboard running at {url}")
        print("Leave this window open. Press Ctrl+C to stop.\n")
        # Server is already listening; run the connectivity check in the
        # background so a slow feed never delays startup or the browser.
        threading.Thread(target=preflight, daemon=True).start()
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
