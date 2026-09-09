"""Flask application factory.

A factory rather than a module-level ``app`` so tests can build an isolated
instance pointed at a temporary database, and so configuration arrives as an
argument instead of being read from the environment at import time.
"""

from __future__ import annotations

from flask import Flask

from ..config import Settings
from ..skills import SkillIndex


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_env()
    settings.ensure_dirs()

    app = Flask(__name__)
    app.config["SETTINGS"] = settings
    # Loaded once at startup: the taxonomy is read-only and parsing it per
    # request would dominate the cost of a request that does almost no work.
    app.config["SKILL_INDEX"] = SkillIndex.from_file(settings.taxonomy_path)

    from .routes import bp

    app.register_blueprint(bp)
    return app
