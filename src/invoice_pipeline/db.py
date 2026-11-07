"""Database connection from the .env file (never hard-code the password)."""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[2]


def get_engine():
    load_dotenv(ROOT / ".env")
    url = URL.create(
        "postgresql+psycopg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
    )
    # Time limits: a wait on a lock or a dead connection ends with an error instead of hanging silently.
    return create_engine(
        url,
        connect_args={"connect_timeout": 10, "options": "-c lock_timeout=15000 -c statement_timeout=60000"},
    )
