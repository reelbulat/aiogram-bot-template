import os


def _parse_allowed_users(raw: str) -> set[int]:
    if not raw.strip():
        return set()
    return {
        int(part.strip())
        for part in raw.split(",")
        if part.strip().isdigit()
    }


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ALLOWED_USERS = _parse_allowed_users(os.getenv("ALLOWED_USERS", ""))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")
