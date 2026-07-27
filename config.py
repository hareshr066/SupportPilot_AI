import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application configuration settings validated via Pydantic.
    Loads values from environment variables or a local .env file.
    """
    # GitHub Personal Access Token. Can be None for unauthenticated access (low rate limits).
    github_token: Optional[str] = None
    
    # Directory where raw ingested data is saved
    raw_data_dir: str = "./data/raw"
    
    # Log level configuration (e.g. DEBUG, INFO, WARNING, ERROR)
    log_level: str = "INFO"

    # Pydantic Configuration to read from .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Allow extra env vars in system without validation errors
    )

# Instantiate a single global config object to be imported across the application
settings = Settings()
