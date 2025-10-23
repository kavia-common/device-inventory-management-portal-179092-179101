from flask import Flask
from flask_cors import CORS
from flask_smorest import Api
import os
from dotenv import load_dotenv

from .routes.health import blp

# Load environment variables from .env if present
load_dotenv()

# PUBLIC_INTERFACE
def create_app() -> Flask:
    """Create and configure the Flask application.

    Loads environment variables, configures CORS, sets OpenAPI/Swagger metadata,
    and prepares hooks for database initialization in future steps.

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

    # Database configuration placeholders (future initialization)
    # Prefer DATABASE_URL if provided, otherwise can be built from POSTGRES_* in a later step.
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")

    # Example hook placeholders for later DB/session initialization
    # from .db import init_db, init_session  # to be added later
    # init_db(app.config["DATABASE_URL"])
    # init_session(app)

    # Register API with Smorest
    api = Api(app)

    # Register blueprints
    api.register_blueprint(blp)

    # Expose api for openapi generation script compatibility
    app.extensions = getattr(app, "extensions", {})
    app.extensions["smorest_api"] = api

    return app


# Maintain existing import interface for run.py and generate_openapi.py
# so that "from app import app, api" continues to work.
app = create_app()
# For generate_openapi.py compatibility: expose 'api' at module level
api = app.extensions.get("smorest_api")
