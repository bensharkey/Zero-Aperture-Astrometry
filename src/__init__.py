import os
from pathlib import Path

from flask import Flask

from .config import Config


def create_app(config_class: type[Config] = Config) -> Flask:
    """Application factory used by the CLI entry point."""
    base_dir = Path(__file__).resolve().parent.parent
    template_dir = base_dir / "src" / "templates"
    app = Flask(
        __name__,
        template_folder=str(template_dir),
    )
    app.config.from_object(config_class)

    # Ensure upload folder exists relative to project root
    upload_folder = app.config["UPLOAD_FOLDER"]
    if not os.path.isabs(upload_folder):
        upload_folder = str((base_dir / upload_folder).resolve())
        app.config["UPLOAD_FOLDER"] = upload_folder
    os.makedirs(upload_folder, exist_ok=True)

    from .routes import main_bp

    app.register_blueprint(main_bp)

    return app
