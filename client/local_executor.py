import json
import logging
import os
import subprocess
import threading
import time

import websocket
import mss
import mss.tools

logger = logging.getLogger(__name__)

SCREENSHOT_PATH = os.path.expanduser("~/jarvis_screenshot.png")


def _handle_screenshot() -> str:
    """Capture the screen and save to disk."""
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=SCREENSHOT_PATH)
        return f"Screenshot saved to {SCREENSHOT_PATH}"
    except Exception as e:
        return f"Screenshot error: {e}"


def _handle_ocr() -> str:
    """Run OCR on the latest screenshot."""
    try:
        import pytesseract
        from PIL import Image

        if not os.path.exists(SCREENSHOT_PATH):
            return "No screenshot found. Take a screenshot first."

        image = Image.open(SCREENSHOT_PATH)
        text = pytesseract.image_to_string(image)
        return text.strip() if text.strip() else "No text detected in the screenshot."
    except ImportError:
        return "OCR requires pytesseract and Pillow. Install them with: pip install pytesseract Pillow"
    except Exception as e:
        return f"OCR error: {e}"


def _handle_arp_scan() -> str:
    """Run arp -a to list network devices."""
    try:
        result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
        return result.stdout if result.stdout else "No devices found."
    except Exception as e:
        return f"ARP scan error: {e}"


ACTION_HANDLERS = {
    "screenshot": _handle_screenshot,
    "ocr": _handle_ocr,
    "arp_scan": _handle_arp_scan,
}


class LocalExecutor:
    """Connects to the backend WebSocket and handles local tool execution requests."""

    def __init__(self, backend_url: str, client_id: str):
        ws_url = backend_url.replace("http://", "ws://").replace("https://", "wss://")
        self.url = f"{ws_url}/ws/client/{client_id}"
        self.ws = None
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"Local executor connecting to {self.url}")

    def stop(self):
        self._running = False
        if self.ws:
            self.ws.close()

    def _run(self):
        while self._running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open,
                )
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")

            if self._running:
                logger.info("Reconnecting in 5 seconds...")
                time.sleep(5)

    def _on_open(self, ws):
        logger.info("WebSocket connected to backend")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)

            # Handle pong
            if data.get("type") == "pong":
                return

            action = data.get("action")
            request_id = data.get("request_id")

            if not action or not request_id:
                return

            logger.info(f"Executing local tool: {action}")

            handler = ACTION_HANDLERS.get(action)
            if handler:
                result = handler()
            else:
                result = f"Unknown action: {action}"

            ws.send(json.dumps({
                "request_id": request_id,
                "result": result,
            }))

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info(f"WebSocket closed: {close_status_code} {close_msg}")
