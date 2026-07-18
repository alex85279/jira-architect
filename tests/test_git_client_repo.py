"""Tests for git_client's repo-creation helpers: clone() and token-aware push()."""
from __future__ import annotations

import base64
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from jira_architect import git_client as git


# ---------------------------------------------------------------------------
# _auth_header_arg
# ---------------------------------------------------------------------------

def test_auth_header_arg_format():
    header = git._auth_header_arg("mytoken")
    assert header.startswith("http.extraheader=AUTHORIZATION: basic ")
    encoded = header.split("basic ", 1)[1]
    decoded = base64.b64decode(encoded).decode()
    assert decoded == "x-access-token:mytoken"


def test_auth_header_arg_differs_per_token():
    assert git._auth_header_arg("a") != git._auth_header_arg("b")


# ---------------------------------------------------------------------------
# clone()
# ---------------------------------------------------------------------------

def _make_bare_remote(tmp_path, name="remote.git"):
    remote_path = tmp_path / name
    subprocess.run(["git", "init", "--bare", "-q", str(remote_path)], check=True)
    # Seed it with one commit via a throwaway working copy.
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(remote_path), str(seed)], check=True)
    subprocess.run(["git", "config", "user.email", "hermes@localhost"], cwd=seed, check=True)
    subprocess.run(["git", "config", "user.name", "Hermes"], cwd=seed, check=True)
    (seed / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=seed, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=seed, check=True)
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=seed, capture_output=True, text=True, check=True,
    ).stdout.strip()
    subprocess.run(["git", "push", "-q", "origin", f"HEAD:{branch}"], cwd=seed, check=True)
    # Point the bare repo's HEAD at the branch we just pushed, so a plain
    # `git clone` (which follows remote HEAD) actually checks out content.
    subprocess.run(
        ["git", "symbolic-ref", "HEAD", f"refs/heads/{branch}"],
        cwd=remote_path, check=True,
    )
    return remote_path


def test_clone_creates_local_checkout(tmp_path):
    remote = _make_bare_remote(tmp_path)
    dest = tmp_path / "checkout"
    git.clone(str(remote), str(dest))
    assert (dest / ".git").exists()
    assert (dest / "README.md").exists()


def test_clone_is_noop_if_dest_already_a_repo(tmp_path):
    remote = _make_bare_remote(tmp_path)
    dest = tmp_path / "checkout"
    git.clone(str(remote), str(dest))
    # Second call must not raise even though dest is non-empty and already a repo.
    git.clone(str(remote), str(dest))
    assert (dest / ".git").exists()


def test_clone_raises_on_invalid_url(tmp_path):
    dest = tmp_path / "checkout"
    try:
        git.clone(str(tmp_path / "does-not-exist.git"), str(dest))
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# push() with a token
# ---------------------------------------------------------------------------

def test_push_with_token_does_not_persist_token_in_git_config(tmp_path):
    remote = _make_bare_remote(tmp_path)
    dest = tmp_path / "checkout"
    git.clone(str(remote), str(dest))

    (dest / "new_file.txt").write_text("content\n")
    git.ensure_branch(str(dest), "feature/x")
    git.commit_all(str(dest), "feat: add file")
    git.push(str(dest), "origin", "feature/x", token="secret-token-value")

    config_text = (dest / ".git" / "config").read_text()
    assert "secret-token-value" not in config_text

    # And the branch really did land on the remote.
    result = subprocess.run(
        ["git", "ls-remote", str(remote), "feature/x"],
        capture_output=True, text=True, check=True,
    )
    assert "feature/x" in result.stdout
