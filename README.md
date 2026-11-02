# ProfDuxMini

A voice-driven AI teaching assistant for university staff. Sign in with Google, call it from the browser, say what you need, and it acts on your own Google Workspace: looks up students, finds course files, sends emails, checks your calendar and creates Google Meet links.

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
| `query_google_sheet` | Answers questions about students and lecturers from your `ProfDux Students` sheet using retrieval over every row (any number of rows, any columns, all tabs) |
| `build_file_catalog` | Lists the files in your `ProfDux Courses` Drive folder |
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
  tools/oauth/google.py  per-user Google token storage and refresh
templates/, static/      web page with the "Start Call" button
requirements.txt
```

## Setup

Requirements: Python 3.10+, a Twilio account, an OpenAI API key and a Google Cloud project.

```bash
git clone https://github.com/Hasan-Shkoukani/profduxmini.git
cd profduxmini
pip install -r requirements.txt
```

### 1. Google Cloud (once, by the developer)

Users sign in with their own Google accounts, so you only create **one OAuth client for the app**, not one per user.

1. Create a project and enable the Drive, Sheets, Gmail and Calendar APIs.
2. Configure the OAuth consent screen. While it is in "Testing" mode, add every account that will sign in as a test user.
3. Create an OAuth client of type **Web application** and add the redirect URI `http://localhost:5000/oauth2callback` (use your public URL if you expose the app).
4. Download the client JSON and save it as `agent/tools/oauth/credentials.json`. It is gitignored.

You do not create `token.json`. Each user's token is saved automatically on sign-in in `agent/tools/oauth/tokens/` (also gitignored).

### 2. Environment variables (or a `.env` file)

```bash
export TWILIO_ACCOUNT_SID=...
export TWILIO_API_KEY=...
export TWILIO_API_SECRET=...
export TWILIO_TWIML_APP_SID=...
export OPENAI_API=...                  # OpenAI API key
export FLASK_SECRET=...                # any long random string, keeps logins across restarts
export GOOGLE_REDIRECT_URI=...         # optional, defaults to http://localhost:5000/oauth2callback
```

### 3. Twilio

In your TwiML App, set the Voice request URL to `https://<your-public-url>/voice`.

## How users get started

1. Open the site and click **Sign in with Google**, then accept the consent screens (Google shows an "unverified app" warning while the app is in testing).
2. On first sign-in the app creates two items in the user's own Drive: a folder `ProfDux Courses` and a Google Sheet `ProfDux Students` (header row Name, Email, Course, Department).
3. Add students to the sheet and course files to the folder. The sheet can use any columns and any number of tabs and rows.
4. Press **Start Call** and allow the microphone.

## How sheet questions work

Each sheet row is one chunk, embedded with `text-embedding-3-small` and cached per user until the sheet changes. The index is built in the background as soon as a call starts. A question selects every row that matches its keywords plus the most similar rows, answers each slice of 150 rows with `gpt-4o-mini` in parallel, then merges the partial answers. There is no row limit, but very large result sets cost more and take longer.

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
| GET | `/login`, `/oauth2callback`, `/logout` | Google sign-in flow |
| GET | `/token` | Issues a Twilio Voice access token (login required) |
| GET/POST | `/voice` | Answers the call and starts listening |
| POST | `/process_speech` | Runs the agent on what the caller said and speaks the reply |

## Example requests

- "Email all students in CIS101 that the homework is posted, and include the link."
- "What is on my calendar this week?"
- "Create a Meet link."
- "Send me the lecture 3 slides."

## Limitations

- Run with a single worker (`gunicorn -w 1`). Conversation memory and the sheet index live in process memory and are lost on restart.
- Google tokens are stored as plain files on disk.
- Gmail and Drive scopes are sensitive, so only listed test users can sign in unless the app goes through Google verification.
- Twilio gives webhooks about 15 seconds to answer, so a very heavy sheet query can time out.
- `create_google_meet_link` creates a placeholder event starting now and lasting a week, not a scheduled meeting.
- The calendar tool only reads events; it cannot create or edit them.
- Student data is sent to OpenAI for embedding and answering.

## Tech stack

Python, Flask, Twilio Voice, LangGraph, LangChain, OpenAI (`gpt-4o-mini`), Google Drive / Sheets / Gmail / Calendar APIs, DuckDuckGo search.

## Author

Hasan Shkoukani, Near East University.
