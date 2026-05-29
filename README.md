# Jarvis - Voice AI Assistant

Hybrid cloud voice assistant powered by Google Gemini. Works with Alexa and Mac.

## Architecture

```
[Mac Client] --HTTP--> [FastAPI on Cloud Run] <--HTTP-- [Alexa Skill]
     WebSocket                 |
  [Local tools]          [Gemini 2.0 Flash + LangChain]
                               |
                         [Tools: search, time, calendar, gmail, smart home]
```

## Components

- **backend/** - FastAPI server with Gemini LLM, LangChain agent, and cloud tools
- **client/** - Mac client with wake word detection and local tool execution
- **alexa/** - Alexa Skill (Lambda) that forwards queries to the backend
- **deploy/** - Cloud Build config for Google Cloud Run

## Quick Start

### 1. Backend

```bash
cp .env.example .env
# Add your GEMINI_API_KEY to .env

cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8080
```

### 2. Test

```bash
curl http://localhost:8080/health
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What time is it in Tokyo?"}'
```

### 3. Mac Client

```bash
cd client
pip install -r requirements.txt
python client.py
```

### 4. Run Tests

```bash
cd backend
pip install -r requirements-test.txt
pytest -v
```

## Tools

| Tool | Type | Description |
|------|------|-------------|
| get_time | Cloud | Current time in 30+ cities |
| web_search | Cloud | DuckDuckGo search |
| get_upcoming_events | Cloud | Google Calendar events |
| create_calendar_event | Cloud | Create calendar events |
| search_emails | Cloud | Search Gmail |
| send_email | Cloud | Send email via Gmail |
| list_smart_devices | Cloud | List Home Assistant devices |
| control_device | Cloud | Control smart home devices |
| take_screenshot | Local | Screenshot via Mac client |
| read_screen_text | Local | OCR via Mac client |
| run_arp_scan | Local | Network scan via Mac client |
