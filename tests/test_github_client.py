"""Tests for the GitHub REST API client used by ensure-repo."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from jira_architect.github_client import GitHubClient


# ---------------------------------------------------------------------------
# slug_from_summary
# ---------------------------------------------------------------------------

def test_slug_from_summary_lowercases_and_hyphenates():
    slug = GitHubClient.slug_from_summary("PROJ-42", "Implement User Auth")
    assert slug == "proj-42-implement-user-auth"


def test_slug_from_summary_strips_special_characters():
    slug = GitHubClient.slug_from_summary("PROJ-1", "Fix: login/logout (bug)!")
    assert slug == "proj-1-fix-login-logout-bug"
    assert all(c.isalnum() or c == "-" for c in slug)


def test_slug_from_summary_truncated_to_60_chars():
    long_summary = "x" * 200
    slug = GitHubClient.slug_from_summary("PROJ-1", long_summary)
    assert len(slug) <= 60


# ---------------------------------------------------------------------------
# plain_clone_url
# ---------------------------------------------------------------------------

def test_plain_clone_url_uses_clone_url_field():
    repo = {"clone_url": "https://github.com/alex85279/proj-1.git"}
    assert GitHubClient.plain_clone_url(repo) == "https://github.com/alex85279/proj-1.git"


# ---------------------------------------------------------------------------
# create_repo — idempotency
# ---------------------------------------------------------------------------

def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


def test_create_repo_returns_existing_repo_without_posting():
    client = GitHubClient("tok")
    user_resp = _mock_response(200, {"login": "alex85279"})
    exists_resp = _mock_response(200)
    get_resp = _mock_response(200, {"html_url": "https://github.com/alex85279/proj-1", "full_name": "alex85279/proj-1"})

    with patch("jira_architect.github_client.requests.get", side_effect=[user_resp, exists_resp, get_resp]) as mock_get, \
         patch("jira_architect.github_client.requests.post") as mock_post:
        repo = client.create_repo("proj-1")

    assert repo["full_name"] == "alex85279/proj-1"
    mock_post.assert_not_called()
    assert mock_get.call_count == 3


def test_create_repo_posts_when_repo_does_not_exist():
    client = GitHubClient("tok")
    user_resp = _mock_response(200, {"login": "alex85279"})
    not_exists_resp = _mock_response(404)
    create_resp = _mock_response(201, {"html_url": "https://github.com/alex85279/proj-2", "full_name": "alex85279/proj-2"})

    with patch("jira_architect.github_client.requests.get", side_effect=[user_resp, not_exists_resp]), \
         patch("jira_architect.github_client.requests.post", return_value=create_resp) as mock_post:
        repo = client.create_repo("proj-2", private=True, auto_init=True)

    assert repo["full_name"] == "alex85279/proj-2"
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["name"] == "proj-2"
    assert kwargs["json"]["private"] is True
    assert kwargs["json"]["auto_init"] is True


def test_create_repo_raises_on_failure():
    client = GitHubClient("tok")
    user_resp = _mock_response(200, {"login": "alex85279"})
    not_exists_resp = _mock_response(404)
    fail_resp = _mock_response(422, {})
    fail_resp.text = "name already exists on this account"

    with patch("jira_architect.github_client.requests.get", side_effect=[user_resp, not_exists_resp]), \
         patch("jira_architect.github_client.requests.post", return_value=fail_resp):
        try:
            client.create_repo("proj-3")
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "proj-3" in str(exc)
