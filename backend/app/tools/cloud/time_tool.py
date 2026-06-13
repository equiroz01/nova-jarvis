from langchain.tools import tool
from datetime import datetime
import unicodedata
import pytz


# Curated fast-path aliases. Keys are city names the user is likely to ask for
# (including Spanish spellings); values are IANA timezone names. Anything not
# here falls back to a search across all of pytz, so coverage is effectively
# "any city/zone pytz knows" — this table just fixes the common/ambiguous ones.
CITY_TIMEZONES = {
    # English
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
    # Spanish names / spellings the model or user may send
    "tokio": "Asia/Tokyo",
    "londres": "Europe/London",
    "nueva york": "America/New_York",
    "los angeles ca": "America/Los_Angeles",
    "ciudad de mexico": "America/Mexico_City",
    "mexico": "America/Mexico_City",
    "sao paulo br": "America/Sao_Paulo",
    "moscu": "Europe/Moscow",
    "roma": "Europe/Rome",
    "lisboa": "Europe/Lisbon",
    "el cairo": "Africa/Cairo",
    "pekin": "Asia/Shanghai",
    "pequin": "Asia/Shanghai",
    "sidney": "Australia/Sydney",
    "ginebra": "Europe/Zurich",
    "bogota dc": "America/Bogota",
    "estambul": "Europe/Istanbul",
    "istanbul": "Europe/Istanbul",
    "singapur": "Asia/Singapore",
    "quito": "America/Guayaquil",        # Ecuador shares one zone
    "kansas city": "America/Chicago",
    "san francisco": "America/Los_Angeles",
    "miami": "America/New_York",
    "washington": "America/New_York",
}


def _normalize(text: str) -> str:
    """Lowercase, strip accents, drop separators — so 'Bogotá', 'bogota' and
    'Bogota_DC' compare equal-ish."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(ch for ch in text.lower() if ch.isalnum())


# Build {normalized city -> IANA name} from every pytz zone, using the last
# path segment ("America/New_York" -> "newyork"). Curated entries win on ties.
def _build_zone_index() -> dict:
    index = {}
    for tz in pytz.all_timezones:
        # Skip legacy single-token abbreviations (EST, GMT, UTC, Japan, Cuba...)
        # and the Etc/* offset zones — they are not real city names and cause
        # garbage substring hits ("Estambul" matching "EST").
        if "/" not in tz or tz.startswith("Etc/"):
            continue
        city = tz.split("/")[-1]
        index.setdefault(_normalize(city), tz)
    # Curated aliases override (e.g. "panama" -> America/Panama, not a collision)
    for alias, tz in CITY_TIMEZONES.items():
        index[_normalize(alias)] = tz
    return index


_ZONE_INDEX = _build_zone_index()


def _resolve_timezone(city: str) -> str | None:
    """Resolve a user-supplied city/zone to an IANA timezone name, or None."""
    raw = city.strip()

    # 1. Raw IANA name passed straight through ("Asia/Tokyo", "America/Bogota")
    if "/" in raw:
        for tz in pytz.all_timezones:
            if tz.lower() == raw.lower():
                return tz

    key = _normalize(raw)
    if not key:
        return None

    # 2. Exact normalized match (curated alias or pytz city)
    if key in _ZONE_INDEX:
        return _ZONE_INDEX[key]

    # 3. Substring match — "buenos" finds "buenosaires", "mexicocity" finds
    #    "mexico". Require the matched key to be >= 4 chars so short, generic
    #    fragments don't latch onto unrelated cities.
    candidates = [
        v for k, v in _ZONE_INDEX.items()
        if len(k) >= 4 and (key in k or k in key)
    ]
    if candidates:
        # Prefer the shortest match (closest to an exact city name)
        return min(candidates, key=len)

    return None


@tool
def get_time(city: str) -> str:
    """Returns the current time in a given city, country capital, or IANA
    timezone. Accepts English or Spanish names ('Tokyo'/'Tokio', 'London'/
    'Londres') and raw zone names ('Asia/Tokyo'). Covers any city pytz knows."""
    try:
        tz_name = _resolve_timezone(city)
        if tz_name is None:
            return (
                f"No pude encontrar la zona horaria de '{city}'. "
                "Prueba con el nombre de una ciudad importante o el país."
            )

        timezone = pytz.timezone(tz_name)
        now = datetime.now(timezone)
        # Display the city the user asked for, plus the zone abbrev/offset.
        label = city.strip().title()
        return (
            f"La hora actual en {label} ({tz_name}) es "
            f"{now.strftime('%I:%M %p')}, {now.strftime('%A %d %b')} "
            f"[{now.strftime('%Z %z')}]."
        )
    except Exception as e:
        return f"Error getting time: {e}"
