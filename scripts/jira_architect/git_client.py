"""Git operations using subprocess.

All functions operate on a local git repository path.
They raise RuntimeError with a human-readable message on failure.
"""
from __future__ import annotations

import base64
import re
import subprocess
from pathlib import Path
from typing import Optional


def _run(cmd: list, cwd: str, check: bool = True) -> str:
    """Run a git command, return stdout. Raises RuntimeError on failure."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command {' '.join(cmd)} failed:\n{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _resolve_repo(repo_path: str) -> str:
    p = Path(repo_path).resolve()
    if not (p / ".git").exists():
        raise RuntimeError(f"No git repository found at: {p}")
    return str(p)


def _inject_token(url: str, token: Optional[str]) -> str:
    """Embed a GitHub PAT into an HTTPS URL for credential-free push/clone.

    https://github.com/org/repo.git  →  https://x-access-token:<token>@github.com/org/repo.git
    """
    if not token or not url.startswith("https://"):
        return url
    # Strip any existing embedded credentials first
    url = re.sub(r"https://[^@]+@", "https://", url)
    return url.replace("https://", f"https://x-access-token:{token}@", 1)


def _auth_header_arg(token: str) -> str:
    """Return a git -c argument that sets an Authorization header for HTTPS operations.

    The resulting string can be passed as the value to `git -c <value> <cmd>` to
    authenticate without modifying any persistent git config or embedding the
    token in the remote URL.

    Format: http.extraheader=AUTHORIZATION: basic <base64(x-access-token:token)>
    """
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return f"http.extraheader=AUTHORIZATION: basic {encoded}"


def ensure_branch(repo_path: str, branch: str) -> None:
    """Create and checkout branch if it doesn't exist, otherwise just checkout."""
    cwd = _resolve_repo(repo_path)
    existing = _run(["git", "branch", "--list", branch], cwd=cwd)
    if existing.strip():
        _run(["git", "checkout", branch], cwd=cwd)
    else:
        _run(["git", "checkout", "-b", branch], cwd=cwd)


def stage_all(repo_path: str) -> None:
    cwd = _resolve_repo(repo_path)
    _run(["git", "add", "-A"], cwd=cwd)


def commit_all(repo_path: str, message: str) -> str:
    """Stage all changes and commit. Returns the full commit hash."""
    cwd = _resolve_repo(repo_path)
    stage_all(repo_path)
    # Check if there is anything to commit
    status = _run(["git", "status", "--porcelain"], cwd=cwd, check=False)
    # If already staged, proceed; if nothing staged, raise
    staged = _run(["git", "diff", "--cached", "--name-only"], cwd=cwd, check=False)
    if not staged and not status:
        raise RuntimeError("Nothing to commit — working tree is clean.")
    _run(["git", "commit", "-m", message], cwd=cwd)
    return get_head_commit(repo_path)


def push(repo_path: str, remote: str, branch: str, token: Optional[str] = None) -> None:
    cwd = _resolve_repo(repo_path)
    if token:
        _run(["git", "-c", _auth_header_arg(token), "push", remote, branch], cwd=cwd)
    else:
        _run(["git", "push", remote, branch], cwd=cwd)


def get_head_commit(repo_path: str) -> str:
    cwd = _resolve_repo(repo_path)
    return _run(["git", "rev-parse", "HEAD"], cwd=cwd)


def get_current_branch(repo_path: str) -> str:
    cwd = _resolve_repo(repo_path)
    return _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)


def get_remote_url(repo_path: str, remote: str = "origin") -> Optional[str]:
    cwd = _resolve_repo(repo_path)
    try:
        url = _run(["git", "remote", "get-url", remote], cwd=cwd, check=True)
        return url if url else None
    except RuntimeError:
        return None


def clone(clone_url: str, local_path: str, token: Optional[str] = None) -> None:
    """Clone clone_url into local_path (skips silently if already cloned)."""
    p = Path(local_path).resolve()
    if (p / ".git").exists():
        return  # already cloned
    p.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git"]
    if token:
        cmd += ["-c", _auth_header_arg(token)]
    cmd += ["clone", clone_url, str(p)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"git clone failed:\n{result.stderr.strip() or result.stdout.strip()}"
        )


def normalize_repo_url(url: str) -> str:
    """Convert SSH git remote URLs to HTTPS browse URLs."""
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url[len("git@github.com:"):]
    elif url.startswith("git@gitlab.com:"):
        url = "https://gitlab.com/" + url[len("git@gitlab.com:"):]
    return url.rstrip("/").removesuffix(".git")


def build_commit_url(repo_url: str, commit_hash: str) -> Optional[str]:
    """Build a web URL to a commit, supporting GitHub and GitLab."""
    normalized = normalize_repo_url(repo_url)
    if "github.com" in normalized or "gitlab.com" in normalized:
        return f"{normalized}/commit/{commit_hash}"
    return None
