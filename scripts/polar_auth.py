"""
One-time Polar Accesslink OAuth flow.

Prerequisites:
1. Register a developer app at developers.polar.com
2. Set redirect URI to http://localhost:8766
3. Add to .env:  POLAR_CLIENT_ID=...  POLAR_CLIENT_SECRET=...

Usage:
    python scripts/polar_auth.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from tools.health.polar import AUTH_URL, exchange_code, register_user, save_token

CLIENT_ID = os.getenv("POLAR_CLIENT_ID")
REDIRECT_URI = "http://localhost:8766"
PORT = 8766

auth_code = None


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>Polar auth complete. You can close this tab.</h2>")

    def log_message(self, *args):
        pass  # suppress request logs


if __name__ == "__main__":
    if not CLIENT_ID:
        print("POLAR_CLIENT_ID not set in .env — add it and try again.")
        sys.exit(1)

    url = (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&scope=accesslink.read_all"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    )

    print("Opening browser for Polar authorization...")
    webbrowser.open(url)

    server = HTTPServer(("localhost", PORT), _Handler)
    server.handle_request()

    if not auth_code:
        print("No authorization code received.")
        sys.exit(1)

    print("Exchanging code for token...")
    token = exchange_code(auth_code, REDIRECT_URI)
    access_token = token["access_token"]

    print("Registering user with Polar Accesslink...")
    user_info = register_user(access_token)
    polar_user_id = user_info.get("polar-user-id") or user_info.get("id")

    token["polar_user_id"] = polar_user_id
    save_token(token)

    print(f"Done. Polar user ID: {polar_user_id}")
    print(f"Token saved to data/polar_token.json")
