#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jira-architect CLI — 獨立執行入口。

子命令：
  config set           — 儲存 Jira + Git 設定
  config show          — 顯示目前設定（token 遮罩）
  config test          — 測試 Jira 連線

  fetch                — 從 Jira 抓取 tickets，存成 JSON
  post-design          — 將架構設計 Markdown 發布到 Jira 作為留言
  check-feedback       — 掃描所有 tickets 的 @hermes 回饋指令

  git-commit           — 建立 branch、commit 並 push
  update-progress      — 在所有 tickets 貼進度更新留言（含 Git 資訊）

零 discord / hermes 依賴，可直接在終端機執行。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jira_architect import config as cfg_mod
from jira_architect.jira_client import JiraClient
from jira_architect.models import IssueTree, GitInfo
from jira_architect import git_client as git
from jira_architect.feedback import scan_comments
from jira_architect.progress import build_design_comment, build_progress_comment
from jira_architect.session import (
    Session, create_session, read_notifications, PHASES, SESSION_DIR,
)


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def cmd_config_set(args) -> None:
    cfg_mod.save(
        url=args.url,
        email=args.email,
        token=args.token,
        project_key=args.project,
        git_repo_path=args.git_repo,
        git_remote=args.git_remote,
        branch_prefix=args.branch_prefix,
        discord_webhook_url=args.webhook,
    )
    print(f"Config saved to {cfg_mod.CONFIG_PATH}")


def cmd_config_show(args) -> None:
    cfg = cfg_mod.load()
    if cfg is None:
        print("No config found. Run: python scripts/cli.py config set --help")
        return
    masked = cfg.token[:4] + "****" + cfg.token[-4:] if len(cfg.token) > 8 else "****"
    print(f"Jira URL     : {cfg.url}")
    print(f"Email        : {cfg.email}")
    print(f"Token        : {masked}")
    print(f"Project      : {cfg.project_key}")
    print(f"Git repo     : {cfg.git_repo_path or '(not set)'}")
    print(f"Git remote   : {cfg.git_remote}")
    print(f"Branch prefix: {cfg.branch_prefix}")
    print(f"Discord wbhk : {cfg.discord_webhook_url or '(not set)'}")


def cmd_config_test(args) -> None:
    cfg = _require_config()
    client = JiraClient(cfg)
    msg = client.test_connection()
    print(f"✅ {msg}")


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def cmd_fetch(args) -> None:
    cfg = _require_config()
    client = JiraClient(cfg)

    issues = []

    if args.epic:
        print(f"Fetching epic {args.epic} and all children...")
        issues = client.fetch_epic_tree(args.epic)
        root_keys = [args.epic]

    elif args.tickets:
        keys = [k.strip() for k in args.tickets.split(",") if k.strip()]
        print(f"Fetching {len(keys)} ticket(s)...")
        for k in keys:
            issues.append(client.fetch_issue(k))
        root_keys = keys

    elif args.jql:
        print(f"Running JQL: {args.jql}")
        issues = client.fetch_issues_by_jql(args.jql)
        root_keys = [i.key for i in issues if i.parent_key is None]
        if not root_keys:
            root_keys = [i.key for i in issues[:1]]

    else:
        print("ERROR: one of --epic, --tickets, or --jql is required", file=sys.stderr)
        sys.exit(1)

    if not issues:
        print("No issues found.", file=sys.stderr)
        sys.exit(1)

    # Determine project key
    project_key = args.project or (cfg.project_key if cfg else issues[0].key.split("-")[0])

    tree = IssueTree(
        project_key=project_key,
        root_keys=root_keys,
        issues=issues,
    )

    output_path = args.output or "/tmp/ja-tickets.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(tree.model_dump(), f, ensure_ascii=False, indent=2)

    print(f"\nFetched {len(issues)} issue(s):")
    type_order = {"Epic": 0, "Story": 1, "Sub-task": 2, "Task": 2}
    for issue in sorted(issues, key=lambda i: (type_order.get(i.issue_type, 9), i.key)):
        indent = "  " if issue.parent_key else ""
        indent = "    " if issue.parent_key and any(
            i.key == issue.parent_key and i.parent_key for i in issues
        ) else indent
        print(f"  {indent}[{issue.issue_type.upper()[:5]:5}] {issue.key}: {issue.summary}")

    print(f"\nSaved to {output_path}")


# ---------------------------------------------------------------------------
# post-design
# ---------------------------------------------------------------------------

def cmd_post_design(args) -> None:
    cfg = _require_config()
    client = JiraClient(cfg)

    tree = _load_tree(args.tickets)

    with open(args.design_file, encoding="utf-8") as f:
        design_md = f.read()

    comment_text = build_design_comment(design_md)

    # Post to root-level tickets only (usually the Epic)
    posted = []
    for key in tree["root_keys"]:
        comment_id = client.add_comment(key, comment_text)
        posted.append({"ticket": key, "comment_id": comment_id})
        print(f"✅ Posted design comment to {key} (comment ID: {comment_id})")

    print(
        "\nFeedback instructions are included in the comment.\n"
        "Users can reply with:\n"
        "  @hermes approve-arch         — to approve the design\n"
        "  @hermes revise-arch: <text>  — to request changes\n"
        "  @hermes question: <text>     — to ask a question"
    )
    # JSON output for agent to capture post timestamp
    from datetime import datetime, timezone
    print(
        json.dumps(
            {
                "posted": posted,
                "posted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            indent=2,
        )
    )


# ---------------------------------------------------------------------------
# check-feedback
# ---------------------------------------------------------------------------

def cmd_check_feedback(args) -> None:
    cfg = _require_config()
    client = JiraClient(cfg)
    tree = _load_tree(args.tickets)

    since = args.since or ""
    all_comments = []
    for issue in tree["issues"]:
        comments = client.get_comments(issue["key"], since_iso=since)
        all_comments.extend(comments)

    items = scan_comments(all_comments, since_iso=since)

    result = {
        "has_new_feedback": len(items) > 0,
        "count": len(items),
        "since": since or "(all time)",
        "items": [i.model_dump() for i in items],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# git-commit
# ---------------------------------------------------------------------------

def cmd_git_commit(args) -> None:
    cfg = cfg_mod.load()
    repo_path = args.repo or (cfg.git_repo_path if cfg else None)
    if not repo_path:
        print(
            "ERROR: --repo is required (or set git_repo_path in config)",
            file=sys.stderr,
        )
        sys.exit(1)

    remote = args.remote or (cfg.git_remote if cfg else "origin")

    print(f"Switching to branch: {args.branch}")
    git.ensure_branch(repo_path, args.branch)

    print(f"Committing all changes...")
    commit_hash = git.commit_all(repo_path, args.message)
    commit_short = commit_hash[:8]
    print(f"Committed: {commit_short}")

    if args.push:
        print(f"Pushing {args.branch} to {remote}...")
        git.push(repo_path, remote, args.branch)
        print("Push complete.")

    repo_url_raw = git.get_remote_url(repo_path, remote) or repo_path
    repo_url = git.normalize_repo_url(repo_url_raw)
    commit_url = git.build_commit_url(repo_url, commit_hash)

    git_info = GitInfo(
        commit_hash=commit_hash,
        commit_short=commit_short,
        branch=args.branch,
        repo_url=repo_url,
        commit_url=commit_url,
    )
    print(json.dumps(git_info.model_dump(), ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# update-progress
# ---------------------------------------------------------------------------

def cmd_update_progress(args) -> None:
    cfg = _require_config()
    client = JiraClient(cfg)
    tree = _load_tree(args.tickets)

    git_info = GitInfo(
        commit_hash=args.commit,
        commit_short=args.commit[:8],
        branch=args.branch,
        repo_url=args.repo_url,
        commit_url=args.commit_url,
    )

    comment_text = build_progress_comment(args.summary, git_info)

    posted = []
    for issue in tree["issues"]:
        comment_id = client.add_comment(issue["key"], comment_text)
        posted.append({"ticket": issue["key"], "comment_id": comment_id})
        print(f"✅ Updated {issue['key']}: {issue['summary'][:60]}")

    print(f"\nProgress comment posted to {len(posted)} ticket(s).")
    print(json.dumps({"posted": posted}, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# session
# ---------------------------------------------------------------------------

def cmd_session_start(args) -> None:
    tree = _load_tree(args.tickets)
    ticket_keys = [i["key"] for i in tree["issues"]]
    label = args.label or tree["root_keys"][0] if tree.get("root_keys") else ""
    sess = create_session(
        tickets_file=args.tickets,
        ticket_keys=ticket_keys,
        label=label,
        phase=args.phase,
    )
    print(f"✅ Session created: {sess.session_id}")
    print(f"   Label   : {sess.label}")
    print(f"   Tickets : {', '.join(ticket_keys)}")
    print(f"   Phase   : {sess.phase}")
    print(f"   Polling : every 2h via cron (run install-cron.sh to activate)")
    print(json.dumps(sess.to_dict(), indent=2, ensure_ascii=False))


def cmd_session_list(args) -> None:
    sessions = Session.load_all()
    if not sessions:
        print("No active sessions.")
        return
    print(f"{'ID':10} {'Phase':18} {'Label / Keys':35} {'Last checked':25}")
    print("-" * 95)
    for s in sessions:
        label = s.label or ", ".join(s.ticket_keys[:3])
        print(f"{s.session_id:10} {s.phase:18} {label[:35]:35} {s.last_checked}")


def cmd_session_update(args) -> None:
    sess = Session.load(args.id)
    sess.phase = args.phase
    sess.save()
    print(f"✅ Session {args.id} phase updated to: {args.phase}")


def cmd_session_close(args) -> None:
    sess = Session.load(args.id)
    if args.delete:
        sess.delete()
        print(f"🗑  Session {args.id} deleted.")
    else:
        sess.phase = "done"
        sess.save()
        print(f"✅ Session {args.id} marked as done (polling will skip it).")


# ---------------------------------------------------------------------------
# notifications
# ---------------------------------------------------------------------------

def cmd_notifications(args) -> None:
    entries = read_notifications(session_id=args.session, last_n=args.last)
    if not entries:
        print(json.dumps({"has_notifications": False, "entries": []}, indent=2))
        return
    print(json.dumps({"has_notifications": True, "count": len(entries), "entries": entries},
                     ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_config() -> cfg_mod.ArchitectConfig:
    cfg = cfg_mod.load()
    if cfg is None:
        print(
            "No config found. Run:\n"
            "  python scripts/cli.py config set --url ... --email ... --token ... --project ...",
            file=sys.stderr,
        )
        sys.exit(1)
    return cfg


def _load_tree(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: tickets file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="jira-architect — 架構設計、程式實作、Jira 進度追蹤",
    )
    sub = parser.add_subparsers(dest="command")

    # --- config ---
    config_p = sub.add_parser("config", help="Manage configuration")
    config_sub = config_p.add_subparsers(dest="config_cmd")

    cs = config_sub.add_parser("set", help="Save Jira + Git config")
    cs.add_argument("--url", required=True, help="Jira base URL")
    cs.add_argument("--email", required=True, help="Jira account email")
    cs.add_argument("--token", required=True, help="Jira API token")
    cs.add_argument("--project", required=True, help="Default project key")
    cs.add_argument("--git-repo", default=None, help="Local git repo path")
    cs.add_argument("--git-remote", default="origin", help="Git remote name")
    cs.add_argument("--branch-prefix", default="feature/hermes-", help="Branch name prefix")
    cs.add_argument("--webhook", default=None,
                    help="Discord webhook URL for polling notifications (optional)")

    config_sub.add_parser("show", help="Show current config")
    config_sub.add_parser("test", help="Test Jira connection")

    # --- fetch ---
    fp = sub.add_parser("fetch", help="Fetch Jira tickets")
    fetch_grp = fp.add_mutually_exclusive_group(required=True)
    fetch_grp.add_argument("--epic", help="Epic key to fetch with all children")
    fetch_grp.add_argument("--tickets", help="Comma-separated ticket keys")
    fetch_grp.add_argument("--jql", help="JQL query string")
    fp.add_argument("--output", default="/tmp/ja-tickets.json", help="Output JSON path")
    fp.add_argument("--project", default=None, help="Override project key")

    # --- post-design ---
    pd = sub.add_parser("post-design", help="Post architecture design to Jira")
    pd.add_argument("--tickets", required=True, help="Tickets JSON path from fetch")
    pd.add_argument("--design-file", required=True, help="Architecture design Markdown file")

    # --- check-feedback ---
    cf = sub.add_parser("check-feedback", help="Scan @hermes feedback in Jira comments")
    cf.add_argument("--tickets", required=True, help="Tickets JSON path from fetch")
    cf.add_argument("--since", default="", help="ISO 8601 datetime; only scan newer comments")

    # --- git-commit ---
    gc = sub.add_parser("git-commit", help="Create branch, commit, and optionally push")
    gc.add_argument("--repo", default=None, help="Local repo path (overrides config)")
    gc.add_argument("--branch", required=True, help="Branch name")
    gc.add_argument("--message", required=True, help="Commit message")
    gc.add_argument("--push", action="store_true", help="Push after commit")
    gc.add_argument("--remote", default=None, help="Remote name (overrides config)")

    # --- update-progress ---
    up = sub.add_parser("update-progress", help="Post progress comment to all tickets")
    up.add_argument("--tickets", required=True, help="Tickets JSON path from fetch")
    up.add_argument("--repo-url", required=True, help="Git repo web URL")
    up.add_argument("--commit", required=True, help="Full commit hash")
    up.add_argument("--branch", required=True, help="Branch name")
    up.add_argument("--summary", required=True, help="Plain-text progress summary")
    up.add_argument("--commit-url", default=None, help="Direct URL to the commit (optional)")

    # --- session ---
    sess_p = sub.add_parser("session", help="Manage polling sessions")
    sess_sub = sess_p.add_subparsers(dest="session_cmd")

    ss = sess_sub.add_parser("start", help="Register tickets for periodic polling")
    ss.add_argument("--tickets", required=True, help="Tickets JSON path from fetch")
    ss.add_argument("--label", default="", help="Human-readable label for this session")
    ss.add_argument("--phase", default="awaiting_arch", choices=list(PHASES),
                    help="Initial workflow phase")

    sess_sub.add_parser("list", help="List all active sessions")

    su = sess_sub.add_parser("update-phase", help="Update the workflow phase of a session")
    su.add_argument("--id", required=True, help="Session ID")
    su.add_argument("--phase", required=True, choices=list(PHASES))

    sc = sess_sub.add_parser("close", help="Mark a session as done (or delete it)")
    sc.add_argument("--id", required=True, help="Session ID")
    sc.add_argument("--delete", action="store_true",
                    help="Permanently delete instead of marking done")

    # --- notifications ---
    np = sub.add_parser("notifications", help="Read accumulated feedback notifications")
    np.add_argument("--session", default=None, help="Filter by session ID")
    np.add_argument("--last", type=int, default=20, help="Return at most N entries (default 20)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "config":
        if args.config_cmd == "set":
            cmd_config_set(args)
        elif args.config_cmd == "show":
            cmd_config_show(args)
        elif args.config_cmd == "test":
            cmd_config_test(args)
        else:
            parser.parse_args(["config", "--help"])

    elif args.command == "fetch":
        cmd_fetch(args)
    elif args.command == "post-design":
        cmd_post_design(args)
    elif args.command == "check-feedback":
        cmd_check_feedback(args)
    elif args.command == "git-commit":
        cmd_git_commit(args)
    elif args.command == "update-progress":
        cmd_update_progress(args)

    elif args.command == "session":
        if args.session_cmd == "start":
            cmd_session_start(args)
        elif args.session_cmd == "list":
            cmd_session_list(args)
        elif args.session_cmd == "update-phase":
            cmd_session_update(args)
        elif args.session_cmd == "close":
            cmd_session_close(args)
        else:
            parser.parse_args(["session", "--help"])

    elif args.command == "notifications":
        cmd_notifications(args)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
