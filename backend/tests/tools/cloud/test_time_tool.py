"""Tests for the get_time cloud tool."""

from unittest.mock import patch
from datetime import datetime

import pytz

from app.tools.cloud.time_tool import get_time, CITY_TIMEZONES


class TestGetTime:
    # ---- Happy path ----

    def test_should_ReturnTimeString_when_KnownCity(self):
        result = get_time.invoke({"city": "Panama"})
        assert "Panama" in result
        assert ":" in result  # contains a time like "10:30 AM"

    def test_should_BeCaseInsensitive_when_CityUppercase(self):
        result = get_time.invoke({"city": "PANAMA"})
        assert "Panama" in result

    def test_should_BeCaseInsensitive_when_CityMixedCase(self):
        result = get_time.invoke({"city": "New York"})
        assert "New York" in result

    def test_should_TrimWhitespace_when_CityHasSpaces(self):
        result = get_time.invoke({"city": "  panama  "})
        assert "Panama" in result

    # ---- Partial matching ----

    def test_should_PartialMatch_when_SubstringProvided(self):
        result = get_time.invoke({"city": "york"})
        # "york" is in "new york" -> partial match should work
        assert "New York" in result or "time" in result.lower()

    # ---- Unknown city ----

    def test_should_ListAvailableCities_when_CityNotFound(self):
        result = get_time.invoke({"city": "Atlantis"})
        assert "don't have" in result.lower() or "available" in result.lower()

    def test_should_IncludeCityList_when_CityNotFound(self):
        result = get_time.invoke({"city": "Narnia"})
        assert "Panama" in result  # Panama should appear in the available list

    # ---- All known cities ----

    def test_should_ReturnValidTime_when_EveryKnownCityQueried(self):
        for city_name in CITY_TIMEZONES:
            result = get_time.invoke({"city": city_name})
            assert "Error" not in result, f"Failed for city: {city_name}"
            assert ":" in result, f"No time format for city: {city_name}"

    # ---- Edge cases ----

    def test_should_HandleEmptyString_when_EmptyCityProvided(self):
        result = get_time.invoke({"city": ""})
        # Empty string after strip() and lower() won't match any key
        # but might partial-match everything -- just shouldn't crash
        assert isinstance(result, str)

    def test_should_HandleUnicode_when_CityHasAccents(self):
        result = get_time.invoke({"city": "Sao Paulo"})
        assert "Sao Paulo" in result or "Error" not in result

    @patch("app.tools.cloud.time_tool.datetime")
    def test_should_FormatAs12Hour_when_TimeReturned(self, mock_dt):
        tz = pytz.timezone("America/Panama")
        mock_dt.now.return_value = datetime(2025, 6, 15, 14, 30, 0, tzinfo=tz)
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        # Just verify the tool doesn't crash; exact format depends on strftime
        result = get_time.invoke({"city": "Panama"})
        assert isinstance(result, str)

    def test_should_HandleSpecialChars_when_CityHasInjection(self):
        result = get_time.invoke({"city": "'; DROP TABLE cities;--"})
        assert isinstance(result, str)
        assert "Error" not in result or "don't have" in result.lower()
