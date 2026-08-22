"""
Phoenix Backend — Flask Application Factory

Creates and configures the Flask app with:
- Flask-CORS
- Flask-SocketIO
- MongoDB connection
- All API blueprints
"""
from __future__ import annotations

import logging

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

from backend.config import get_config
from backend.db.mongo import init_db
from backend.websocket.events import init_socketio

logger = logging.getLogger(__name__)

socketio = SocketIO()


def create_app() -> Flask:
    """Flask application factory."""
    config = get_config()

    app = Flask(__name__)
    app.config.from_object(config)

    # ------------------------------------------------------------------ #
    # CORS                                                                 #
    # ------------------------------------------------------------------ #
    CORS(app, origins=config.CORS_ORIGINS, supports_credentials=True)

    # ------------------------------------------------------------------ #
    # Socket.IO                                                            #
    # ------------------------------------------------------------------ #
    socketio.init_app(
        app,
        cors_allowed_origins=config.SOCKETIO_CORS_ALLOWED_ORIGINS,
        async_mode=config.SOCKETIO_ASYNC_MODE,
        logger=False,
        engineio_logger=False,
    )
    init_socketio(socketio)

    # ------------------------------------------------------------------ #
    # MongoDB                                                              #
    # ------------------------------------------------------------------ #
    try:
        init_db(config.MONGO_URI, config.MONGO_DB_NAME)
        logger.info("MongoDB: ready")
    except Exception as exc:
        logger.error("MongoDB: connection failed — %s", exc)
        # Don't crash — allow health endpoint to still respond

    # ------------------------------------------------------------------ #
    # API Blueprints                                                       #
    # ------------------------------------------------------------------ #
    from backend.api.incidents import bp as incidents_bp
    from backend.api.metrics import bp as metrics_bp
    from backend.api.health import health_bp, containers_bp

    app.register_blueprint(incidents_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(containers_bp)

    logger.info("Phoenix Backend: application ready")
    return app


def run() -> None:
    """Entrypoint for running the backend."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = create_app()
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    run()
