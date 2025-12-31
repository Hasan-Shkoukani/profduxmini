from flask import Flask, request, jsonify, render_template
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

call_memory = []


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/token", methods=["GET"])
def voice_token():
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
        "token": token.to_jwt()
    })


@app.route("/voice", methods=["GET", "POST"])
def answer_call():
    resp = VoiceResponse()

    # BARGE-IN ENABLED
    gather = Gather(
        input="speech",
        bargeIn=True, 
        speech_timeout="auto",
        action="/process_speech",
        language="en-US"
    )

    gather.say("Hello! I am Professor Dux Mini. How can I help you today?")
    resp.append(gather)

    return str(resp)


@app.route("/process_speech", methods=["POST"])
def process_speech():
    global call_memory

    user_text = request.values.get("SpeechResult", "")
    resp = VoiceResponse()

    if not user_text:
        resp.say("Sorry, I didn't hear anything. Please say that again.")
        resp.redirect("/voice")
        return str(resp)

    try:
        assistant_reply = run(
            str(call_memory) + f"\nUser: {user_text}"
        )

        call_memory.append({
            "user": user_text,
            "assistant": assistant_reply
        })
        call_memory = call_memory[-10:]

    except Exception as e:
        print("AI Error:", e)
        assistant_reply = "Sorry, something went wrong."

    gather = Gather(
        input="speech",
        bargeIn=True,
        speech_timeout="auto",
        action="/process_speech",
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
