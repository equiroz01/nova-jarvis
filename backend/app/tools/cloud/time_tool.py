from langchain.tools import tool
from datetime import datetime
import pytz


CITY_TIMEZONES = {
    "new york": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "chicago": "America/Chicago",
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "madrid": "Europe/Madrid",
    "tokyo": "Asia/Tokyo",
    "sydney": "Australia/Sydney",
    "dubai": "Asia/Dubai",
    "mumbai": "Asia/Kolkata",
    "beijing": "Asia/Shanghai",
    "sao paulo": "America/Sao_Paulo",
    "mexico city": "America/Mexico_City",
    "toronto": "America/Toronto",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "bogota": "America/Bogota",
    "lima": "America/Lima",
    "santiago": "America/Santiago",
    "panama": "America/Panama",
    "santo domingo": "America/Santo_Domingo",
    "havana": "America/Havana",
    "seoul": "Asia/Seoul",
    "singapore": "Asia/Singapore",
    "hong kong": "Asia/Hong_Kong",
    "moscow": "Europe/Moscow",
    "cairo": "Africa/Cairo",
    "johannesburg": "Africa/Johannesburg",
    "amsterdam": "Europe/Amsterdam",
    "rome": "Europe/Rome",
    "lisbon": "Europe/Lisbon",
}


@tool
def get_time(city: str) -> str:
    """Returns the current time in a given city. Supports major world cities."""
    try:
        city_key = city.lower().strip()
        if city_key not in CITY_TIMEZONES:
            # Try partial match
            matches = [k for k in CITY_TIMEZONES if city_key in k or k in city_key]
            if matches:
                city_key = matches[0]
            else:
                available = ", ".join(c.title() for c in sorted(CITY_TIMEZONES.keys()))
                return f"I don't have the timezone for '{city}'. Available cities: {available}"

        timezone = pytz.timezone(CITY_TIMEZONES[city_key])
        current_time = datetime.now(timezone).strftime("%I:%M %p")
        return f"The current time in {city_key.title()} is {current_time}."
    except Exception as e:
        return f"Error getting time: {e}"
