"""Tests for the feedback module."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest
from jira_architect.feedback import extract_directives, is_hermes_comment, scan_comments
from jira_architect.models import FeedbackItem


# ---------------------------------------------------------------------------
# is_hermes_comment
# ---------------------------------------------------------------------------

def test_is_hermes_comment_true():
    text = "Some comment\n\n<!-- hermes-marker: progress-2024-01-15T10:00:00Z -->"
    assert is_hermes_comment(text) is True


def test_is_hermes_comment_false():
    text = "@hermes fix: something broken"
    assert is_hermes_comment(text) is False


def test_is_hermes_comment_false_empty():
    assert is_hermes_comment("") is False


# ---------------------------------------------------------------------------
# extract_directives
# ---------------------------------------------------------------------------

def test_extract_approve_arch():
    items = extract_directives("PROJ-1", "c1", "Alice", "2024-01-15T10:00:00Z",
                                "@hermes approve-arch")
    assert len(items) == 1
    assert items[0].directive == "approve-arch"
    assert items[0].content == ""


def test_extract_revise_arch_with_content():
    text = "@hermes revise-arch: Please add a Redis caching layer"
    items = extract_directives("PROJ-1", "c1", "Alice", "2024-01-15T10:00:00Z", text)
    assert len(items) == 1
    assert items[0].directive == "revise-arch"
    assert items[0].content == "Please add a Redis caching layer"


def test_extract_fix_directive():
    text = "I found some issues:\n\n@hermes fix: login returns 500 on invalid email\n@hermes fix: missing rate limiting"
    items = extract_directives("PROJ-2", "c2", "Bob", "2024-01-15T11:00:00Z", text)
    assert len(items) == 2
    assert all(i.directive == "fix" for i in items)
    assert "500" in items[0].content
    assert "rate limiting" in items[1].content


def test_extract_multiple_directives():
    text = (
        "@hermes fix: wrong status code\n"
        "@hermes question: why use JWT?\n"
        "@hermes approve-impl"
    )
    items = extract_directives("PROJ-3", "c3", "Carol", "2024-01-15T12:00:00Z", text)
    assert len(items) == 3
    directives = [i.directive for i in items]
    assert "fix" in directives
    assert "question" in directives
    assert "approve-impl" in directives


def test_skips_hermes_own_comment():
    text = "@hermes fix: something\n<!-- hermes-marker: progress-2024T10:00Z -->"
    items = extract_directives("PROJ-1", "c1", "Hermes", "2024-01-15T10:00:00Z", text)
    assert items == []


def test_case_insensitive_directive():
    items = extract_directives("PROJ-1", "c1", "Alice", "2024-01-15T10:00:00Z",
                                "@hermes Approve-Arch")
    assert len(items) == 1
    assert items[0].directive == "approve-arch"


# ---------------------------------------------------------------------------
# scan_comments
# ---------------------------------------------------------------------------

def test_scan_comments_filters_by_since():
    comments = [
        {
            "_ticket_key": "PROJ-1",
            "id": "c1",
            "author": "Alice",
            "created": "2024-01-10T10:00:00Z",
            "body_text": "@hermes approve-arch",
        },
        {
            "_ticket_key": "PROJ-1",
            "id": "c2",
            "author": "Bob",
            "created": "2024-01-20T10:00:00Z",
            "body_text": "@hermes fix: broken",
        },
    ]
    items = scan_comments(comments, since_iso="2024-01-15T00:00:00Z")
    assert len(items) == 1
    assert items[0].directive == "fix"


def test_scan_comments_excludes_hermes_posts():
    comments = [
        {
            "_ticket_key": "PROJ-1",
            "id": "c1",
            "author": "Hermes Bot",
            "created": "2024-01-20T10:00:00Z",
            "body_text": "Progress update\n<!-- hermes-marker: progress-2024T -->",
        },
    ]
    items = scan_comments(comments)
    assert items == []


def test_scan_comments_no_feedback():
    comments = [
        {
            "_ticket_key": "PROJ-1",
            "id": "c1",
            "author": "Alice",
            "created": "2024-01-20T10:00:00Z",
            "body_text": "Looks good to me! Nice work.",
        },
    ]
    items = scan_comments(comments)
    assert items == []
