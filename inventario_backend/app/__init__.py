from flask import Flask, jsonify, make_response, request
from flask_cors import CORS
from flask_smorest import Api
import os
from dotenv import load_dotenv

from .routes.health import blp
from .routes.items import blp as items_blp
from .db import init_db, init_session

# Load environment variables from .env if present
load_dotenv()

# PUBLIC_INTERFACE
def create_app() -> Flask:
    """Create and configure the Flask application.

    Loads environment variables, configures CORS, sets OpenAPI/Swagger metadata,
    and initializes the database engine and session for development use.

    This function also:
    - Ensures CORS allows the frontend origin provided by FRONTEND_ORIGIN env var.
    - Handles OPTIONS preflight requests.
    - Exposes OpenAPI docs at /docs and spec at /openapi.json for convenience.

    Returns:
        Flask: The configured Flask application instance.
    """
    app = Flask(__name__)
    app.url_map.strict_slashes = False

    # API Docs / OpenAPI metadata
    app.config["API_TITLE"] = "Inventario API"
    app.config["API_VERSION"] = "v1"
    app.config["OPENAPI_VERSION"] = "3.0.3"
    # Serve Swagger UI under /docs
    app.config["OPENAPI_URL_PREFIX"] = "/docs"
    app.config["OPENAPI_SWAGGER_UI_PATH"] = ""
    app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

    # CORS configuration based on env
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "*")
    CORS(
        app,
        resources={r"/*": {"origins": frontend_origin}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        expose_headers=["Content-Disposition"],
    )

    # Lightweight global OPTIONS handler for preflight requests (in addition to Flask-CORS)
    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            resp = make_response("", 204)
            return resp
        return None

    # Database configuration:
    # Prefer DATABASE_URL if provided, otherwise construct from POSTGRES_* env vars.
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")

    # Initialize DB Engine and Session (dev-friendly: create tables if missing)
    # In production, prefer migrations over create_all.
    echo_sql = os.getenv("SQL_ECHO", "false").lower() in ("1", "true", "yes")
    init_db(app.config["DATABASE_URL"], echo=echo_sql)
    init_session()

    # Register API with Smorest
    api = Api(app)

    # Register blueprints
    api.register_blueprint(blp)
    api.register_blueprint(items_blp)

    # Convenience: expose raw openapi JSON under /openapi.json (outside /docs prefix)
    @app.get("/openapi.json")
    def openapi_json():
        """Return the OpenAPI JSON specification for this API."""
        spec = api.spec.to_dict()
        return jsonify(spec)

    # Convenience: plain docs usage help at GET /docs/help
    @app.get("/docs/help")
    def docs_help():
        """Usage note for API documentation and WebSocket endpoints (if any)."""
        return jsonify(
            {
                "message": "API documentation is available at /docs (Swagger UI) and /openapi.json (spec).",
                "openapi": app.config.get("OPENAPI_VERSION", "3.0.3"),
                "title": app.config.get("API_TITLE", "API"),
                "version": app.config.get("API_VERSION", "v1"),
            }
        )

    # Expose api for openapi generation script compatibility
    app.extensions = getattr(app, "extensions", {})
    app.extensions["smorest_api"] = api

    return app


# Maintain existing import interface for run.py and generate_openapi.py
# so that "from app import app, api" continues to work.
app = create_app()
# For generate_openapi.py compatibility: expose 'api' at module level
api = app.extensions.get("smorest_api")
