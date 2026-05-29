"""AWS Lambda function for the Jarvis Alexa Skill.
Forwards user queries to the Jarvis Cloud Run backend."""

import os
import logging
import requests

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_model.ui import SimpleCard

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BACKEND_URL = os.environ.get("JARVIS_BACKEND_URL", "https://jarvis-backend-xxxxx-uc.a.run.app")
BACKEND_TIMEOUT = 7  # Alexa has 8s limit, leave 1s buffer


def call_jarvis(query: str, session_id: str) -> str:
    """Call the Jarvis backend /chat endpoint."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/chat",
            json={"message": query, "session_id": session_id},
            timeout=BACKEND_TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("response", "I couldn't process that request.")
    except requests.exceptions.Timeout:
        return "I'm taking too long to respond. Please try a simpler question."
    except Exception as e:
        logger.error(f"Backend error: {e}")
        return "I'm having trouble connecting to my backend. Please try again later."


class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        speech = "Hello! I'm Jarvis. How can I help you?"
        return (
            handler_input.response_builder
            .speak(speech)
            .ask(speech)
            .set_card(SimpleCard("Jarvis", speech))
            .response
        )


class AskJarvisIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AskJarvisIntent")(handler_input)

    def handle(self, handler_input):
        slots = handler_input.request_envelope.request.intent.slots
        query = slots.get("query", None)

        if not query or not query.value:
            speech = "I didn't catch that. Could you repeat your question?"
            return handler_input.response_builder.speak(speech).ask(speech).response

        session_id = handler_input.request_envelope.session.user.user_id
        speech = call_jarvis(query.value, f"alexa-{session_id}")

        return (
            handler_input.response_builder
            .speak(speech)
            .ask("Is there anything else?")
            .set_card(SimpleCard("Jarvis", speech))
            .response
        )


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        speech = (
            "You can ask me about the time in any city, search the web, "
            "check your calendar, read your emails, or control your smart home devices. "
            "What would you like to do?"
        )
        return handler_input.response_builder.speak(speech).ask(speech).response


class CancelStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.CancelIntent")(handler_input) or \
               is_intent_name("AMAZON.StopIntent")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.speak("Goodbye, sir.").response


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        speech = "I'm not sure about that. Try asking me a question."
        return handler_input.response_builder.speak(speech).ask(speech).response


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.response


class AllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error(f"Exception: {exception}", exc_info=True)
        speech = "Sorry, I ran into an error. Please try again."
        return handler_input.response_builder.speak(speech).ask(speech).response


sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(AskJarvisIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(AllExceptionHandler())

handler = sb.lambda_handler()
