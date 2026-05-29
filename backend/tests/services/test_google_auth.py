"""Tests for the Google OAuth2 credentials helper."""

from unittest.mock import patch, MagicMock

import pytest


class TestGetGoogleCredentials:
    @patch("app.services.google_auth.GoogleRequest")
    @patch("app.services.google_auth.Credentials")
    def test_should_ReturnCredentials_when_ConfigIsValid(self, mock_creds_cls, mock_request):
        mock_creds = MagicMock()
        mock_creds_cls.return_value = mock_creds

        from app.services.google_auth import get_google_credentials
        result = get_google_credentials()

        assert result is mock_creds
        mock_creds.refresh.assert_called_once()

    @patch("app.services.google_auth.settings")
    def test_should_RaiseRuntimeError_when_ClientIdMissing(self, mock_settings):
        mock_settings.google_client_id = None
        mock_settings.google_refresh_token = "some-token"

        from app.services.google_auth import get_google_credentials
        with pytest.raises(RuntimeError, match="OAuth not configured"):
            get_google_credentials()

    @patch("app.services.google_auth.settings")
    def test_should_RaiseRuntimeError_when_RefreshTokenMissing(self, mock_settings):
        mock_settings.google_client_id = "some-id"
        mock_settings.google_refresh_token = None

        from app.services.google_auth import get_google_credentials
        with pytest.raises(RuntimeError, match="OAuth not configured"):
            get_google_credentials()

    @patch("app.services.google_auth.settings")
    def test_should_RaiseRuntimeError_when_BothMissing(self, mock_settings):
        mock_settings.google_client_id = None
        mock_settings.google_refresh_token = None

        from app.services.google_auth import get_google_credentials
        with pytest.raises(RuntimeError):
            get_google_credentials()

    @patch("app.services.google_auth.GoogleRequest")
    @patch("app.services.google_auth.Credentials")
    def test_should_PassCorrectScopes_when_CreatingCredentials(self, mock_creds_cls, mock_request):
        mock_creds_cls.return_value = MagicMock()

        from app.services.google_auth import get_google_credentials, SCOPES
        get_google_credentials()

        call_kwargs = mock_creds_cls.call_args[1]
        assert call_kwargs["scopes"] == SCOPES

    @patch("app.services.google_auth.GoogleRequest")
    @patch("app.services.google_auth.Credentials")
    def test_should_UseCorrectTokenUri_when_CreatingCredentials(self, mock_creds_cls, mock_request):
        mock_creds_cls.return_value = MagicMock()

        from app.services.google_auth import get_google_credentials
        get_google_credentials()

        call_kwargs = mock_creds_cls.call_args[1]
        assert call_kwargs["token_uri"] == "https://oauth2.googleapis.com/token"

    @patch("app.services.google_auth.GoogleRequest")
    @patch("app.services.google_auth.Credentials")
    def test_should_RefreshToken_when_CalledSuccessfully(self, mock_creds_cls, mock_request):
        mock_creds = MagicMock()
        mock_creds_cls.return_value = mock_creds

        from app.services.google_auth import get_google_credentials
        get_google_credentials()

        mock_creds.refresh.assert_called_once_with(mock_request.return_value)

    @patch("app.services.google_auth.GoogleRequest")
    @patch("app.services.google_auth.Credentials")
    def test_should_PropagateError_when_RefreshFails(self, mock_creds_cls, mock_request):
        mock_creds = MagicMock()
        mock_creds.refresh.side_effect = Exception("Token expired permanently")
        mock_creds_cls.return_value = mock_creds

        from app.services.google_auth import get_google_credentials
        with pytest.raises(Exception, match="Token expired"):
            get_google_credentials()
