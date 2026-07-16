"""Jira REST API v3 client for jira-architect skill.

Operations:
  - test_connection      — verify credentials
  - fetch_issue          — fetch a single issue with its fields
  - fetch_issues_by_jql  — search issues with JQL
  - fetch_children       — recursively fetch parent→children hierarchy
  - add_comment          — post a text comment (converted to ADF)
  - get_comments         — list comments on an issue, optionally filtered by date
"""
from __future__ import annotations

import base64
import re
from typing import Any, Dict, List, Optional
import requests

from .config import ArchitectConfig
from .models import JiraIssue


# ---------------------------------------------------------------------------
# ADF helpers
# ---------------------------------------------------------------------------

def _parse_inline(line: str) -> list:
    """Convert inline markdown (bold, code) to ADF text nodes."""
    nodes: list = []
    pos = 0
    pattern = re.compile(r"\*\*(.+?)\*\*|`(.+?)`")
    for m in pattern.finditer(line):
        if m.start() > pos:
            nodes.append({"type": "text", "text": line[pos:m.start()]})
        if m.group(1) is not None:
            nodes.append({"type": "text", "text": m.group(1), "marks": [{"type": "strong"}]})
        else:
            nodes.append({"type": "text", "text": m.group(2), "marks": [{"type": "code"}]})
        pos = m.end()
    if pos < len(line):
        nodes.append({"type": "text", "text": line[pos:]})
    return nodes or [{"type": "text", "text": line}]


def _para_from_lines(lines: list) -> dict:
    content: list = []
    for i, line in enumerate(lines):
        content.extend(_parse_inline(line))
        if i < len(lines) - 1:
            content.append({"type": "hardBreak"})
    return {"type": "paragraph", "content": content or [{"type": "text", "text": ""}]}


def text_to_adf(md: str) -> dict:
    """Convert markdown text to Atlassian Document Format (ADF)."""
    adf_content: list = []
    current_lines: list = []

    def flush():
        if current_lines:
            adf_content.append(_para_from_lines(current_lines))
            current_lines.clear()

    for raw_line in md.splitlines():
        stripped = raw_line.rstrip()

        # Heading
        hm = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if hm:
            flush()
            level = min(len(hm.group(1)), 6)
            adf_content.append({
                "type": "heading",
                "attrs": {"level": level},
                "content": [{"type": "text", "text": hm.group(2)}],
            })
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            flush()
            adf_content.append({"type": "rule"})
            continue

        # Table row (simplified: just render as code block line)
        # Empty line = paragraph break
        if stripped == "":
            flush()
            continue

        current_lines.append(stripped)

    flush()

    if not adf_content:
        adf_content = [{"type": "paragraph", "content": [{"type": "text", "text": md}]}]

    return {"type": "doc", "version": 1, "content": adf_content}


def extract_text_from_adf(node: Any) -> str:
    """Recursively extract plain text from an ADF node."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    ntype = node.get("type", "")
    if ntype == "text":
        return node.get("text", "")
    if ntype == "hardBreak":
        return "\n"
    children = node.get("content", [])
    parts = [extract_text_from_adf(c) for c in children]
    sep = "\n" if ntype in ("paragraph", "heading", "rule") else ""
    return sep.join(parts) + (sep if sep and parts else "")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class JiraClient:
    def __init__(self, cfg: ArchitectConfig) -> None:
        raw = f"{cfg.email}:{cfg.token}"
        encoded = base64.b64encode(raw.encode()).decode()
        self._base = cfg.url.rstrip("/") + "/rest/api/3"
        self._browse = cfg.url.rstrip("/") + "/browse"
        self._headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def test_connection(self) -> str:
        resp = requests.get(f"{self._base}/myself", headers=self._headers, timeout=10)
        if resp.status_code == 200:
            d = resp.json()
            return f"Connected as: {d.get('displayName', d.get('emailAddress', '?'))}"
        raise RuntimeError(f"Connection failed ({resp.status_code}): {resp.text[:200]}")

    # ------------------------------------------------------------------
    # Issue fetching
    # ------------------------------------------------------------------

    def fetch_issue(self, key: str) -> JiraIssue:
        resp = requests.get(
            f"{self._base}/issue/{key}",
            headers=self._headers,
            params={"fields": "summary,description,issuetype,status,priority,labels,assignee,parent"},
            timeout=15,
        )
        if resp.status_code == 404:
            raise RuntimeError(f"Issue not found: {key}")
        resp.raise_for_status()
        return self._parse_issue(resp.json())

    def fetch_issues_by_jql(self, jql: str, max_results: int = 100) -> List[JiraIssue]:
        issues: List[JiraIssue] = []
        start = 0
        while True:
            resp = requests.post(
                f"{self._base}/issue/search",
                headers=self._headers,
                json={
                    "jql": jql,
                    "startAt": start,
                    "maxResults": min(max_results - len(issues), 50),
                    "fields": ["summary", "description", "issuetype", "status",
                               "priority", "labels", "assignee", "parent"],
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            batch = [self._parse_issue(i) for i in data.get("issues", [])]
            issues.extend(batch)
            if len(issues) >= data.get("total", 0) or not batch:
                break
            start += len(batch)
            if len(issues) >= max_results:
                break
        return issues

    def fetch_children(self, parent_key: str) -> List[JiraIssue]:
        """Fetch direct children of parent_key using JQL."""
        return self.fetch_issues_by_jql(f"parent = {parent_key} ORDER BY created ASC")

    def fetch_epic_tree(self, epic_key: str) -> List[JiraIssue]:
        """Fetch epic + all descendants, returning a flat list."""
        root = self.fetch_issue(epic_key)
        all_issues: List[JiraIssue] = [root]
        self._recurse_children(root, all_issues)
        return all_issues

    def _recurse_children(self, issue: JiraIssue, accumulator: List[JiraIssue]) -> None:
        children = self.fetch_children(issue.key)
        for child in children:
            child.parent_key = issue.key
            accumulator.append(child)
            self._recurse_children(child, accumulator)

    def _parse_issue(self, raw: dict) -> JiraIssue:
        fields = raw.get("fields", {})
        key = raw["key"]
        desc_adf = fields.get("description") or {}
        description = extract_text_from_adf(desc_adf).strip() or None
        parent = fields.get("parent")
        parent_key = parent["key"] if parent else None
        assignee = fields.get("assignee") or {}
        return JiraIssue(
            key=key,
            summary=fields.get("summary", ""),
            description=description,
            issue_type=fields.get("issuetype", {}).get("name", ""),
            status=fields.get("status", {}).get("name", ""),
            priority=fields.get("priority", {}).get("name", "Medium"),
            labels=fields.get("labels", []),
            assignee=assignee.get("displayName") if assignee else None,
            parent_key=parent_key,
            jira_url=f"{self._browse}/{key}",
        )

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def add_comment(self, issue_key: str, text: str) -> str:
        """Post a comment (text converted to ADF). Returns comment ID."""
        adf_body = text_to_adf(text)
        resp = requests.post(
            f"{self._base}/issue/{issue_key}/comment",
            headers=self._headers,
            json={"body": adf_body},
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to comment on {issue_key} ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()["id"]

    def get_comments(self, issue_key: str, since_iso: Optional[str] = None) -> List[Dict]:
        """Return comments as dicts with 'id', 'author', 'created', 'body_text' keys."""
        resp = requests.get(
            f"{self._base}/issue/{issue_key}/comment",
            headers=self._headers,
            params={"maxResults": 100, "orderBy": "created"},
            timeout=15,
        )
        resp.raise_for_status()
        comments = []
        for c in resp.json().get("comments", []):
            created = c.get("created", "")
            if since_iso and created < since_iso:
                continue
            body_text = extract_text_from_adf(c.get("body", {}))
            comments.append({
                "id": c["id"],
                "author": c.get("author", {}).get("displayName", "Unknown"),
                "created": created,
                "body_text": body_text,
                "_ticket_key": issue_key,
            })
        return comments
