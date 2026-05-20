import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CREDENTIALS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../credentials.json")
)
TOKEN_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../data/calendar_token.json")
)


def get_credentials() -> Credentials:
    """Return valid Google Calendar credentials, refreshing or re-authing as needed."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_PATH}. "
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=8765)

        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


def run_oauth_flow():
    """Run the OAuth flow interactively and save the token."""
    if os.path.exists(TOKEN_PATH):
        os.remove(TOKEN_PATH)
    creds = get_credentials()
    print(f"Calendar auth complete. Token saved to {TOKEN_PATH}")
    return creds
