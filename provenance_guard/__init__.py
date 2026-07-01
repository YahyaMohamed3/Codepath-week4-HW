"""Provenance Guard application factory.

``create_app`` builds an isolated Flask app so tests can use temporary databases
and injected detectors without touching the developer's demo database or the
Groq API.
"""

from __future__ import annotations

import logging
import os

from flask import Flask, g, jsonify

from .config import Config
from .database import init_db
from .detection.llm_signal import GroqSemanticSignal
from .errors import APIError
from .extensions import limiter

logger = logging.getLogger(__name__)


def create_app(config: Config | None = None, detector=None) -> Flask:
    """Create and configure a Provenance Guard Flask application.

    Parameters
    ----------
    config:
        Optional :class:`Config`. If omitted one is built from the environment.
    detector:
        Optional object with ``analyze(text) -> dict``. If omitted a
        :class:`GroqSemanticSignal` is constructed from the config. Tests pass a
        fake detector so no API credits are consumed.
    """
    if config is None:
        config = Config()

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "..", "static"),
    )
    app.config["DATABASE_PATH"] = config.database_path
    app.config["GROQ_CONFIGURED"] = config.groq_configured
    app.config["SECRET_KEY"] = config.secret_key
    app.config["TESTING"] = config.testing
    app.config["RATELIMIT_ENABLED"] = config.rate_limits_enabled
    app.config["JSON_SORT_KEYS"] = False

    init_db(config.database_path)

    # Detector: injected fake in tests, real Groq signal otherwise.
    if detector is None:
        detector = GroqSemanticSignal(
            api_key=config.groq_api_key, model=config.groq_model
        )
    app.extensions["provenance_detector"] = detector

    limiter.init_app(app)

    from .routes import bp

    app.register_blueprint(bp)

    _register_error_handlers(app)
    _register_teardown(app)
    return app


def _register_teardown(app: Flask) -> None:
    @app.teardown_appcontext
    def close_db(exception=None):  # noqa: ANN001
        db = g.pop("db", None)
        if db is not None:
            db.close()


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(err: APIError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(429)
    def handle_rate_limit(err):  # noqa: ANN001
        return (
            jsonify(
                {
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please wait before trying again.",
                }
            ),
            429,
        )

    @app.errorhandler(404)
    def handle_404(err):  # noqa: ANN001
        return (
            jsonify({"error": "not_found", "message": "Resource not found.", "details": {}}),
            404,
        )

    @app.errorhandler(405)
    def handle_405(err):  # noqa: ANN001
        return (
            jsonify(
                {
                    "error": "method_not_allowed",
                    "message": "That HTTP method is not allowed for this endpoint.",
                    "details": {},
                }
            ),
            405,
        )

    @app.errorhandler(500)
    def handle_500(err):  # noqa: ANN001
        # Never expose tracebacks to clients.
        logger.exception("Unhandled server error")
        return (
            jsonify(
                {
                    "error": "internal_error",
                    "message": "An unexpected error occurred.",
                    "details": {},
                }
            ),
            500,
        )
