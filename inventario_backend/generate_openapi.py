import argparse
import json
import os
from dotenv import load_dotenv

# Ensure env variables are available (e.g., FRONTEND_ORIGIN)
load_dotenv()

# Import app and smorest api instance
from app import app, api  # noqa: E402


def main() -> None:
    """Generate and write the OpenAPI specification to a JSON file."""
    parser = argparse.ArgumentParser(description="Generate OpenAPI specification JSON from Flask app.")
    parser.add_argument(
        "-o",
        "--output",
        default=os.path.join("interfaces", "openapi.json"),
        help="Output file path for the generated OpenAPI JSON (default: interfaces/openapi.json)",
    )
    args = parser.parse_args()

    output_path = args.output
    output_dir = os.path.dirname(output_path) or "."

    with app.app_context():
        # flask-smorest stores the spec in api.spec
        openapi_spec = api.spec.to_dict()

    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(openapi_spec, f, indent=2)

    print(f"OpenAPI spec written to: {output_path}")


if __name__ == "__main__":
    main()
