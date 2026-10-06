import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_dependencies_match_requirements_txt() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pinned = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    assert sorted(pyproject["project"]["dependencies"]) == sorted(pinned)


def test_runtime_redaction_stack_is_pinned_to_what_the_eval_measured() -> None:
    # adversary checkpoint 1, M10: production must not resolve a Presidio or spaCy the redacted-upload stage
    # never ran, so the runtime pins equal requirements-dev.txt's (numpy and blis may stay ranges at runtime).
    def pins(name: str) -> dict[str, str]:
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        return {x.split("==")[0]: x for x in (line.strip() for line in lines) if "==" in x}

    runtime, dev = pins("requirements.txt"), pins("requirements-dev.txt")
    names = ("presidio-analyzer", "spacy", "thinc", "openpyxl")
    assert {n: runtime.get(n) for n in names} == {n: dev[n] for n in names}
