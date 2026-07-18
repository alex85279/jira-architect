"""Jira + Git config for jira-architect, stored at ~/.hermes/jira-architect.json.

Credentials are stored with owner-only file permissions (chmod 600).

Config path resolution order:
  1. $HERMES_HOME/.hermes/jira-architect.json  (Hermes gateway runtime)
  2. $HOME/.hermes/jira-architect.json          (docker exec / local dev)

GitHub token resolution order (inside load()):
  1. github_token field in the JSON config file
  2. $GITHUB_TOKEN environment variable
  3. $GH_TOKEN environment variable
  4. $GITHUB_PAT environment variable
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _config_path() -> Path:
    """Return the config file path, respecting HERMES_HOME runtime env."""
    base = os.environ.get("HERMES_HOME")
    if base:
        return Path(base) / ".hermes" / "jira-architect.json"
    return Path.home() / ".hermes" / "jira-architect.json"


CONFIG_PATH = _config_path()


@dataclass
class ArchitectConfig:
    url: str            # e.g. https://yourcompany.atlassian.net
    email: str
    token: str
    project_key: str
    git_repo_path: Optional[str] = None
    git_remote: str = "origin"
    branch_prefix: str = "feature/hermes-"
    discord_webhook_url: Optional[str] = None  # optional: push notifications to Discord
    github_token: Optional[str] = None         # GitHub PAT with 'repo' scope
    workspace_dir: str = "~/.hermes/jira-architect/repos"  # local root for cloned repos


def load() -> Optional[ArchitectConfig]:
    """Return config or None if not configured yet."""
    path = _config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        # GitHub token: JSON config → env var fallbacks
        github_token = (
            data.get("github_token")
            or os.environ.get("GITHUB_TOKEN")
            or os.environ.get("GH_TOKEN")
            or os.environ.get("GITHUB_PAT")
        )
        return ArchitectConfig(
            url=data["url"].rstrip("/"),
            email=data["email"],
            token=data["token"],
            project_key=data.get("project_key", ""),
            git_repo_path=data.get("git_repo_path"),
            git_remote=data.get("git_remote", "origin"),
            branch_prefix=data.get("branch_prefix", "feature/hermes-"),
            discord_webhook_url=data.get("discord_webhook_url"),
            github_token=github_token,
            workspace_dir=data.get("workspace_dir", "~/.hermes/jira-architect/repos"),
        )
    except (KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Malformed config at {path}: {exc}") from exc


def save(
    url: str,
    email: str,
    token: str,
    project_key: str,
    git_repo_path: Optional[str] = None,
    git_remote: str = "origin",
    branch_prefix: str = "feature/hermes-",
    discord_webhook_url: Optional[str] = None,
    github_token: Optional[str] = None,
    workspace_dir: Optional[str] = None,
) -> None:
    """Persist config with owner-only read/write permissions."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "url": url.rstrip("/"),
                "email": email,
                "token": token,
                "project_key": project_key,
                "git_repo_path": git_repo_path,
                "git_remote": git_remote,
                "branch_prefix": branch_prefix,
                "discord_webhook_url": discord_webhook_url,
                "github_token": github_token,
                "workspace_dir": workspace_dir or "~/.hermes/jira-architect/repos",
            },
            indent=2,
        )
    )
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
