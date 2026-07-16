"""Data models for jira-architect."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class JiraIssue(BaseModel):
    key: str
    summary: str
    description: Optional[str] = None
    issue_type: str
    status: str
    priority: str
    labels: List[str] = Field(default_factory=list)
    assignee: Optional[str] = None
    parent_key: Optional[str] = None
    jira_url: str = ""
    children: List["JiraIssue"] = Field(default_factory=list)


class IssueTree(BaseModel):
    """A collection of fetched issues with root-level keys identified."""
    project_key: str
    root_keys: List[str]
    issues: List[JiraIssue]  # flat list of all fetched issues


class FeedbackItem(BaseModel):
    ticket_key: str
    comment_id: str
    author: str
    created: str  # ISO datetime string from Jira
    directive: str  # e.g. "approve-arch", "revise-arch", "fix", "approve-impl", "question"
    content: str   # text after ":", empty for directives with no argument


class GitInfo(BaseModel):
    commit_hash: str
    commit_short: str
    branch: str
    repo_url: str
    commit_url: Optional[str] = None
