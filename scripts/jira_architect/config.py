"""Jira + Git config for jira-architect, stored at ~/.hermes/jira-architect.json.

Credentials are stored with owner-only file permissions (chmod 600).
"""
from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path.home() / ".hermes" / "jira-architect.json"


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
    if not CONFIG_PATH.exists():
        return None
    try:
        data = json.loads(CONFIG_PATH.read_text())
        return ArchitectConfig(
            url=data["url"].rstrip("/"),
            email=data["email"],
            token=data["token"],
            project_key=data.get("project_key", ""),
            git_repo_path=data.get("git_repo_path"),
            git_remote=data.get("git_remote", "origin"),
            branch_prefix=data.get("branch_prefix", "feature/hermes-"),
            discord_webhook_url=data.get("discord_webhook_url"),
            github_token=data.get("github_token"),
            workspace_dir=data.get("workspace_dir", "~/.hermes/jira-architect/repos"),
        )
    except (KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Malformed config at {CONFIG_PATH}: {exc}") from exc


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
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
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
    CONFIG_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
