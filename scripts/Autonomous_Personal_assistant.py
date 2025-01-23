import os
import openai
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from datetime import datetime, timedelta
import spacy
from transformers import pipeline

# Initialize Flask App
app = Flask(__name__)

# Load NLP Model (spaCy for intent parsing, Hugging Face for text generation)
nlp = spacy.load("en_core_web_sm")
text_generator = pipeline("text-generation", model="gpt2")

# Google Calendar API Setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
credentials = None
if os.path.exists('token.pickle'):
    with open('token.pickle', 'rb') as token:
        credentials = pickle.load(token)
if not credentials or not credentials.valid:
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        credentials = flow.run_local_server(port=0)
    with open('token.pickle', 'wb') as token:
        pickle.dump(credentials, token)
calendar_service = build('calendar', 'v3', credentials=credentials)

# OpenAI GPT Integration
openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_response(prompt):
    """Generate a response using OpenAI GPT"""
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=150
    )
    return response.choices[0].text.strip()

@app.route('/parse-intent', methods=['POST'])
def parse_intent():
    """Parse user command and extract intent using spaCy"""
    data = request.json
    user_input = data.get('input')
    doc = nlp(user_input)

    # Extract entities and intent
    intent = None
    if "schedule" in user_input:
        intent = "schedule_meeting"
    elif "email" in user_input:
        intent = "respond_email"
    elif "reminder" in user_input:
        intent = "set_reminder"

    return jsonify({"intent": intent, "entities": [(ent.text, ent.label_) for ent in doc.ents]})

@app.route('/generate-email', methods=['POST'])
def generate_email():
    """Generate an email response based on user input"""
    data = request.json
    context = data.get('context')
    subject = data.get('subject', "")
    body_prompt = f"Write a professional email about: {subject}. Context: {context}"
    response = generate_response(body_prompt)
    return jsonify({"email_body": response})

@app.route('/add-event', methods=['POST'])
def add_event():
    """Add an event to Google Calendar"""
    data = request.json
    event = {
        'summary': data.get('summary'),
        'location': data.get('location', ''),
        'description': data.get('description', ''),
        'start': {
            'dateTime': data.get('start_time'),
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': data.get('end_time'),
            'timeZone': 'UTC',
        },
    }
    event_result = calendar_service.events().insert(calendarId='primary', body=event).execute()
    return jsonify({"event_id": event_result['id']})

@app.route('/set-reminder', methods=['POST'])
def set_reminder():
    """Set a reminder by adding a timed event to Google Calendar"""
    data = request.json
    reminder_time = datetime.utcnow() + timedelta(minutes=data.get('time_offset', 10))
    event = {
        'summary': data.get('summary', 'Reminder'),
        'description': data.get('description', ''),
        'start': {
            'dateTime': reminder_time.isoformat() + 'Z',
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': (reminder_time + timedelta(minutes=10)).isoformat() + 'Z',
            'timeZone': 'UTC',
        },
    }
    event_result = calendar_service.events().insert(calendarId='primary', body=event).execute()
    return jsonify({"reminder_id": event_result['id']})

@app.route('/get-suggestions', methods=['POST'])
def get_suggestions():
    """Provide proactive suggestions based on user patterns"""
    data = request.json
    user_context = data.get('context')
    suggestions_prompt = f"Based on the context: {user_context}, suggest useful actions."
    suggestions = generate_response(suggestions_prompt)
    return jsonify({"suggestions": suggestions})

@app.route('/view-upcoming-events', methods=['GET'])
def view_upcoming_events():
    """Retrieve upcoming events from Google Calendar"""
    now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    events_result = calendar_service.events().list(
        calendarId='primary', timeMin=now, maxResults=10, singleEvents=True,
        orderBy='startTime').execute()
    events = events_result.get('items', [])

    event_list = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        event_list.append({
            'summary': event['summary'],
            'start': start
        })

    return jsonify({"upcoming_events": event_list})

if __name__ == '__main__':
    app.run(debug=True)
