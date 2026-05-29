"""Tests for the calendar cloud tools (get_upcoming_events, create_calendar_event)."""

from unittest.mock import patch, MagicMock


def _mock_calendar_service(events_list=None):
    """Build a mock Google Calendar service."""
    service = MagicMock()
    events_result = {"items": events_list or []}
    service.events.return_value.list.return_value.execute.return_value = events_result
    service.events.return_value.insert.return_value.execute.return_value = {
        "htmlLink": "https://calendar.google.com/event/123"
    }
    return service


class TestGetUpcomingEvents:
    @patch("app.tools.cloud.calendar_tool.build")
    @patch("app.tools.cloud.calendar_tool.get_google_credentials")
    def test_should_ReturnEvents_when_EventsExist(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_calendar_service([
            {"start": {"dateTime": "2025-06-15T10:00:00"}, "summary": "Team standup"},
            {"start": {"date": "2025-06-15"}, "summary": "All-day event"},
        ])

        from app.tools.cloud.calendar_tool import get_upcoming_events
        result = get_upcoming_events.invoke({"days": 1})

        assert "Team standup" in result
        assert "All-day event" in result

    @patch("app.tools.cloud.calendar_tool.build")
    @patch("app.tools.cloud.calendar_tool.get_google_credentials")
    def test_should_ReturnNoEvents_when_CalendarIsEmpty(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_calendar_service([])

        from app.tools.cloud.calendar_tool import get_upcoming_events
        result = get_upcoming_events.invoke({"days": 1})

        assert "No events" in result

    @patch("app.tools.cloud.calendar_tool.get_google_credentials")
    def test_should_ReturnConfigError_when_OAuthNotSetUp(self, mock_creds):
        mock_creds.side_effect = RuntimeError("Google OAuth not configured")

        from app.tools.cloud.calendar_tool import get_upcoming_events
        result = get_upcoming_events.invoke({"days": 1})

        assert "not configured" in result.lower() or "OAuth" in result

    @patch("app.tools.cloud.calendar_tool.build")
    @patch("app.tools.cloud.calendar_tool.get_google_credentials")
    def test_should_ReturnError_when_APIFails(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value.events.return_value.list.return_value.execute.side_effect = (
            Exception("API quota exceeded")
        )

        from app.tools.cloud.calendar_tool import get_upcoming_events
        result = get_upcoming_events.invoke({"days": 1})

        assert "Error" in result

    @patch("app.tools.cloud.calendar_tool.build")
    @patch("app.tools.cloud.calendar_tool.get_google_credentials")
    def test_should_ClampDaysToMinimum1_when_ZeroOrNegative(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_calendar_service([])

        from app.tools.cloud.calendar_tool import get_upcoming_events
        # days=0 -> max(1, 0) = 1, so timedelta(days=1)
        result = get_upcoming_events.invoke({"days": 0})
        assert "No events" in result  # Doesn't crash

    @patch("app.tools.cloud.calendar_tool.build")
    @patch("app.tools.cloud.calendar_tool.get_google_credentials")
    def test_should_HandleMissingSummary_when_EventHasNoTitle(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_calendar_service([
            {"start": {"dateTime": "2025-06-15T10:00:00"}},  # No "summary" key
        ])

        from app.tools.cloud.calendar_tool import get_upcoming_events
        result = get_upcoming_events.invoke({"days": 1})

        assert "No title" in result


class TestCreateCalendarEvent:
    @patch("app.tools.cloud.calendar_tool.build")
    @patch("app.tools.cloud.calendar_tool.get_google_credentials")
    def test_should_ReturnSuccess_when_EventCreated(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_calendar_service()

        from app.tools.cloud.calendar_tool import create_calendar_event
        result = create_calendar_event.invoke({
            "title": "Test Meeting",
            "start_time": "2025-06-15T14:00:00",
            "end_time": "2025-06-15T15:00:00",
        })

        assert "Event created" in result
        assert "Test Meeting" in result
        assert "calendar.google.com" in result

    @patch("app.tools.cloud.calendar_tool.build")
    @patch("app.tools.cloud.calendar_tool.get_google_credentials")
    def test_should_IncludeDescription_when_Provided(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        service = _mock_calendar_service()
        mock_build.return_value = service

        from app.tools.cloud.calendar_tool import create_calendar_event
        create_calendar_event.invoke({
            "title": "Demo",
            "start_time": "2025-06-15T14:00:00",
            "end_time": "2025-06-15T15:00:00",
            "description": "Demo description",
        })

        body = service.events.return_value.insert.call_args[1]["body"]
        assert body["description"] == "Demo description"

    @patch("app.tools.cloud.calendar_tool.get_google_credentials")
    def test_should_ReturnConfigError_when_OAuthMissing(self, mock_creds):
        mock_creds.side_effect = RuntimeError("not configured")

        from app.tools.cloud.calendar_tool import create_calendar_event
        result = create_calendar_event.invoke({
            "title": "Test",
            "start_time": "2025-06-15T14:00:00",
            "end_time": "2025-06-15T15:00:00",
        })

        assert "not configured" in result

    @patch("app.tools.cloud.calendar_tool.build")
    @patch("app.tools.cloud.calendar_tool.get_google_credentials")
    def test_should_ReturnError_when_InsertFails(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value.events.return_value.insert.return_value.execute.side_effect = (
            Exception("quota exceeded")
        )

        from app.tools.cloud.calendar_tool import create_calendar_event
        result = create_calendar_event.invoke({
            "title": "Test",
            "start_time": "2025-06-15T14:00:00",
            "end_time": "2025-06-15T15:00:00",
        })

        assert "Error creating event" in result
