"""GitHub REST API v3 client for jira-architect.

Operations:
  - create_repo       — create a new repository under the authenticated user
  - repo_exists       — check if a repo already exists
  - get_login         — return the authenticated user's login
  - slug_from_summary — generate a safe repo name slug from ticket key + summary
  - plain_clone_url   — HTTPS clone URL from a GitHub API repo dict
"""
from __future__ import annotations

import re
from typing import Dict, Optional

import requests


class GitHubClient:
    _API = "https://api.github.com"

    def __init__(self, token: str) -> None:
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._login: Optional[str] = None  # cached

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def get_login(self) -> str:
        """Return the authenticated user's GitHub login (cached after first call)."""
        if self._login is None:
            resp = requests.get(f"{self._API}/user", headers=self._headers, timeout=10)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"GitHub auth failed ({resp.status_code}). "
                    "Check that --github-token has 'repo' scope."
                )
            self._login = resp.json()["login"]
        return self._login

    # ------------------------------------------------------------------
    # Repo operations
    # ------------------------------------------------------------------

    def repo_exists(self, full_name: str) -> bool:
        """Return True if `owner/name` exists and is accessible."""
        resp = requests.get(
            f"{self._API}/repos/{full_name}", headers=self._headers, timeout=10
        )
        return resp.status_code == 200

    def create_repo(
        self,
        name: str,
        description: str = "",
        private: bool = True,
        auto_init: bool = True,
    ) -> Dict:
        """Create a repo under the authenticated user. Returns the GitHub repo dict.

        Proactively checks whether the repo already exists before attempting to
        create it, making the operation idempotent.
        """
        login = self.get_login()

        # Check existence first (idempotency)
        if self.repo_exists(f"{login}/{name}"):
            resp = requests.get(
                f"{self._API}/repos/{login}/{name}",
                headers=self._headers,
                timeout=10,
            )
            return resp.json()

        # Repo does not exist — create it
        resp = requests.post(
            f"{self._API}/user/repos",
            headers=self._headers,
            json={
                "name": name,
                "description": description[:350],
                "private": private,
                "auto_init": auto_init,
            },
            timeout=20,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to create GitHub repo '{name}' "
                f"({resp.status_code}): {resp.text[:400]}"
            )
        return resp.json()

    # ------------------------------------------------------------------
    # Class-level helpers (no auth required)
    # ------------------------------------------------------------------

    @classmethod
    def slug_from_summary(cls, ticket_key: str, summary: str) -> str:
        """Generate a safe, lowercase GitHub repo name from ticket key + summary.

        Examples:
          "KAN-1", "User Authentication System" → "kan-1-user-authentication-system"
          "PROJ-42", "設計登入 API endpoint"    → "proj-42-api-endpoint"
        """
        key_part = ticket_key.lower()

        # Strip non-ASCII (e.g. CJK characters), keep alphanumeric + spaces/hyphens
        ascii_summary = summary.encode("ascii", errors="ignore").decode()
        words = re.sub(r"[^a-zA-Z0-9\s-]", " ", ascii_summary).split()
        slug_words = [w.lower() for w in words if len(w) > 1][:5]

        slug = key_part
        if slug_words:
            slug = key_part + "-" + "-".join(slug_words)

        # GitHub name rules: max 60 chars, no leading/trailing hyphens
        slug = re.sub(r"-{2,}", "-", slug)
        return slug[:60].strip("-")

    @classmethod
    def plain_clone_url(cls, repo: Dict) -> str:
        """Return the HTTPS clone URL from a GitHub API repo response dict."""
        return repo.get("clone_url") or (repo.get("html_url", "") + ".git")
