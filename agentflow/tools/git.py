"""Git worktree lifecycle tools. All subprocess calls use list args with shell disabled."""

import re
import subprocess
from pathlib import Path

BRANCH_PATTERN = re.compile(r"^[a-zA-Z0-9._/-]{1,100}$")


class GitError(Exception):
    pass


class WorktreeExistsError(GitError):
    pass


class WorktreeNotFoundError(GitError):
    pass


class DirtyWorkingTreeError(GitError):
    pass


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or result.stdout.strip())
    return result


def create_worktree(base_path: Path, task_id: str, branch_name: str) -> Path:
    """Create a git worktree at <base_path>/workspaces/<task_id> on a new branch.

    Returns the worktree path. Idempotent: if the worktree already exists, returns its path.
    """
    if not BRANCH_PATTERN.match(branch_name):
        raise ValueError(
            f"Invalid branch name {branch_name!r}. "
            "Must match [a-zA-Z0-9._/-]{1,100}."
        )

    worktree_path = base_path / "workspaces" / task_id

    if worktree_path.exists():
        return worktree_path

    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        _run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            cwd=base_path,
        )
    except GitError as exc:
        # Branch already exists but worktree dir was missing — use existing branch
        if "already exists" in str(exc):
            _run(
                ["git", "worktree", "add", str(worktree_path), branch_name],
                cwd=base_path,
            )
        else:
            raise

    return worktree_path


def _main_repo_root(worktree_path: Path) -> Path | None:
    """Return the main repo root from inside a worktree (or the path itself if it is the main repo)."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    common_dir = result.stdout.strip()
    # In the main repo this is ".git"; in a worktree it's an absolute path
    if common_dir == ".git":
        return worktree_path
    return Path(common_dir).parent


def delete_worktree(worktree_path: Path) -> None:
    """Remove the worktree directory and prune the ref. Idempotent if already gone."""
    if not worktree_path.exists():
        return

    repo_root = _main_repo_root(worktree_path)
    if repo_root is None:
        import shutil
        shutil.rmtree(worktree_path, ignore_errors=True)
        return

    try:
        _run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=repo_root,
        )
    except GitError:
        import shutil
        shutil.rmtree(worktree_path, ignore_errors=True)

    # Prune stale refs — repo_root still exists after worktree removal
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=repo_root,
        capture_output=True,
    )


def commit_files(worktree_path: Path, message: str, files: list[Path]) -> str:
    """Stage only the listed files and create a commit. Returns the commit SHA."""
    if not files:
        raise ValueError("files list must not be empty")

    for f in files:
        _run(["git", "add", str(f)], cwd=worktree_path)

    _run(["git", "commit", "-m", message], cwd=worktree_path)

    result = _run(["git", "rev-parse", "HEAD"], cwd=worktree_path)
    return result.stdout.strip()


def push_branch(worktree_path: Path, branch_name: str, remote: str = "origin") -> None:
    """Push the branch to the remote repository."""
    _run(["git", "push", "-u", remote, branch_name], cwd=worktree_path)

