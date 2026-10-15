"""Reads settings from a .env file (if there is one) and from the environment."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent


def load_env(path=None):
    """Tiny .env reader so we don't need another dependency. Real environment variables win."""
    path = Path(path) if path else BASE / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
