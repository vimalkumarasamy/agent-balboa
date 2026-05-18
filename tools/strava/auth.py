import os
import webbrowser
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv, set_key

ENV_PATH = os.path.join(os.path.dirname(__file__), "../../.env")

load_dotenv(ENV_PATH)

REDIRECT_PORT = 8000
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
SCOPES = "read,activity:read_all,activity:write"

_auth_code = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        params = parse_qs(urlparse(self.path).query)
        _auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Authorization successful. You can close this tab.</h2>")

    def log_message(self, *args):
        pass  # suppress request logs


def run_oauth_flow():
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError("STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET must be set in .env")

    url = (
        f"{AUTH_URL}?client_id={client_id}&response_type=code"
        f"&redirect_uri={REDIRECT_URI}&scope={SCOPES}&approval_prompt=force"
    )

    print("Opening browser for Strava authorization...")
    webbrowser.open(url)

    server = HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    print(f"Waiting for callback on {REDIRECT_URI} ...")
    server.handle_request()  # handles exactly one request then stops

    if not _auth_code:
        raise RuntimeError("No auth code received. Did you authorize the app?")

    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": _auth_code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    tokens = resp.json()

    env_path = os.path.abspath(ENV_PATH)
    set_key(env_path, "STRAVA_REFRESH_TOKEN", tokens["refresh_token"])
    print(f"Refresh token saved to .env")
    return tokens["refresh_token"]


def get_access_token() -> str:
    load_dotenv(os.path.abspath(ENV_PATH), override=True)
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")

    if not refresh_token:
        refresh_token = run_oauth_flow()

    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]
