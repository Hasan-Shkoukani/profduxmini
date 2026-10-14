# ProfDuxMini

A voice-driven AI teaching assistant for university staff. Call it from the browser, say what you need, and it acts on Google Workspace for you: looks up students, finds course files, sends emails, checks your calendar and creates Google Meet links.

Built as a miniature version of "Professor Dux", the Near East University AI agent.

## How it works

```
Browser (Twilio Voice) -> Flask /voice -> speech-to-text (Twilio Gather)
        -> LangGraph agent (GPT-4o-mini + tools) -> reply spoken back via Twilio
```

- **Voice interface:** Twilio Voice with speech recognition and barge-in, so you can interrupt the assistant. The last 10 turns are kept as conversation memory.
- **Agent:** a LangGraph loop (`agent` node -> `tools` node -> back to `agent`) running `gpt-4o-mini` through `langchain-openai`. The system prompt defines when each tool may be used and how replies should sound on a call.

## Tools

| Tool | What it does |
| --- | --- |
| `query_google_sheet` | Answers questions about students and lecturers from a Google Sheet (emails, departments, course lists) |
| `build_file_catalog` | Lists the files in a Google Drive course folder |
| `fetch_drive_file` | Returns a Drive link for the file whose name matches |
| `email_students` | Sends an email through the Gmail API. Recipients are looked up in the sheet; subject and body are generated if not given |
| `fetch_weekly_calendar_events` | Reads this week's Google Calendar events (UTC) |
| `create_google_meet_link` | Creates a calendar event with a Google Meet link and returns the URL |
| `web_search` | DuckDuckGo web search for general questions |

## Project structure

```
main.py                  Flask app and Twilio voice routes
agent/
  agent.py               LangGraph agent definition and run() entry point
  prompts/system.py      system prompt (persona, tool rules, spoken style)
  tools/tools.py         the seven tools above
  tools/oauth/google.py  Google OAuth credential loading
templates/, static/      web page with the "Start Call" button
requirements.txt
```

## Setup

Requirements: Python 3.10+, a Twilio account, an OpenAI API key and a Google Cloud project with the Drive, Sheets, Gmail and Calendar APIs enabled.

```bash
git clone https://github.com/Hasan-Shkoukani/profduxmini.git
cd profduxmini
pip install -r requirements.txt
```

Set the environment variables (or put the last one in a `.env` file):

```bash
export TWILIO_ACCOUNT_SID=...
export TWILIO_API_KEY=...
export TWILIO_API_SECRET=...
export TWILIO_TWIML_APP_SID=...
export OPENAI_API=...          # OpenAI API key
```

Then:

1. Put your Google OAuth `credentials.json` where `agent/tools/oauth/google.py` expects it.
2. In `agent/tools/tools.py`, replace `GOOGLE_DRIVE_FOLDER_ID` and `SHEET_ID` with your own folder and sheet. The sheet must be shared as "Anyone with the link -> Viewer" because it is read as a CSV export. Do not use a sheet containing real student data.
3. In your Twilio TwiML App, set the Voice request URL to `https://<your-public-url>/voice`.

## Run

```bash
python main.py            # starts Flask on port 5000
ngrok http 5000           # expose it so Twilio can reach /voice
```

Open the site and press **Start Call**.

## HTTP endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Web page with the call button |
| GET | `/token` | Issues a Twilio Voice access token |
| GET/POST | `/voice` | Answers the call and starts listening |
| POST | `/process_speech` | Runs the agent on what the caller said and speaks the reply |

## Example requests

- "Email all students in CIS101 that the homework is posted, and include the link."
- "What is on my calendar this week?"
- "Create a Meet link."
- "Send me the lecture 3 slides."

## Limitations

- Conversation memory is one global list shared by every caller, so it is meant for a single user or demo.
- `create_google_meet_link` creates a placeholder event starting now and lasting a week, not a scheduled meeting.
- The calendar tool only reads events; it cannot create or edit them.
- Student data is read from a link-shared sheet and sent to OpenAI for answering.

## Tech stack

Python, Flask, Twilio Voice, LangGraph, LangChain, OpenAI (`gpt-4o-mini`), Google Drive / Sheets / Gmail / Calendar APIs, DuckDuckGo search.

## Author

Hasan Shkoukani, Near East University.
