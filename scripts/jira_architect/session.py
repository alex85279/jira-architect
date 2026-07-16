"""Session state management for jira-architect polling.

Each active session tracks which tickets to watch, when we last polled,
and the current workflow phase. Sessions persist under:
  ~/.hermes/jira-architect/sessions/<session_id>.json

Feedback notifications are appended to:
  ~/.hermes/jira-architect/notifications.jsonl
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

SESSION_DIR = Path.home() / ".hermes" / "jira-architect" / "sessions"
NOTIFICATIONS_FILE = Path.home() / ".hermes" / "jira-architect" / "notifications.jsonl"

PHASES = ("awaiting_arch", "awaiting_impl", "done")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Session:
    def __init__(
        self,
        session_id: str,
        tickets_file: str,
        ticket_keys: List[str],
        phase: str = "awaiting_arch",
        last_checked: Optional[str] = None,
        created_at: Optional[str] = None,
        label: str = "",
    ) -> None:
        if phase not in PHASES:
            raise ValueError(f"Invalid phase '{phase}'. Must be one of: {PHASES}")
        self.session_id = session_id
        self.tickets_file = tickets_file
        self.ticket_keys = list(ticket_keys)
        self.phase = phase
        self.last_checked = last_checked or _now_iso()
        self.created_at = created_at or _now_iso()
        self.label = label

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "tickets_file": self.tickets_file,
            "ticket_keys": self.ticket_keys,
            "phase": self.phase,
            "last_checked": self.last_checked,
            "created_at": self.created_at,
            "label": self.label,
        }

    def save(self) -> None:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        (SESSION_DIR / f"{self.session_id}.json").write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        )

    def delete(self) -> None:
        path = SESSION_DIR / f"{self.session_id}.json"
        if path.exists():
            path.unlink()

    @classmethod
    def load(cls, session_id: str) -> "Session":
        path = SESSION_DIR / f"{session_id}.json"
        if not path.exists():
            raise RuntimeError(f"Session not found: {session_id}")
        return cls(**json.loads(path.read_text()))

    @classmethod
    def load_all(cls) -> List["Session"]:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        sessions = []
        for p in sorted(SESSION_DIR.glob("*.json")):
            try:
                sessions.append(cls(**json.loads(p.read_text())))
            except Exception:
                pass
        return sessions


def create_session(
    tickets_file: str,
    ticket_keys: List[str],
    label: str = "",
    phase: str = "awaiting_arch",
) -> Session:
    sess = Session(
        session_id=uuid.uuid4().hex[:8],
        tickets_file=tickets_file,
        ticket_keys=ticket_keys,
        label=label,
        phase=phase,
    )
    sess.save()
    return sess


def append_notification(session_id: str, feedback_items: list, checked_at: str) -> None:
    """Append a batch of feedback to the global notifications JSONL file."""
    NOTIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps(
        {
            "session_id": session_id,
            "checked_at": checked_at,
            "feedback": [
                f if isinstance(f, dict) else f.model_dump()
                for f in feedback_items
            ],
        },
        ensure_ascii=False,
    )
    with NOTIFICATIONS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(entry + "\n")


def read_notifications(
    session_id: Optional[str] = None,
    last_n: int = 20,
) -> List[dict]:
    """Return the most recent notifications, optionally filtered by session."""
    if not NOTIFICATIONS_FILE.exists():
        return []
    lines = NOTIFICATIONS_FILE.read_text(encoding="utf-8").strip().splitlines()
    results: List[dict] = []
    for line in lines[-200:]:
        try:
            entry = json.loads(line)
            if session_id is None or entry.get("session_id") == session_id:
                results.append(entry)
        except json.JSONDecodeError:
            pass
    return results[-last_n:]
