from flask import Flask, request, jsonify, render_template, session, redirect
from itsdangerous import URLSafeTimedSerializer, BadSignature
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests as g_requests
from agent.tools.tools import ensure_workspace, warm_sheet
from agent.tools.oauth.google import SCOPES, client_config, save_credentials
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Gather
from agent.agent import run
from flask_cors import CORS
import os

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates"
)

CORS(app)
app.secret_key = os.environ.get("FLASK_SECRET") or os.urandom(24)  # set FLASK_SECRET to keep logins across restarts
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/oauth2callback")
if REDIRECT_URI.startswith("http://localhost"):
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
signer = URLSafeTimedSerializer(app.secret_key)  # ties a Twilio call to the signed-in user


def make_flow():
    return Flow.from_client_config(client_config(), SCOPES, redirect_uri=REDIRECT_URI)


def call_user(auth):
    try:
        return signer.loads(auth, max_age=3600)
    except (BadSignature, TypeError):
        return None


@app.route("/login")
def login():
    flow = make_flow()
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    session["state"], session["verifier"] = state, flow.code_verifier
    return redirect(url)


@app.route("/oauth2callback")
def oauth2callback():
    if request.args.get("state") != session.get("state") or "error" in request.args:
        return redirect("/")
    flow = make_flow()
    flow.code_verifier = session.get("verifier")
    flow.fetch_token(authorization_response=request.url)
    info = id_token.verify_oauth2_token(
        flow.credentials.id_token, g_requests.Request(), flow.client_config["client_id"]
    )
    save_credentials(info["sub"], flow.credentials)
    try:
        ensure_workspace(flow.credentials)
    except Exception as e:  # sign-in still succeeds; tools will explain what is missing
        print("workspace setup failed:", e)
    session["user_id"], session["email"] = info["sub"], info.get("email")
    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_API_KEY = os.environ.get("TWILIO_API_KEY")
TWILIO_API_SECRET = os.environ.get("TWILIO_API_SECRET")
TWILIO_TWIML_APP_SID = os.environ.get("TWILIO_TWIML_APP_SID")

if not all([
    TWILIO_ACCOUNT_SID,
    TWILIO_API_KEY,
    TWILIO_API_SECRET,
    TWILIO_TWIML_APP_SID
]):
    raise EnvironmentError("Twilio credentials are not set.")

call_memory = {}  # per user


@app.route("/")
def index():
    return render_template("index.html", email=session.get("email"))


@app.route("/token", methods=["GET"])
def voice_token():
    if "user_id" not in session:
        return jsonify({"error": "login required"}), 401
    identity = "user_" + os.urandom(4).hex()

    token = AccessToken(
        TWILIO_ACCOUNT_SID,
        TWILIO_API_KEY,
        TWILIO_API_SECRET,
        identity=identity
    )

    voice_grant = VoiceGrant(
        outgoing_application_sid=TWILIO_TWIML_APP_SID,
        incoming_allow=True
    )
    token.add_grant(voice_grant)

    return jsonify({
        "identity": identity,
        "token": token.to_jwt(),
        "auth": signer.dumps(session["user_id"])
    })


@app.route("/voice", methods=["GET", "POST"])
def answer_call():
    resp = VoiceResponse()
    auth = request.values.get("auth")
    user_id = call_user(auth)
    if not user_id:
        resp.say("Please sign in with Google first.")
        return str(resp)
    warm_sheet(user_id)  # no-op when already cached

    # BARGE-IN ENABLED
    gather = Gather(
        input="speech",
        bargeIn=True, 
        speech_timeout="auto",
        action=f"/process_speech?auth={auth}",
        language="en-US"
    )

    gather.say("Hello! I am Professor Dux Mini. How can I help you today?")
    resp.append(gather)

    return str(resp)


@app.route("/process_speech", methods=["POST"])
def process_speech():
    auth = request.args.get("auth")
    user_id = call_user(auth)
    user_text = request.values.get("SpeechResult", "")
    resp = VoiceResponse()
    if not user_id:
        resp.say("Please sign in with Google first.")
        return str(resp)

    if not user_text:
        resp.say("Sorry, I didn't hear anything. Please say that again.")
        resp.redirect(f"/voice?auth={auth}")
        return str(resp)

    try:
        assistant_reply = run(
            str(call_memory.get(user_id, [])) + f"\nUser: {user_text}", user_id
        )

        call_memory[user_id] = (call_memory.get(user_id, []) + [{
            "user": user_text,
            "assistant": assistant_reply
        }])[-10:]

    except Exception as e:
        print("AI Error:", e)
        assistant_reply = "Sorry, something went wrong."

    gather = Gather(
        input="speech",
        bargeIn=True,
        speech_timeout="auto",
        action=f"/process_speech?auth={auth}",
        language="en-US"
    )
    gather.say(assistant_reply)
    resp.append(gather)

    return str(resp)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )
