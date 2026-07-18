"""Tests for per-ticket summary logic in cmd_update_progress."""
from __future__ import annotations

import json
import sys
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from cli import _load_summaries, cmd_update_progress
from jira_architect.models import GitInfo


# ---------------------------------------------------------------------------
# _load_summaries
# ---------------------------------------------------------------------------

def test_load_summaries_empty_string():
    assert _load_summaries("") == {}


def test_load_summaries_json_string():
    data = '{"KAN-1": "Epic done", "KAN-2": "Story done"}'
    result = _load_summaries(data)
    assert result == {"KAN-1": "Epic done", "KAN-2": "Story done"}


def test_load_summaries_file(tmp_path):
    f = tmp_path / "summaries.json"
    f.write_text('{"KAN-3": "Sub-task complete"}')
    result = _load_summaries(f"@{f}")
    assert result == {"KAN-3": "Sub-task complete"}


def test_load_summaries_invalid_json_exits():
    with patch("sys.exit") as mock_exit:
        _load_summaries("{not valid json")
        mock_exit.assert_called_once_with(1)


def test_load_summaries_non_dict_exits():
    with patch("sys.exit") as mock_exit:
        _load_summaries('["KAN-1", "KAN-2"]')
        mock_exit.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# cmd_update_progress — per-ticket summaries
# ---------------------------------------------------------------------------

_TICKETS_TREE = {
    "issues": [
        {"key": "KAN-1", "summary": "Epic: crawler", "issuetype": "Epic",
         "status": "In Progress", "priority": "Medium", "labels": [], "parent": None},
        {"key": "KAN-2", "summary": "Story: schedule", "issuetype": "Story",
         "status": "In Progress", "priority": "Medium", "labels": [], "parent": "KAN-1"},
        {"key": "KAN-3", "summary": "Sub-task: impl", "issuetype": "Sub-task",
         "status": "In Progress", "priority": "Medium", "labels": [], "parent": "KAN-2"},
    ],
    "root_keys": ["KAN-1"],
}


def _make_args(summaries=None, summary=None):
    return SimpleNamespace(
        tickets="/fake/tickets.json",
        repo_url="https://github.com/alex85279/repo",
        commit="abcdef1234567890",
        branch="feature/hermes-KAN-1",
        commit_url=None,
        summaries=summaries,
        summary=summary,
    )


def _run(args):
    """Run cmd_update_progress with mocked Jira and config."""
    mock_client = MagicMock()
    mock_client.add_comment.return_value = "comment-id-123"
    with (
        patch("cli._require_config", return_value=MagicMock()),
        patch("cli.JiraClient", return_value=mock_client),
        patch("cli._load_tree", return_value=_TICKETS_TREE),
    ):
        cmd_update_progress(args)
    return mock_client


def test_global_summary_posts_same_to_all():
    client = _run(_make_args(summary="Global summary"))
    assert client.add_comment.call_count == 3
    # All three tickets get a comment
    keys = [c.args[0] for c in client.add_comment.call_args_list]
    assert keys == ["KAN-1", "KAN-2", "KAN-3"]
    # All comments contain the global summary
    for c in client.add_comment.call_args_list:
        assert "Global summary" in c.args[1]


def test_per_ticket_summaries_used():
    summaries = json.dumps({
        "KAN-1": "Epic progress",
        "KAN-2": "Story done",
        "KAN-3": "Sub-task complete",
    })
    client = _run(_make_args(summaries=summaries))
    calls = client.add_comment.call_args_list
    assert "Epic progress" in calls[0].args[1]
    assert "Story done" in calls[1].args[1]
    assert "Sub-task complete" in calls[2].args[1]


def test_per_ticket_fallback_to_global():
    """KAN-1 has per-ticket summary; KAN-2 and KAN-3 fall back to global."""
    summaries = json.dumps({"KAN-1": "Specific for epic"})
    client = _run(_make_args(summaries=summaries, summary="Fallback"))
    calls = client.add_comment.call_args_list
    assert "Specific for epic" in calls[0].args[1]
    assert "Fallback" in calls[1].args[1]
    assert "Fallback" in calls[2].args[1]


def test_tickets_with_no_summary_skipped():
    """Tickets with no per-ticket summary AND no global summary are skipped."""
    summaries = json.dumps({"KAN-1": "Epic only"})
    client = _run(_make_args(summaries=summaries, summary=None))
    assert client.add_comment.call_count == 1
    assert client.add_comment.call_args_list[0].args[0] == "KAN-1"
