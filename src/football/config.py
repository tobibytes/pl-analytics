"""Settings, credentials and paths.

Credentials come from the environment, falling back to a ``.env`` file at the
project root. Nothing here raises on import: a missing key is only a problem
for the one source that needs it, and three of the four sources need none.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

#: Understat/FPL label a season by the year it starts, so 2026 is 2026/27.
CURRENT_SEASON = int(os.getenv("FOOTBALL_SEASON", "2026"))

CACHE_DIR = Path(os.getenv("FOOTBALL_CACHE_DIR", PROJECT_ROOT / ".cache"))
OUTPUT_DIR = Path(os.getenv("FOOTBALL_OUTPUT_DIR", PROJECT_ROOT / "output"))


class MissingCredential(RuntimeError):
    """A source needs an API key that is not configured."""

    def __init__(self, env_var: str, signup_url: str):
        super().__init__(
            f"{env_var} is not set.\n"
            f"  1. Get a free key: {signup_url}\n"
            f"  2. cp .env.example .env\n"
            f"  3. Put the key in .env as {env_var}=..."
        )


def football_data_token() -> str:
    """Token for football-data.org. Free tier, 10 requests/minute."""
    token = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    if not token:
        raise MissingCredential(
            "FOOTBALL_DATA_TOKEN", "https://www.football-data.org/client/register"
        )
    return token


def api_football_key() -> str:
    """Key for API-Football. Free tier cannot read seasons after 2024."""
    key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise MissingCredential(
            "API_FOOTBALL_KEY", "https://dashboard.api-football.com/register"
        )
    return key


def season_label(season: int = CURRENT_SEASON) -> str:
    """``2026`` -> ``"2026/27"``."""
    return f"{season}/{str(season + 1)[-2:]}"
