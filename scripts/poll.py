#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jira-architect 定期 Polling 腳本。

掃描所有 active sessions 的 Jira tickets，尋找新的 @hermes 回饋，
並將結果：
  1. 寫入 ~/.hermes/jira-architect/notifications.jsonl（永遠執行）
  2. 透過 Discord Webhook 推送通知（若 config 中設定了 webhook_url）

設計為由 cron 每 2 小時執行一次：
  0 */2 * * * /usr/bin/python3 /path/to/jira-architect/scripts/poll.py >> ~/.hermes/jira-architect/poll.log 2>&1

也可手動執行：
  python3 scripts/poll.py --once --verbose
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

from jira_architect import config as cfg_mod
from jira_architect.jira_client import JiraClient
from jira_architect.feedback import scan_comments
from jira_architect.session import Session, append_notification, read_notifications


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Discord webhook notification
# ---------------------------------------------------------------------------

def _send_discord_notification(webhook_url: str, session: Session, items: list) -> None:
    """POST a summary message to a Discord webhook."""
    lines = [
        f"🤖 **Hermes Jira Feedback** — Session `{session.session_id}` ({session.label or ', '.join(session.ticket_keys[:3])})",
        f"🕐 發現 **{len(items)}** 條新的 `@hermes` 回饋：",
        "",
    ]
    for item in items[:10]:  # cap at 10 to avoid Discord 2000-char limit
        content_preview = f": {item['content'][:80]}" if item.get("content") else ""
        lines.append(f"• `[{item['ticket_key']}]` **@hermes {item['directive']}**{content_preview}")

    if len(items) > 10:
        lines.append(f"• … 以及其他 {len(items) - 10} 條回饋")

    lines += [
        "",
        "_請在 Hermes 中輸入「check Jira feedback」查看詳情並處理。_",
    ]

    payload = {"content": "\n".join(lines)}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        _log(f"  WARNING: Discord webhook failed: {e}")


# ---------------------------------------------------------------------------
# Core poll logic
# ---------------------------------------------------------------------------

def poll_once(cfg: cfg_mod.ArchitectConfig, verbose: bool = False) -> int:
    """Run one poll cycle across all active sessions. Returns total feedback count."""
    client = JiraClient(cfg)
    sessions = Session.load_all()
    active = [s for s in sessions if s.phase != "done"]

    if not active:
        if verbose:
            _log("No active sessions to poll (all done or none created).")
        return 0

    _log(f"Polling {len(active)} active session(s)...")
    total = 0

    for sess in active:
        label = sess.label or ", ".join(sess.ticket_keys[:3])
        if verbose:
            _log(f"  Session {sess.session_id} [{label}] — since {sess.last_checked}")

        if not os.path.exists(sess.tickets_file):
            _log(f"  WARNING: tickets file missing for session {sess.session_id}: {sess.tickets_file}")
            continue

        try:
            with open(sess.tickets_file, encoding="utf-8") as fh:
                tree = json.load(fh)
        except Exception as e:
            _log(f"  ERROR loading tickets for session {sess.session_id}: {e}")
            continue

        all_comments = []
        for issue in tree.get("issues", []):
            try:
                comments = client.get_comments(issue["key"], since_iso=sess.last_checked)
                all_comments.extend(comments)
            except Exception as e:
                _log(f"  ERROR fetching comments for {issue['key']}: {e}")

        items = scan_comments(all_comments, since_iso=sess.last_checked)
        checked_at = _now_iso()

        # Always advance the last_checked timestamp
        sess.last_checked = checked_at
        sess.save()

        if not items:
            if verbose:
                _log(f"  No new @hermes feedback in session {sess.session_id}.")
            continue

        _log(f"  [{sess.session_id}] Found {len(items)} directive(s):")
        for item in items:
            content_preview = f": {item.content[:60]}" if item.content else ""
            _log(f"    [{item.ticket_key}] @hermes {item.directive}{content_preview}")

        # 1. Write to notifications file
        append_notification(sess.session_id, items, checked_at)

        # 2. Discord webhook (if configured)
        webhook_url = getattr(cfg, "discord_webhook_url", None)
        if webhook_url:
            _send_discord_notification(
                webhook_url,
                sess,
                [i.model_dump() for i in items],
            )

        total += len(items)

    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="jira-architect Jira feedback poller (designed for cron, every 2h)"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Poll once and exit (default behaviour when run by cron)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print status even when no new feedback is found",
    )
    args = parser.parse_args()

    cfg = cfg_mod.load()
    if cfg is None:
        _log("ERROR: No config found. Run: python3 scripts/cli.py config set ...")
        sys.exit(1)

    _log("jira-architect poller: starting poll cycle.")
    total = poll_once(cfg, verbose=args.verbose)
    _log(f"Poll complete — {total} new feedback item(s) found.")


if __name__ == "__main__":
    main()
