"""Entry point for running Provenance Guard locally.

Loads environment variables from a local ``.env`` file (never committed), builds
the application via the factory, and runs the development server.
"""

from __future__ import annotations

from dotenv import load_dotenv

from provenance_guard import create_app
from provenance_guard.config import Config

load_dotenv()

app = create_app(Config())


if __name__ == "__main__":
    # Development server only. Use a production WSGI server for deployment.
    app.run(host="127.0.0.1", port=5000, debug=False)
