"""Tests for the pydantic-settings configuration."""

import os
from unittest.mock import patch


class TestSettings:
    def test_should_HaveDefaults_when_MinimalConfig(self):
        """Settings should have safe defaults for non-critical fields.

        We must clear the env vars set by the autouse fixture to test true defaults.
        """
        from app.config import Settings

        clean_env = {
            "GEMINI_API_KEY": "test",
            "ALLOWED_ORIGINS": "*",
            "LOG_LEVEL": "INFO",
        }
        # Remove all the keys the autouse fixture sets so defaults are tested
        remove_keys = [
            "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN",
            "HOME_ASSISTANT_URL", "HOME_ASSISTANT_TOKEN", "ALEXA_SKILL_ID",
        ]
        with patch.dict(os.environ, clean_env, clear=False):
            for k in remove_keys:
                os.environ.pop(k, None)
            s = Settings(_env_file=None)
            assert s.allowed_origins == "*"
            assert s.log_level == "INFO"
            assert s.home_assistant_url is None
            assert s.home_assistant_token is None
            assert s.alexa_skill_id is None

    def test_should_ReadFromEnv_when_EnvVarsSet(self):
        from app.config import Settings
        env = {
            "GEMINI_API_KEY": "key-123",
            "ALLOWED_ORIGINS": "http://localhost:3000",
            "LOG_LEVEL": "DEBUG",
            "HOME_ASSISTANT_URL": "http://ha.local:8123",
            "HOME_ASSISTANT_TOKEN": "ha-tok",
        }
        with patch.dict(os.environ, env, clear=False):
            s = Settings(_env_file=None)
            assert s.gemini_api_key == "key-123"
            assert s.allowed_origins == "http://localhost:3000"
            assert s.log_level == "DEBUG"
            assert s.home_assistant_url == "http://ha.local:8123"
            assert s.home_assistant_token == "ha-tok"

    def test_should_AllowEmptyGeminiKey_when_Default(self):
        from app.config import Settings
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            s = Settings(_env_file=None)
            assert s.gemini_api_key == ""

    def test_should_SplitOrigins_when_CommaSeparated(self):
        from app.config import Settings
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": "http://a.com,http://b.com"}, clear=False):
            s = Settings(_env_file=None)
            origins = s.allowed_origins.split(",")
            assert len(origins) == 2
            assert "http://a.com" in origins
            assert "http://b.com" in origins

    def test_should_AcceptOptionalNone_when_GoogleOAuthNotSet(self):
        from app.config import Settings
        env_override = {
            "GEMINI_API_KEY": "k",
        }
        remove_keys = [
            "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN",
        ]
        with patch.dict(os.environ, env_override, clear=False):
            for k in remove_keys:
                os.environ.pop(k, None)
            s = Settings(_env_file=None)
            assert s.google_client_id is None
            assert s.google_client_secret is None
            assert s.google_refresh_token is None
