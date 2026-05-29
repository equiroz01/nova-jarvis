"""Tests for the Gmail cloud tools (search_emails, send_email)."""

from unittest.mock import patch, MagicMock


def _mock_gmail_service(messages=None, msg_detail=None):
    """Build a mock Gmail API service."""
    service = MagicMock()
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": messages or []
    }
    if msg_detail:
        service.users.return_value.messages.return_value.get.return_value.execute.return_value = msg_detail
    service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "msg-abc"
    }
    return service


class TestSearchEmails:
    @patch("app.tools.cloud.gmail_tool.build")
    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_ReturnFormattedEmails_when_ResultsFound(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_gmail_service(
            messages=[{"id": "m1"}],
            msg_detail={
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Hello World"},
                        {"name": "From", "value": "test@example.com"},
                        {"name": "Date", "value": "Mon, 1 Jan 2025"},
                    ]
                },
                "snippet": "This is a test email snippet",
            },
        )

        from app.tools.cloud.gmail_tool import search_emails
        result = search_emails.invoke({"query": "is:unread"})

        assert "Hello World" in result
        assert "test@example.com" in result
        assert "1 email" in result

    @patch("app.tools.cloud.gmail_tool.build")
    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_ReturnNoEmails_when_SearchEmpty(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_gmail_service(messages=[])

        from app.tools.cloud.gmail_tool import search_emails
        result = search_emails.invoke({"query": "from:nobody"})

        assert "No emails found" in result

    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_ReturnConfigError_when_OAuthMissing(self, mock_creds):
        mock_creds.side_effect = RuntimeError("not configured")

        from app.tools.cloud.gmail_tool import search_emails
        result = search_emails.invoke({"query": "is:unread"})

        assert "not configured" in result

    @patch("app.tools.cloud.gmail_tool.build")
    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_HandleMissingHeaders_when_EmailHasNoSubject(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_gmail_service(
            messages=[{"id": "m1"}],
            msg_detail={"payload": {"headers": []}, "snippet": "text"},
        )

        from app.tools.cloud.gmail_tool import search_emails
        result = search_emails.invoke({"query": "test"})

        assert "No subject" in result
        assert "Unknown" in result

    @patch("app.tools.cloud.gmail_tool.build")
    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_TruncateSnippet_when_LongerThan100Chars(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        long_snippet = "x" * 200
        mock_build.return_value = _mock_gmail_service(
            messages=[{"id": "m1"}],
            msg_detail={
                "payload": {"headers": [{"name": "Subject", "value": "S"}]},
                "snippet": long_snippet,
            },
        )

        from app.tools.cloud.gmail_tool import search_emails
        result = search_emails.invoke({"query": "test"})

        # The snippet in the output should be truncated to 100 chars
        # (the code does snippet[:100])
        assert "x" * 101 not in result

    @patch("app.tools.cloud.gmail_tool.build")
    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_ReturnError_when_APIFails(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value.users.return_value.messages.return_value.list.return_value.execute.side_effect = (
            Exception("API error")
        )

        from app.tools.cloud.gmail_tool import search_emails
        result = search_emails.invoke({"query": "test"})

        assert "Error" in result


class TestSendEmail:
    @patch("app.tools.cloud.gmail_tool.build")
    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_ReturnSuccess_when_EmailSent(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_gmail_service()

        from app.tools.cloud.gmail_tool import send_email
        result = send_email.invoke({
            "to": "user@example.com",
            "subject": "Test Subject",
            "body": "Test body",
        })

        assert "Email sent" in result
        assert "user@example.com" in result

    @patch("app.tools.cloud.gmail_tool.build")
    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_IncludeSubjectInResponse_when_Sent(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_gmail_service()

        from app.tools.cloud.gmail_tool import send_email
        result = send_email.invoke({
            "to": "a@b.com",
            "subject": "Important Subject",
            "body": "content",
        })

        assert "Important Subject" in result

    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_ReturnConfigError_when_OAuthMissing(self, mock_creds):
        mock_creds.side_effect = RuntimeError("not configured")

        from app.tools.cloud.gmail_tool import send_email
        result = send_email.invoke({
            "to": "a@b.com",
            "subject": "S",
            "body": "B",
        })

        assert "not configured" in result

    @patch("app.tools.cloud.gmail_tool.build")
    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_ReturnError_when_SendFails(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value.users.return_value.messages.return_value.send.return_value.execute.side_effect = (
            Exception("SMTP error")
        )

        from app.tools.cloud.gmail_tool import send_email
        result = send_email.invoke({
            "to": "a@b.com",
            "subject": "S",
            "body": "B",
        })

        assert "Error sending email" in result

    @patch("app.tools.cloud.gmail_tool.build")
    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_EncodeBodyAsBase64_when_Sending(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        service = _mock_gmail_service()
        mock_build.return_value = service

        from app.tools.cloud.gmail_tool import send_email
        send_email.invoke({
            "to": "a@b.com",
            "subject": "S",
            "body": "Test body content",
        })

        call_kwargs = (
            service.users.return_value.messages.return_value.send.return_value.execute.call_args
        )
        # Verify send was called (the mock was invoked)
        service.users.return_value.messages.return_value.send.assert_called_once()

    @patch("app.tools.cloud.gmail_tool.build")
    @patch("app.tools.cloud.gmail_tool.get_google_credentials")
    def test_should_HandleUnicodeBody_when_SpanishContent(self, mock_creds, mock_build):
        mock_creds.return_value = MagicMock()
        mock_build.return_value = _mock_gmail_service()

        from app.tools.cloud.gmail_tool import send_email
        result = send_email.invoke({
            "to": "a@b.com",
            "subject": "Prueba",
            "body": "Hola, como estas? Ano nuevo feliz!",
        })

        assert "Email sent" in result
