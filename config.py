"""Configuration via environment variables + .env."""

import os
import re
import logging
from functools import lru_cache

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@lru_cache
def get_settings():
    return Settings()


class Settings:
    def __init__(self):
        self.email: str = os.getenv("VIPUBER_EMAIL", "")
        self.password: str = os.getenv("VIPUBER_PASSWORD", "")
        self.base_url: str = os.getenv("VIPUBER_BASE_URL", "https://booking.vipuber.net")
        self.customer_id: str = os.getenv("VIPUBER_CUSTOMER_ID", "447")
        self.api_key: str = os.getenv("API_KEY", "")
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8222"))
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "30"))

    def validate(self):
        missing = []
        errors = []
        if not self.email:
            missing.append("VIPUBER_EMAIL")
        elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", self.email):
            errors.append(f"VIPUBER_EMAIL '{self.email}' is not a valid email address")
        if not self.password:
            missing.append("VIPUBER_PASSWORD")
        if not self.api_key:
            missing.append("API_KEY")
        if missing:
            raise RuntimeError(
                f"Missing required config: {', '.join(missing)}. "
                f"Set them in .env or environment variables."
            )
        if errors:
            raise RuntimeError("Configuration validation errors:\n" + "\n".join(errors))
        if not self.customer_id.isdigit():
            raise RuntimeError(f"VIPUBER_CUSTOMER_ID '{self.customer_id}' must be a numeric ID")


def setup_logging():
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("vipuber")
