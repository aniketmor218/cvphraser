"""Runtime configuration.

Everything is overridable through environment variables so the same code runs
unchanged on a laptop, in a container, or on a PaaS dyno.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_TAXONOMY = PACKAGE_ROOT / "data" / "skills.yml"


def _default_data_dir() -> Path:
    """Follow the XDG spec on Linux, fall back to a dot-dir everywhere else."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "skillsift"


@dataclass(frozen=True)
class Settings:
    database_path: Path
    taxonomy_path: Path
    #: Skills in a "required" block count this much more than "nice to have".
    required_weight: float = 3.0
    preferred_weight: float = 1.0
    #: Below this, the CLI exits non-zero so it can gate a shell pipeline.
    pass_threshold: float = 0.6

    @classmethod
    def from_env(cls) -> Settings:
        db = os.environ.get("SKILLSIFT_DB")
        taxonomy = os.environ.get("SKILLSIFT_TAXONOMY")
        return cls(
            database_path=Path(db) if db else _default_data_dir() / "skillsift.db",
            taxonomy_path=Path(taxonomy) if taxonomy else DEFAULT_TAXONOMY,
            required_weight=float(os.environ.get("SKILLSIFT_REQUIRED_WEIGHT", 3.0)),
            preferred_weight=float(os.environ.get("SKILLSIFT_PREFERRED_WEIGHT", 1.0)),
            pass_threshold=float(os.environ.get("SKILLSIFT_PASS_THRESHOLD", 0.6)),
        )

    def ensure_dirs(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
