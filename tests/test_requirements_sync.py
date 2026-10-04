import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_dependencies_match_requirements_txt() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pinned = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    assert sorted(pyproject["project"]["dependencies"]) == sorted(pinned)
