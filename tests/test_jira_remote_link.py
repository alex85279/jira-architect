"""Tests for JiraClient's remote-link (ticket <-> repo) methods."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from jira_architect.config import ArchitectConfig
from jira_architect.jira_client import JiraClient


def _cfg():
    return ArchitectConfig(
        url="https://example.atlassian.net",
        email="user@example.com",
        token="tok",
        project_key="PROJ",
    )


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# find_repo_link
# ---------------------------------------------------------------------------

def test_find_repo_link_returns_url_when_hermes_link_present():
    client = JiraClient(_cfg())
    links = [
        {"globalId": "some-other-link", "object": {"url": "https://example.com"}},
        {"globalId": "hermes-repo:PROJ-42", "object": {"url": "https://github.com/alex85279/proj-42"}},
    ]
    with patch("jira_architect.jira_client.requests.get", return_value=_mock_response(200, links)):
        url = client.find_repo_link("PROJ-42")
    assert url == "https://github.com/alex85279/proj-42"


def test_find_repo_link_returns_none_when_absent():
    client = JiraClient(_cfg())
    with patch("jira_architect.jira_client.requests.get", return_value=_mock_response(200, [])):
        url = client.find_repo_link("PROJ-42")
    assert url is None


def test_find_repo_link_ignores_non_hermes_links():
    client = JiraClient(_cfg())
    links = [{"globalId": "jira-dvcs-connector:abc", "object": {"url": "https://gitlab.com/x/y"}}]
    with patch("jira_architect.jira_client.requests.get", return_value=_mock_response(200, links)):
        url = client.find_repo_link("PROJ-42")
    assert url is None


# ---------------------------------------------------------------------------
# add_remote_link
# ---------------------------------------------------------------------------

def test_add_remote_link_posts_expected_payload():
    client = JiraClient(_cfg())
    with patch("jira_architect.jira_client.requests.post", return_value=_mock_response(201)) as mock_post:
        client.add_remote_link(
            "PROJ-42",
            url="https://github.com/alex85279/proj-42",
            title="GitHub: alex85279/proj-42",
            global_id="hermes-repo:PROJ-42",
        )
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/issue/PROJ-42/remotelink")
    payload = kwargs["json"]
    assert payload["globalId"] == "hermes-repo:PROJ-42"
    assert payload["object"]["url"] == "https://github.com/alex85279/proj-42"


def test_add_remote_link_raises_on_failure():
    client = JiraClient(_cfg())
    resp = _mock_response(400)
    resp.text = "bad request"
    with patch("jira_architect.jira_client.requests.post", return_value=resp):
        try:
            client.add_remote_link("PROJ-42", url="u", title="t", global_id="g")
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "PROJ-42" in str(exc)
