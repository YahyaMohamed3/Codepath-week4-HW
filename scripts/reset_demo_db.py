"""Delete and re-initialize the local demo database.

Never touches test databases (those live in pytest temp dirs).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

from provenance_guard.config import Config
from provenance_guard.database import init_db


def reset(database_path: str | None = None) -> str:
    load_dotenv()
    config = Config()
    path = database_path or config.database_path
    if os.path.exists(path):
        os.remove(path)
        print(f"Removed existing database: {path}")
    init_db(path)
    print(f"Initialized fresh database: {path}")
    return path


if __name__ == "__main__":
    reset()
