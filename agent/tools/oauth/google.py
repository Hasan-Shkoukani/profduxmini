import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events"
]


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def get_google_credentials():
    """
    Returns valid Google credentials, refreshing automatically if expired.
    Prevents repeated login by storing a refresh_token in token.json.
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            try:
                with open(CREDENTIALS_FILE, "r") as f:
                    client_config = json.load(f)
            except Exception as e:
                raise Exception(f"Error loading credentials.json: {e}")

            flow = InstalledAppFlow.from_client_config(
                client_config,
                SCOPES
            )

            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="select_account",
            )

            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

    return creds
