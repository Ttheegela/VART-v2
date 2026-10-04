import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sponsor_check.sh"


def _env() -> dict[str, str]:
    # No SPONSOR_NAME, and no GIT_*: a git hook exports GIT_DIR and GIT_INDEX_FILE, which would aim every git
    # command here at the repository running the hook instead of the one under test.
    return {k: v for k, v in os.environ.items() if k != "SPONSOR_NAME" and not k.startswith("GIT_")}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
        text=True,
        env=_env(),
    )
    return result.stdout.strip()


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, env=_env())
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _run(cwd: Path, name: str | None = "Acmecorp", **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = _env() | extra_env
    if name is not None:
        env["SPONSOR_NAME"] = name
    return subprocess.run(["bash", str(SCRIPT)], cwd=cwd, env=env, capture_output=True, text=True)


def _delete_object(repo: Path, rev: str) -> None:
    sha = _git(repo, "rev-parse", rev)
    (repo / ".git" / "objects" / sha[:2] / sha[2:]).unlink()


def _git_failing_on(directory: Path, subcommand: str) -> str:
    """A PATH whose `git` is the real one, except that `git <subcommand>` fails with status 128."""
    directory.mkdir()
    shim = directory / "git"
    shim.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        f'  if [ "$arg" = "{subcommand}" ]; then\n'
        f'    echo "fatal: simulated {subcommand} failure" >&2; exit 128\n'
        "  fi\n"
        "done\n"
        f'exec "{shutil.which("git")}" "$@"\n'
    )
    shim.chmod(0o755)
    return f"{directory}{os.pathsep}{os.environ['PATH']}"


def _leak_in_the_working_tree(repo: Path) -> None:
    (repo / "a.md").write_text("built for Acmecorp")  # edited, not committed: only `git grep` sees it


def _leak_in_the_index(repo: Path) -> None:
    (repo / "acmecorp.txt").write_text("x")
    _git(repo, "add", "acmecorp.txt")  # staged, not committed: only `git ls-files` sees it


def _leak_in_history(repo: Path) -> None:
    (repo / "a.md").write_text("copied from Acmecorp")
    _git(repo, "commit", "-qam", "leak")
    (repo / "a.md").write_text("hello")
    _git(repo, "commit", "-qam", "scrub")  # only `git log` sees it


def _printed(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout + result.stderr).lower()


def test_a_clean_repo_passes(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, {"a.md": "hello"}))
    assert result.returncode == 0
    assert "sponsor-check: clean" in result.stdout


def test_the_name_in_a_file_fails_in_any_case(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, {"a.md": "built for ACMECORP"}))
    assert result.returncode == 1
    assert "files above" in result.stderr
    assert "acmecorp" not in _printed(result)  # it lists files, never the matching lines


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
    assert "acmecorp" not in _printed(result)


def test_the_name_only_in_history_fails_in_any_case(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"a.md": "copied from ACMECORP"})
    (repo / "a.md").write_text("clean now")
    _git(repo, "commit", "-qam", "scrub")
    result = _run(repo)
    assert result.returncode == 1
    assert "git history" in result.stderr


def test_the_name_only_on_another_branch_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"a.md": "hello"})
    _git(repo, "checkout", "-qb", "side")
    (repo / "b.md").write_text("copied from Acmecorp")
    _git(repo, "add", "b.md")
    _git(repo, "commit", "-qm", "side")
    _git(repo, "checkout", "-q", "-")  # back on the first branch, whose tree and log are clean
    result = _run(repo)
    assert result.returncode == 1
    assert "git history" in result.stderr


def test_an_unset_name_is_an_error_not_a_pass(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, {"a.md": "hello"}), name=None)
    assert result.returncode != 0
    assert "SPONSOR_NAME" in result.stderr


def test_an_empty_name_is_an_error_not_a_pass(tmp_path: Path) -> None:
    # In CI the name is a GitHub repository secret. A secret that was never set, or any secret on a fork PR,
    # expands to an empty string.
    result = _run(_repo(tmp_path, {"a.md": "hello"}), name="")
    assert result.returncode != 0
    assert "SPONSOR_NAME" in result.stderr


@pytest.mark.parametrize("padded", [" Acmecorp", "Acmecorp ", "Acmecorp\n", "\tAcmecorp"])
def test_a_name_with_leading_or_trailing_whitespace_is_an_error_not_a_weaker_check(
    tmp_path: Path, padded: str
) -> None:
    # "Acmecorp " would not match "Acmecorp." in the repo, so padding is refused instead of searched for.
    result = _run(_repo(tmp_path, {"a.md": "built for Acmecorp."}), name=padded)
    assert result.returncode != 0
    assert "SPONSOR_NAME" in result.stderr
    assert "whitespace" in result.stderr
    assert "clean" not in result.stdout
    assert "acmecorp" not in _printed(result)  # it names the variable, not the value


def test_a_directory_git_cannot_read_is_an_error_not_a_pass(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.md").write_text("built for Acmecorp")
    result = _run(plain, GIT_CEILING_DIRECTORIES=str(tmp_path))  # git must not look above tmp_path
    assert result.returncode != 0
    assert "sponsor-check: clean" not in result.stdout


def test_a_run_from_a_subdirectory_still_scans_the_whole_repository(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"sub/b.md": "clean", "top.md": "built for Acmecorp", "acmecorp_notes.txt": "x"})
    result = _run(repo / "sub")
    assert result.returncode == 1
    assert "files above" in result.stderr  # the file outside sub/
    assert "file names above" in result.stderr


def test_a_clean_run_from_a_subdirectory_passes(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, {"sub/b.md": "hello", "top.md": "hello"}) / "sub")
    assert result.returncode == 0
    assert "sponsor-check: clean" in result.stdout


def test_a_non_ascii_name_is_found_in_file_names_and_in_history(tmp_path: Path) -> None:
    # git prints non-ASCII paths as octal escapes unless core.quotePath is off, which would hide this name.
    name = "Acmécorp"
    repo = _repo(tmp_path, {f"{name}.txt": "x"})
    result = _run(repo, name=name)
    assert result.returncode == 1
    assert "file names above" in result.stderr
    _git(repo, "rm", "-q", f"{name}.txt")
    _git(repo, "commit", "-qm", "scrub")
    result = _run(repo, name=name)
    assert result.returncode == 1
    assert "git history" in result.stderr
    assert "file names above" not in result.stderr


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ({"a.md": "copied from Acmecorp"}, {"a.md": "clean now"}),
        ({"a.md": "hello"}, {"b.md": "built for Acmecorp"}),
    ],
    ids=["the name only in history", "the name in a tracked file"],
)
def test_a_repository_with_a_missing_object_is_an_error_not_a_pass(
    tmp_path: Path, first: dict[str, str], second: dict[str, str]
) -> None:
    # git log cannot show a commit whose blob is gone. Reading that as "no match" passes history it never saw.
    repo = _repo(tmp_path, first)
    for name, text in second.items():
        (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "second")
    _delete_object(repo, "HEAD~1:a.md")
    result = _run(repo)
    assert result.returncode != 0
    assert "sponsor-check: clean" not in result.stdout


@pytest.mark.parametrize(
    ("subcommand", "leak", "found", "error"),
    [
        ("grep", _leak_in_the_working_tree, "files above", "sponsor-check: git grep failed"),
        ("ls-files", _leak_in_the_index, "file names above", "simulated ls-files failure"),
        ("log", _leak_in_history, "git history", "simulated log failure"),
    ],
    ids=["git grep", "git ls-files", "git log"],
)
def test_a_git_read_that_fails_is_an_error_not_a_pass(
    tmp_path: Path, subcommand: str, leak: Callable[[Path], None], found: str, error: str
) -> None:
    # Each leak is visible to one git read only, so taking that read's failure for "no match" prints "clean".
    repo = _repo(tmp_path / "repo", {"a.md": "hello"})
    leak(repo)
    assert found in _run(repo).stderr  # with a working git the leak is found
    result = _run(repo, PATH=_git_failing_on(tmp_path / "shim", subcommand))
    assert result.returncode == 128  # git's own status
    assert error in result.stderr
    assert "sponsor-check: clean" not in result.stdout


def test_it_leaves_no_temporary_files_behind(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    clean = _repo(tmp_path / "clean", {"a.md": "hello"})
    leaky = _repo(tmp_path / "leaky", {"a.md": "built for Acmecorp"})
    broken_git = _git_failing_on(tmp_path / "shim", "log")
    assert _run(clean, TMPDIR=str(scratch)).returncode == 0
    assert _run(leaky, TMPDIR=str(scratch)).returncode == 1
    assert _run(clean, TMPDIR=str(scratch), PATH=broken_git).returncode == 128
    assert list(scratch.iterdir()) == []


def test_the_helpers_ignore_the_git_environment_of_an_outer_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer = tmp_path / "outer.git"
    monkeypatch.setenv("GIT_DIR", str(outer))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "outer-index"))
    result = _run(_repo(tmp_path / "inner", {"a.md": "hello"}))
    assert result.returncode == 0
    assert not outer.exists()
