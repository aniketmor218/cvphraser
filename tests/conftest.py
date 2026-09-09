import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skillsift.config import Settings  # noqa: E402
from skillsift.skills import SkillIndex  # noqa: E402

TAXONOMY = Path(__file__).resolve().parents[1] / "skillsift" / "data" / "skills.yml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(database_path=tmp_path / "test.db", taxonomy_path=TAXONOMY)


@pytest.fixture
def index() -> SkillIndex:
    return SkillIndex.from_file(TAXONOMY)


@pytest.fixture
def cv_text() -> str:
    return (FIXTURES / "cv.md").read_text()


@pytest.fixture
def jd_text() -> str:
    return (FIXTURES / "job.md").read_text()
