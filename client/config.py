import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("JARVIS_BACKEND_URL", "http://localhost:8080")
CLIENT_ID = os.getenv("JARVIS_CLIENT_ID", "mac-client-01")
WAKE_WORD = os.getenv("JARVIS_WAKE_WORD", "jarvis")
MIC_INDEX = int(os.getenv("JARVIS_MIC_INDEX", "0")) if os.getenv("JARVIS_MIC_INDEX") else None
CONVERSATION_TIMEOUT = int(os.getenv("JARVIS_CONVERSATION_TIMEOUT", "30"))
