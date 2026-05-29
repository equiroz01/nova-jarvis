from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    gemini_api_key: str = ""
    google_cloud_project: Optional[str] = None
    google_application_credentials: Optional[str] = None

    allowed_origins: str = "*"
    log_level: str = "INFO"

    # Google OAuth (Calendar/Gmail)
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_refresh_token: Optional[str] = None

    # Home Assistant
    home_assistant_url: Optional[str] = None
    home_assistant_token: Optional[str] = None

    # Alexa
    alexa_skill_id: Optional[str] = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
