from flask import Flask
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

    Returns:
        Flask: The configured Flask application instance.
    """
    app = Flask(__name__)
    app.url_map.strict_slashes = False

    # API Docs / OpenAPI metadata
    app.config["API_TITLE"] = "Inventario API"
    app.config["API_VERSION"] = "v1"
    app.config["OPENAPI_VERSION"] = "3.0.3"
    app.config["OPENAPI_URL_PREFIX"] = "/docs"
    app.config["OPENAPI_SWAGGER_UI_PATH"] = ""
    app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

    # CORS configuration based on env
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "*")
    CORS(
        app,
        resources={r"/*": {"origins": frontend_origin}},
        supports_credentials=True,
    )

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

    # Expose api for openapi generation script compatibility
    app.extensions = getattr(app, "extensions", {})
    app.extensions["smorest_api"] = api

    return app


# Maintain existing import interface for run.py and generate_openapi.py
# so that "from app import app, api" continues to work.
app = create_app()
# For generate_openapi.py compatibility: expose 'api' at module level
api = app.extensions.get("smorest_api")
