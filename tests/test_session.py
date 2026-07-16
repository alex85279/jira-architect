"""Tests for session state management."""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest
from unittest.mock import patch
from pathlib import Path

from jira_architect.session import (
    Session, create_session, append_notification, read_notifications, PHASES
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_dir(tmp_path):
    """Patch SESSION_DIR and NOTIFICATIONS_FILE to use tmp_path."""
    return tmp_path


# ---------------------------------------------------------------------------
# Session creation and persistence
# ---------------------------------------------------------------------------

def test_create_session_fields(tmp_path):
    with patch("jira_architect.session.SESSION_DIR", tmp_path):
        sess = create_session(
            tickets_file="/tmp/test.json",
            ticket_keys=["PROJ-1", "PROJ-2"],
            label="test session",
            phase="awaiting_arch",
        )
    assert len(sess.session_id) == 8
    assert sess.tickets_file == "/tmp/test.json"
    assert sess.ticket_keys == ["PROJ-1", "PROJ-2"]
    assert sess.label == "test session"
    assert sess.phase == "awaiting_arch"
    assert sess.last_checked  # non-empty ISO string
    assert sess.created_at


def test_session_saves_and_loads(tmp_path):
    with patch("jira_architect.session.SESSION_DIR", tmp_path):
        sess = create_session("/tmp/t.json", ["PROJ-1"], label="load test")
        sid = sess.session_id
        loaded = Session.load(sid)

    assert loaded.session_id == sid
    assert loaded.label == "load test"
    assert loaded.ticket_keys == ["PROJ-1"]


def test_session_load_all(tmp_path):
    with patch("jira_architect.session.SESSION_DIR", tmp_path):
        create_session("/tmp/a.json", ["PROJ-1"])
        create_session("/tmp/b.json", ["PROJ-2"])
        sessions = Session.load_all()
    assert len(sessions) == 2


def test_session_save_updates_phase(tmp_path):
    with patch("jira_architect.session.SESSION_DIR", tmp_path):
        sess = create_session("/tmp/t.json", ["PROJ-1"])
        sess.phase = "awaiting_impl"
        sess.save()
        loaded = Session.load(sess.session_id)
    assert loaded.phase == "awaiting_impl"


def test_session_invalid_phase():
    with pytest.raises(ValueError):
        Session(
            session_id="abc",
            tickets_file="/tmp/t.json",
            ticket_keys=["PROJ-1"],
            phase="invalid_phase",
        )


def test_session_delete(tmp_path):
    with patch("jira_architect.session.SESSION_DIR", tmp_path):
        sess = create_session("/tmp/t.json", ["PROJ-1"])
        sid = sess.session_id
        sess.delete()
        with pytest.raises(RuntimeError):
            Session.load(sid)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def test_append_and_read_notifications(tmp_path):
    notif_file = tmp_path / "notifications.jsonl"
    fake_items = [
        {"ticket_key": "PROJ-1", "directive": "fix", "content": "broken", "comment_id": "c1", "author": "Alice", "created": "2024-01-20T10:00:00Z"}
    ]
    with patch("jira_architect.session.NOTIFICATIONS_FILE", notif_file):
        append_notification("sess1", fake_items, "2024-01-20T10:00:00Z")
        entries = read_notifications()

    assert len(entries) == 1
    assert entries[0]["session_id"] == "sess1"
    assert len(entries[0]["feedback"]) == 1


def test_read_notifications_filter_by_session(tmp_path):
    notif_file = tmp_path / "notifications.jsonl"
    with patch("jira_architect.session.NOTIFICATIONS_FILE", notif_file):
        append_notification("sess1", [{"ticket_key": "A", "directive": "fix", "content": "", "comment_id": "c1", "author": "X", "created": "2024-01-20T00:00:00Z"}], "2024-01-20T10:00:00Z")
        append_notification("sess2", [{"ticket_key": "B", "directive": "approve-impl", "content": "", "comment_id": "c2", "author": "Y", "created": "2024-01-20T00:00:00Z"}], "2024-01-20T11:00:00Z")
        entries_1 = read_notifications(session_id="sess1")
        entries_2 = read_notifications(session_id="sess2")

    assert len(entries_1) == 1
    assert entries_1[0]["session_id"] == "sess1"
    assert len(entries_2) == 1
    assert entries_2[0]["session_id"] == "sess2"


def test_read_notifications_empty(tmp_path):
    notif_file = tmp_path / "notifications.jsonl"
    with patch("jira_architect.session.NOTIFICATIONS_FILE", notif_file):
        entries = read_notifications()
    assert entries == []
