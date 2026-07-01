"""Shared Flask extensions.

The limiter is created here without an app and initialized in the application
factory so route decorators can reference a stable instance.
"""

from __future__ import annotations

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=[],
)
