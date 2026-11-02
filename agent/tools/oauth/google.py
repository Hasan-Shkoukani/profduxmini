import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",  # create the starter folder/sheet
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
# One token file per Google account. ponytail: files on disk, swap for a DB if you deploy >1 instance.
TOKEN_DIR = os.path.join(BASE_DIR, "tokens")


def client_config() -> dict:
    with open(CREDENTIALS_FILE) as f:
        return json.load(f)


def _token_path(user_id: str) -> str:
    return os.path.join(TOKEN_DIR, f"{int(user_id)}.json")  # Google 'sub' is numeric; int() blocks path tricks


def save_credentials(user_id: str, creds: Credentials) -> None:
    os.makedirs(TOKEN_DIR, exist_ok=True)
    with open(_token_path(user_id), "w") as f:
        f.write(creds.to_json())


def get_google_credentials(config) -> Credentials:
    """Credentials of the logged-in user running this agent turn (config['configurable']['user_id'])."""
    user_id = (config or {}).get("configurable", {}).get("user_id")
    if not user_id or not os.path.exists(_token_path(user_id)):
        raise PermissionError("User is not signed in with Google.")

    creds = Credentials.from_authorized_user_file(_token_path(user_id), SCOPES)
    if not creds.valid:
        if not (creds.expired and creds.refresh_token):
            raise PermissionError("Google session expired, sign in again.")
        creds.refresh(Request())
        save_credentials(user_id, creds)
    return creds
