import os
import threading
import re
import numpy as np
import base64
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from openai import OpenAI
load_dotenv()

# Each user's own Drive is searched for these names (ponytail: name convention, no settings UI).
COURSE_FOLDER_NAME = "ProfDux Courses"
STUDENT_SHEET_NAME = "ProfDux Students"


def _find_in_my_drive(service, name, mime):
    files = service.files().list(
        q=f"name = '{name}' and mimeType = '{mime}' and trashed = false and 'me' in owners",
        fields="files(id)", pageSize=1,
    ).execute().get("files", [])
    return files[0]["id"] if files else None

_index_cache = {}  # (user, sheet, modifiedTime) -> (rows, embeddings); lives until restart
TOP_K = 40


def _embed(client, texts):
    out = []
    for i in range(0, len(texts), 500):
        r = client.embeddings.create(model="text-embedding-3-small", input=texts[i:i + 500])
        out += [d.embedding for d in r.data]
    return np.array(out)


def _sheet_rows(config, sheet_id):
    """Every tab, any layout: first non-empty row of a tab = headers, blank/duplicate headers get 'colN'."""
    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials

    sheets = build("sheets", "v4", credentials=get_google_credentials(config)).spreadsheets()
    titles = [t["properties"]["title"] for t in sheets.get(spreadsheetId=sheet_id, fields="sheets.properties.title").execute()["sheets"]]
    rows = []
    for tab in sheets.values().batchGet(spreadsheetId=sheet_id, ranges=[f"'{t}'" for t in titles]).execute().get("valueRanges", []):
        values = [r for r in tab.get("values", []) if any(str(c).strip() for c in r)]
        if not values:
            continue
        name = tab["range"].split("!")[0].strip("'")
        head = []
        for i, h in enumerate(values[0]):
            h = str(h).strip()
            head.append(h if h and h not in head else f"col{i + 1}")
        for r in values[1:]:
            cells = [f"{head[i] if i < len(head) else f'col{i + 1}'}: {c}" for i, c in enumerate(r) if str(c).strip()]
            rows.append(" | ".join([f"Tab: {name}"] + cells))
    return rows


_locks = {}


def _get_index(service, client, config, sheet_id):
    modified = service.files().get(fileId=sheet_id, fields="modifiedTime").execute()["modifiedTime"]
    key = (config["configurable"]["user_id"], sheet_id, modified)
    with _locks.setdefault(key, threading.Lock()):  # a query arriving mid-warmup waits instead of embedding twice
        if key not in _index_cache:
            rows = _sheet_rows(config, sheet_id)
            _index_cache[key] = (rows, _embed(client, rows) if rows else None)
    return _index_cache[key]


def warm_sheet(user_id):
    """Call start: build the user's sheet index in the background so the first question is fast."""
    def work():
        from googleapiclient.discovery import build
        from agent.tools.oauth.google import get_google_credentials
        config = {"configurable": {"user_id": user_id}}
        try:
            service = build("drive", "v3", credentials=get_google_credentials(config))
            sheet_id = _find_in_my_drive(service, STUDENT_SHEET_NAME, "application/vnd.google-apps.spreadsheet")
            if sheet_id:
                _get_index(service, OpenAI(api_key=os.getenv("OPENAI_API")), config, sheet_id)
        except Exception as e:
            print("warm-up failed:", e)
    threading.Thread(target=work, daemon=True).start()


def _retrieve_rows(service, client, config, sheet_id, query):
    """RAG: one row = one chunk. Embeddings + exact-token boost (codes like CIS101 / names embed poorly)."""
    rows, emb = _get_index(service, client, config, sheet_id)
    if not rows:
        return []

    q = _embed(client, [query])[0]
    sim = emb @ q / (np.linalg.norm(emb, axis=1) * np.linalg.norm(q))
    low = [r.lower() for r in rows]
    tokens = {t for t in re.findall(r"\w+", query.lower()) if len(t) >= 3}
    # drop words found in nearly every row (column names etc.), they say nothing about which rows matter
    tokens = {t for t in tokens if sum(t in r for r in low) <= 0.9 * len(rows)}
    hits = np.array([sum(t in r for t in tokens) for r in low])
    # no row cap: EVERY exact-token match is a candidate, plus the TOP_K most similar for fuzzy questions
    keep = set(np.flatnonzero(hits)) | set(np.argsort(-(sim + 0.3 * hits))[:TOP_K])
    return [rows[i] for i in sorted(keep)]


def ensure_workspace(creds):
    """Called at sign-in: create the user's course folder and student sheet if they don't have them yet."""
    from googleapiclient.discovery import build

    drive = build("drive", "v3", credentials=creds)
    if not _find_in_my_drive(drive, COURSE_FOLDER_NAME, "application/vnd.google-apps.folder"):
        drive.files().create(body={"name": COURSE_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}).execute()
    if not _find_in_my_drive(drive, STUDENT_SHEET_NAME, "application/vnd.google-apps.spreadsheet"):
        sheet = drive.files().create(body={"name": STUDENT_SHEET_NAME, "mimeType": "application/vnd.google-apps.spreadsheet"}).execute()
        build("sheets", "v4", credentials=creds).spreadsheets().values().update(
            spreadsheetId=sheet["id"], range="A1", valueInputOption="RAW",
            body={"values": [["Name", "Email", "Course", "Department"]]},
        ).execute()


@tool
def build_file_catalog(config: RunnableConfig) -> list:
    """
    Returns a list of all publicly visible filenames inside a Google Drive folder.
    """
    print("Building file catalog using Drive API...")
    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials

    creds = get_google_credentials(config)
    service = build("drive", "v3", credentials=creds)

    folder_id = _find_in_my_drive(service, COURSE_FOLDER_NAME, "application/vnd.google-apps.folder")
    if not folder_id:
        return f"No Drive folder named '{COURSE_FOLDER_NAME}' in your account."

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
def fetch_weekly_calendar_events(config: RunnableConfig) -> str:
    """
    Fetches all Google Calendar events for the current week (UTC).
    """
    print("Fetching calendar events for the current week...")

    from datetime import datetime, timedelta, timezone
    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials

    creds = get_google_credentials(config)
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
def create_google_meet_link(config: RunnableConfig) -> str:
    """
    Creates a Google Meet link and returns the meeting URL.
    """
    print("Creating Google Meet link...")

    from datetime import datetime, timedelta, timezone
    import uuid
    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials

    creds = get_google_credentials(config)
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
def fetch_drive_file(file_base_name: str, config: RunnableConfig) -> str:
    """
    Retrieves a Google Drive link for any file whose name partially matches the string.
    """
    print("Fetching Drive file using Drive API...")

    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials

    creds = get_google_credentials(config)
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
def query_google_sheet(query: str, config: RunnableConfig) -> str:
    """
    Queries the logged-in user's student Google Sheet and answers using OpenAI gpt-4o-mini.
    """
    print(f"Querying Google Sheet with: {query}...")
    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials

    service = build("drive", "v3", credentials=get_google_credentials(config))
    sheet_id = _find_in_my_drive(service, STUDENT_SHEET_NAME, "application/vnd.google-apps.spreadsheet")
    if not sheet_id:
        return f"No Google Sheet named '{STUDENT_SHEET_NAME}' in your account."

    client = OpenAI(api_key=os.getenv("OPENAI_API"))
    try:
        candidates = _retrieve_rows(service, client, config, sheet_id, query)
        if not candidates:
            return "Not found in the sheet."
        relevant = _filter_rows(client, query, candidates)
        if not relevant:
            return "Not found in the sheet."
        # the model can't count reliably, so the count is computed here and handed over as a fact
        hint = f"{query}\n(Verified: exactly {len(relevant)} rows in the sheet are relevant. Use this number for any count.)"
        return _map_reduce(client, hint, relevant)
    except Exception as e:
        print("Sheet query error:", e)
        return "Error: could not read or process the sheet."


def _ask(client, instructions, data, query):
    return client.responses.create(
        model="gpt-4o-mini",
        input=f"{instructions}\n\nData:\n{data}\n\nUser question:\n{query}",
    ).output_text.strip()


MAP_RULES = """Answer ONLY from the spreadsheet rows below (a slice of a larger sheet).
Return only what was asked (names, emails, rows...). For a specific person return their entire row.
For lists by course/department return the relevant fields only (usually names and emails); the course code must match strictly.
For counts, answer with the number only and do not list rows. If nothing here is relevant, reply exactly: NONE"""

REDUCE_RULES = """Below are partial answers, each computed from a different slice of one sheet.
Merge them into ONE final answer to the question: combine lists, remove duplicates, add up counts. Do not invent anything."""


def _filter_rows(client, query, rows, batch=150):
    """Step 1: the model only picks WHICH numbered rows matter (reliable); everything after works on those."""
    import json
    from concurrent.futures import ThreadPoolExecutor

    def pick(start):
        data = "\n".join(f"[{i}] {r}" for i, r in enumerate(rows[start:start + batch], start))
        out = _ask(client, "Below are numbered spreadsheet rows. Return a JSON list of the numbers of EVERY row that contains "
                           "information needed to answer the question (e.g. the row of the person asked about, or every row "
                           "of the course asked about; codes and names must match strictly). Example: [3, 17]. "
                           "Return [] only if no row at all is about the question. JSON only.", data, query)
        try:
            return json.loads(out[out.index("["):out.rindex("]") + 1])
        except ValueError:
            return []

    with ThreadPoolExecutor(8) as pool:
        ids = sorted({i for part in pool.map(pick, range(0, len(rows), batch)) for i in part if isinstance(i, int) and 0 <= i < len(rows)})
    return [rows[i] for i in ids]


def _map_reduce(client, query, rows, batch=150):
    """Any number of candidate rows: answer each slice in parallel, then merge the partial answers."""
    from concurrent.futures import ThreadPoolExecutor

    slices = ["\n".join(rows[i:i + batch]) for i in range(0, len(rows), batch)]
    with ThreadPoolExecutor(8) as pool:
        parts = [a for a in pool.map(lambda d: _ask(client, MAP_RULES, d, query), slices) if a != "NONE"]
    if not parts:
        return "Not found in the sheet."
    while len(parts) > 1:  # merge in groups so the merge step never overflows either
        groups = ["\n---\n".join(parts[i:i + 20]) for i in range(0, len(parts), 20)]
        parts = [_ask(client, REDUCE_RULES, g, query) if "\n---\n" in g else g for g in groups]
    return parts[0]


@tool
def email_students(to: str, subject: str, body: str, config: RunnableConfig) -> str:
    """
    Sends an email to one or more recipients using Gmail API.
    """
    print(f"Sending email to: {to}...")

    from googleapiclient.discovery import build
    from agent.tools.oauth.google import get_google_credentials
    from email.mime.text import MIMEText

    CREDS = get_google_credentials(config)
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
