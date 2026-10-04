import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sponsor_check.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
    )


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _run(repo: Path, name: str | None = "Acmecorp") -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "SPONSOR_NAME"}
    if name is not None:
        env["SPONSOR_NAME"] = name
    return subprocess.run(["bash", str(SCRIPT)], cwd=repo, env=env, capture_output=True, text=True)


def test_a_clean_repo_passes(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, {"a.md": "hello"}))
    assert result.returncode == 0
    assert "sponsor-check: clean" in result.stdout


def test_the_name_in_a_file_fails_in_any_case(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, {"a.md": "built for ACMECORP"}))
    assert result.returncode == 1
    assert "files above" in result.stderr


def test_the_name_in_a_file_name_fails(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, {"acmecorp_policy.txt": "x"}))
    assert result.returncode == 1
    assert "file names above" in result.stderr


def test_the_name_only_in_history_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"a.md": "copied from Acmecorp"})
    (repo / "a.md").write_text("clean now")
    _git(repo, "commit", "-qam", "scrub")
    result = _run(repo)
    assert result.returncode == 1
    assert "git history" in result.stderr


def test_an_unset_name_is_an_error_not_a_pass(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, {"a.md": "hello"}), name=None)
    assert result.returncode != 0
    assert "SPONSOR_NAME" in result.stderr


def test_an_empty_name_is_an_error_not_a_pass(tmp_path: Path) -> None:
    # GitHub expands a repository variable that was never set to an empty string.
    result = _run(_repo(tmp_path, {"a.md": "hello"}), name="")
    assert result.returncode != 0
    assert "SPONSOR_NAME" in result.stderr
