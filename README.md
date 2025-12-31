# AI Assistant

An AI-powered virtual assistant that can help with a variety of tasks, including:

- Fetching files from Google Drive
- Querying data from a Google Sheet
- Sending emails
- Creating Google Meet links
- Searching the web
- And more!

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/HasanShkoukani/ProfDuxMini.git
   ```
2. Navigate to the project directory:
   ```
   cd ProfDuxMini
   ```
3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Set the necessary environment variables:
   ```
   export TWILIO_ACCOUNT_SID=your_twilio_account_sid
   export TWILIO_API_KEY=your_twilio_api_key
   export TWILIO_API_SECRET=your_twilio_api_secret
   export TWILIO_TWIML_APP_SID=your_twilio_twiml_app_sid
   export OPENAI_API=your_openai_api_key
   ```
5. Set the Google oauth credentials.json file


## Usage

1. Start the Flask application:
   ```
   python main.py
   ```
2. Run Ngrok Tunnel and Open the site.
3. Click the "Start Call" button to begin a voice interaction with the AI assistant.

## API

The AI assistant exposes the following API endpoints:

- `GET /token`: Generates a Twilio token for voice interactions.
- `GET /voice`: Handles incoming voice calls and initiates the conversation.
- `POST /process_speech`: Processes the user's speech input and generates a response.

## Contributing

1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Make your changes and commit them.
4. Push your branch to your forked repository.
5. Submit a pull request to the main repository.
