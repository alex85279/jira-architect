"""Tests for the progress comment formatter."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from jira_architect.progress import build_design_comment, build_progress_comment
from jira_architect.models import GitInfo


def _make_git_info(commit_url=None):
    return GitInfo(
        commit_hash="a1b2c3d4e5f6789012345678901234567890abcd",
        commit_short="a1b2c3d4",
        branch="feature/hermes-PROJ-42-auth",
        repo_url="https://github.com/company/repo",
        commit_url=commit_url,
    )


# ---------------------------------------------------------------------------
# build_design_comment
# ---------------------------------------------------------------------------

def test_design_comment_contains_hermes_header():
    result = build_design_comment("## Architecture\n\nSome design.")
    assert "Hermes 架構設計計畫" in result


def test_design_comment_contains_design_content():
    result = build_design_comment("## My Design\n\nContent here.")
    assert "My Design" in result
    assert "Content here." in result


def test_design_comment_contains_approve_arch_instruction():
    result = build_design_comment("design content")
    assert "@hermes approve-arch" in result


def test_design_comment_contains_revise_arch_instruction():
    result = build_design_comment("design content")
    assert "@hermes revise-arch" in result


def test_design_comment_contains_hermes_marker():
    result = build_design_comment("design content")
    assert "<!-- hermes-marker:" in result
    assert "design-" in result


# ---------------------------------------------------------------------------
# build_progress_comment
# ---------------------------------------------------------------------------

def test_progress_comment_contains_summary():
    git = _make_git_info()
    result = build_progress_comment("Implemented auth module", git)
    assert "Implemented auth module" in result


def test_progress_comment_contains_branch():
    git = _make_git_info()
    result = build_progress_comment("summary", git)
    assert "feature/hermes-PROJ-42-auth" in result


def test_progress_comment_contains_commit_short():
    git = _make_git_info()
    result = build_progress_comment("summary", git)
    assert "a1b2c3d4" in result


def test_progress_comment_contains_repo_url():
    git = _make_git_info()
    result = build_progress_comment("summary", git)
    assert "https://github.com/company/repo" in result


def test_progress_comment_with_commit_url():
    commit_url = "https://github.com/company/repo/commit/a1b2c3d4e5f6789"
    git = _make_git_info(commit_url=commit_url)
    result = build_progress_comment("summary", git)
    assert commit_url in result


def test_progress_comment_contains_feedback_instructions():
    git = _make_git_info()
    result = build_progress_comment("summary", git)
    assert "@hermes approve-impl" in result
    assert "@hermes fix" in result
    assert "@hermes revise-arch" in result


def test_progress_comment_contains_hermes_marker():
    git = _make_git_info()
    result = build_progress_comment("summary", git)
    assert "<!-- hermes-marker:" in result
    assert "progress-" in result
