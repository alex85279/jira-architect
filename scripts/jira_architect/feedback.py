"""Parse @hermes directives from Jira comment text.

Protocol:
  @hermes <directive>                 — directive with no argument
  @hermes <directive>: <content>      — directive with a text argument

The @hermes token must appear at the start of any line in the comment.
Comments posted by Hermes itself (identified by <!-- hermes-marker: ... -->)
are excluded from feedback results.
"""
from __future__ import annotations

import re
from typing import List

from .models import FeedbackItem

# Matches "@hermes <directive>" optionally followed by ": <content>"
# Must be at start of a line (after optional leading whitespace)
_DIRECTIVE_RE = re.compile(
    r"^\s*@hermes\s+([a-zA-Z][a-zA-Z0-9-]*)(?:\s*:\s*(.+?))?$",
    re.MULTILINE,
)

# Identifies comments posted by Hermes (invisible HTML comment tag)
_MARKER_RE = re.compile(r"<!--\s*hermes-marker:", re.IGNORECASE)


def is_hermes_comment(text: str) -> bool:
    """Return True if the comment was originally posted by Hermes."""
    return bool(_MARKER_RE.search(text))


def extract_directives(
    ticket_key: str,
    comment_id: str,
    author: str,
    created: str,
    text: str,
) -> List[FeedbackItem]:
    """Extract all @hermes directives from a comment body.

    Skips comments that contain the hermes-marker (i.e. posted by Hermes itself).
    """
    if is_hermes_comment(text):
        return []

    results: List[FeedbackItem] = []
    for m in _DIRECTIVE_RE.finditer(text):
        directive = m.group(1).lower()
        content = (m.group(2) or "").strip()
        results.append(
            FeedbackItem(
                ticket_key=ticket_key,
                comment_id=comment_id,
                author=author,
                created=created,
                directive=directive,
                content=content,
            )
        )
    return results


def scan_comments(comments: List[dict], since_iso: str = "") -> List[FeedbackItem]:
    """Scan a list of comment dicts (from JiraClient.get_comments) for @hermes directives.

    Parameters
    ----------
    comments:  List of comment dicts with keys: id, author, created, body_text, _ticket_key
    since_iso: ISO 8601 datetime string; only process comments created at or after this time
    """
    results: List[FeedbackItem] = []
    for c in comments:
        if since_iso and c.get("created", "") < since_iso:
            continue
        items = extract_directives(
            ticket_key=c.get("_ticket_key", ""),
            comment_id=c["id"],
            author=c.get("author", "Unknown"),
            created=c.get("created", ""),
            text=c.get("body_text", ""),
        )
        results.extend(items)
    return results
