import os
import requests
import base64
from dotenv import load_dotenv
from langchain_core.tools import tool
from openai import OpenAI
load_dotenv()

GOOGLE_DRIVE_FOLDER_ID = "1Byz9xJDRhcc4BjzTmNdTrAnwTlYykU4O"
SHEET_ID = "1E30lwiwyz90fHXr1E4jLlvbT-suIhv3aAhVjj2fhyMs"

@tool
def build_file_catalog() -> list:
    """
    Returns a list of all publicly visible filenames inside a Google Drive folder.
    """
    print("Building file catalog using Drive API...")
    folder_id = GOOGLE_DRIVE_FOLDER_ID

    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials

    creds = get_google_credentials()
    service = build("drive", "v3", credentials=creds)

    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(
        q=query,
        fields="files(name)"
    ).execute()

    files = results.get("files", [])
    file_names = [f["name"] for f in files]
    print(file_names)
    return file_names

@tool
def fetch_weekly_calendar_events() -> str:
    """
    Fetches all Google Calendar events for the current week (UTC).
    """
    print("Fetching calendar events for the current week...")

    from datetime import datetime, timedelta, timezone
    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials

    creds = get_google_credentials()
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(timezone.utc)

    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    end_of_week = start_of_week + timedelta(days=7)

    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_of_week.isoformat(),
        timeMax=end_of_week.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])

    if not events:
        return "No events scheduled for this week."

    formatted = []
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        formatted.append(
            f"- {event.get('summary', 'No title')} | {start} → {end}"
        )

    return "Events for the current week:\n" + "\n".join(formatted)

@tool
def create_google_meet_link() -> str:
    """
    Creates a Google Meet link and returns the meeting URL.
    """
    print("Creating Google Meet link...")

    from datetime import datetime, timedelta, timezone
    import uuid
    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials

    creds = get_google_credentials()
    service = build("calendar", "v3", credentials=creds)

    start_time = datetime.now(timezone.utc)
    end_time = start_time + timedelta(days=7)

    event = {
        "summary": "Meeting created by AI Assistant",
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": "UTC",
        },
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {
                    "type": "hangoutsMeet"
                },
            }
        },
    }

    created_event = service.events().insert(
        calendarId="primary",
        body=event,
        conferenceDataVersion=1
    ).execute()

    return created_event.get("hangoutLink", "Failed to create Google Meet link.")

@tool
def fetch_drive_file(file_base_name: str) -> str:
    """
    Retrieves a Google Drive link for any file whose name partially matches the string.
    """
    print("Fetching Drive file using Drive API...")

    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials

    creds = get_google_credentials()
    service = build("drive", "v3", credentials=creds)

    results = service.files().list(
        q=f"name contains '{file_base_name}' and trashed = false",
        fields="files(id, name, mimeType, webViewLink)",
        pageSize=10
    ).execute()

    files = results.get("files", [])

    if not files:
        return f"No files found containing '{file_base_name}'."

    file = files[0]
    return file.get("webViewLink", f"No accessible link for '{file['name']}'")

@tool
def query_google_sheet(query: str) -> str:
    """
    Queries the student Google Sheet and answers using OpenAI gpt-4o-mini.
    """
    print(f"Querying Google Sheet with: {query}...")
    sheet_id = SHEET_ID

    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

    try:
        response = requests.get(csv_url)
        response.raise_for_status()
    except Exception:
        return (
            "Error: Could not access the sheet.\n"
            "Make sure it is set to: Anyone with the link → Viewer."
        )

    client = OpenAI(
        api_key=os.getenv("OPENAI_API"))

    prompt = f"""
    You are an assistant answering questions based ONLY on the spreadsheet data below.
    
    Spreadsheet data (CSV):
    {response.text}

    User question:
    {query}

    Return only what the user asked for (names, emails, rows, etc).

    If asked for a specific person, return their entire row.

    If asked for a list of students from a specific course or deprartment, return their names and emails only.
    The course code must strictly match
    
    If the answer is not present, say "Not found in the sheet."
    """
    try:
        ai_response = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        return ai_response.output_text.strip()

    except Exception as e:
        print("OpenAI error:", e)
        return "Error: AI processing failed."

@tool
def email_students(to: str, subject: str, body: str) -> str:
    """
    Sends an email to one or more recipients using Gmail API.
    """
    print(f"Sending email to: {to}...")

    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials
    from email.mime.text import MIMEText

    CREDS = get_google_credentials()
    service = build("gmail", "v1", credentials=CREDS)

    recipients = [to] if isinstance(to, str) else to

    for receiver in recipients:
        message = MIMEText(body)
        message["to"] = receiver
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

    return f"Emails sent to {', '.join(recipients)}"

@tool
def web_search(query: str) -> str:
    """
    Searches the web for the given query.
    Args:
        query (str): The search query.
    Returns:
        str: The search results
    """
    from langchain_community.tools import DuckDuckGoSearchRun
    search = DuckDuckGoSearchRun()
    print("Searching the web for:", query)
    return search.invoke(query)
