"""Format progress and design comments posted to Jira by Hermes.

All comments include an invisible <!-- hermes-marker: ... --> tag so
the feedback scanner can exclude them from user feedback detection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .models import GitInfo


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_display() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _commit_url_for(git: GitInfo) -> Optional[str]:
    if git.commit_url:
        return git.commit_url
    url = git.repo_url.rstrip("/").removesuffix(".git")
    if "github.com" in url or "gitlab.com" in url:
        return f"{url}/commit/{git.commit_hash}"
    return None


def build_design_comment(design_md: str) -> str:
    """Wrap an architecture design markdown doc with Hermes header/footer."""
    ts_display = _now_display()
    ts_marker = _now_iso()

    header = f"""\
🤖 **Hermes 架構設計計畫**

📅 {ts_display}

---

"""
    footer = f"""

---

_如需提供回饋，請在此 Jira 留言欄輸入以下指令：_

| 指令 | 說明 |
|------|------|
| `@hermes approve-arch` | ✅ 確認設計，請開始實作 |
| `@hermes revise-arch: <描述>` | 🔄 要求修改架構，說明需要調整的地方 |
| `@hermes question: <問題>` | ❓ 詢問設計相關問題 |

<!-- hermes-marker: design-{ts_marker} -->"""

    return header + design_md + footer


def build_progress_comment(summary: str, git: GitInfo) -> str:
    """Build a standardized progress comment with Git info and feedback instructions."""
    ts_display = _now_display()
    ts_marker = _now_iso()

    commit_url = _commit_url_for(git)
    if commit_url:
        commit_ref = f"[`{git.commit_short}`]({commit_url})"
    else:
        commit_ref = f"`{git.commit_short}`"

    return f"""\
🤖 **Hermes 進度更新**

📅 {ts_display}

---

📋 **更新摘要**

{summary}

---

🔗 **Git 資訊**

| 項目 | 值 |
|------|-----|
| Repo | {git.repo_url} |
| Branch | `{git.branch}` |
| Commit | {commit_ref} |

---

_如需提供回饋，請在此 Jira 留言欄輸入以下指令：_

| 指令 | 說明 |
|------|------|
| `@hermes approve-impl` | ✅ 確認實作沒問題，可以 merge |
| `@hermes fix: <描述>` | 🔧 請求程式碼修正，說明問題所在 |
| `@hermes revise-arch: <描述>` | 🔄 要求重新設計架構 |
| `@hermes question: <問題>` | ❓ 詢問實作相關問題 |

<!-- hermes-marker: progress-{ts_marker} -->"""
