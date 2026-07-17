# jira-architect

> Hermes skill — 根據 Jira tickets 進行架構設計、程式實作與進度追蹤，並透過 Jira 留言的 `@hermes` 指令接收回饋，支援架構修訂與程式修正的完整循環。

---

## 目錄

1. [功能概覽](#功能概覽)
2. [快速開始](#快速開始)
3. [完整工作流程](#完整工作流程)
4. [定時 Polling 設定](#定時-polling-設定)
5. [@hermes 回饋協議](#hermes-回饋協議)
6. [CLI 指令參考](#cli-指令參考)
7. [檔案結構](#檔案結構)

---

## 功能概覽

```
Jira Tickets
    │
    ▼  fetch
  讀取需求
    │
    ▼  (Agent 推理)
  生成架構設計 Markdown
    │
    ▼  post-design
  發布到 Jira，等待確認
    │
    ▼  @hermes approve-arch (Jira 留言)
  ──────────────────────────────────────
    │  (cron 每 2h 偵測)
    ▼  (Agent 推理)
  生成程式碼，寫入 repo
    │
    ▼  git-commit --push
  commit & push
    │
    ▼  update-progress
  所有 tickets 記錄 Git 資訊 + 摘要
    │
    ▼  @hermes fix / approve-impl (Jira 留言)
  ──────────────────────────────────────
    │  (cron 每 2h 偵測，Discord webhook 通知)
    ▼
  修正程式 / 確認完成
```

---

## 快速開始

> **注意：** config、session、polling 都需在 **container 內**（hermes 身份）執行，不是在 host 上直接執行。

```bash
# 1. 設定 Jira 連線、Git repo 與 Discord Webhook
docker exec -u hermes hermes-gateway python3 \
  /opt/data/external-skills/jira-architect/scripts/cli.py config set \
  --url "https://yourcompany.atlassian.net" \
  --email "user@company.com" \
  --token "YOUR_JIRA_API_TOKEN" \
  --project "PROJ" \
  --webhook "https://discord.com/api/webhooks/..."   # Discord 頻道 Webhook

# 2. 測試連線
docker exec -u hermes hermes-gateway python3 \
  /opt/data/external-skills/jira-architect/scripts/cli.py config test

# 3. 安裝 cron job（每台機器只需執行一次）
POLL_CMD="0 */2 * * * docker exec -u hermes hermes-gateway python3 /opt/data/external-skills/jira-architect/scripts/poll.py --once >> /tmp/jira-architect-poll.log 2>&1"
(crontab -l 2>/dev/null | grep -v "jira-architect"; echo "$POLL_CMD") | crontab -

# 4. 手動測試一次 polling
docker exec -u hermes hermes-gateway python3 \
  /opt/data/external-skills/jira-architect/scripts/poll.py --once --verbose

# 5. 開始使用：抓取 tickets
docker exec -u hermes hermes-gateway python3 \
  /opt/data/external-skills/jira-architect/scripts/cli.py \
  fetch --epic PROJ-42 --output /tmp/ja-tickets.json
```

**config 儲存位置（container 內）：** `/opt/data/.hermes/jira-architect.json`  
**Sessions & 通知（container 內）：** `/opt/data/.hermes/jira-architect/`

---

## 完整工作流程

### 步驟一：Fetch Jira Tickets

```bash
# 抓取一個 Epic 及其所有子 ticket（Story、Sub-task）
python scripts/cli.py fetch --epic PROJ-42 --output /tmp/ja-tickets.json

# 或指定多個 tickets
python scripts/cli.py fetch --tickets PROJ-42,PROJ-43,PROJ-44 --output /tmp/ja-tickets.json

# 或用 JQL
python scripts/cli.py fetch --jql "sprint in openSprints() AND project=PROJ" --output /tmp/ja-tickets.json
```

輸出 `/tmp/ja-tickets.json`，包含所有 tickets 的完整資訊（summary、description、status 等）。

---

### 步驟二：架構設計（Agent 推理）

Agent（Hermes/LLM）讀取 `/tmp/ja-tickets.json`，生成包含以下章節的架構設計 Markdown：

1. **系統概觀** — 目標與邊界
2. **技術選型** — 語言、框架、資料庫及選擇理由
3. **系統架構圖** — Mermaid 或 ASCII 圖
4. **模組拆解** — 各模組職責與接口
5. **資料模型** — 主要 entities 與 schema
6. **API 設計** — 主要 endpoints（method、path、request/response）
7. **非功能性需求** — 安全性、效能、擴展性
8. **實作計畫** — 分階段步驟

儲存設計文件：
```bash
# 將 Agent 生成的 Markdown 存到暫存檔
python -c "
content = '''<架構設計 Markdown>'''
open('/tmp/ja-design.md', 'w').write(content)
"
```

---

### 步驟三：發布架構設計到 Jira

```bash
python scripts/cli.py post-design \
  --tickets /tmp/ja-tickets.json \
  --design-file /tmp/ja-design.md
```

設計文件會作為留言發布到所有 root-level tickets（通常是 Epic）。  
輸出包含 `posted_at` 時間戳，記錄此值供後續追蹤使用。

**同時啟動 polling session：**

```bash
python scripts/cli.py session start \
  --tickets /tmp/ja-tickets.json \
  --label "PROJ-42 auth system" \
  --phase awaiting_arch
```

記錄輸出的 `session_id`（例如 `a1b2c3d4`），後續查詢通知時使用。

---

### 步驟四：等待架構確認

**方式 A — Jira 留言（cron 自動偵測）：**

使用者在 Jira 對應 ticket 留言 `@hermes approve-arch`，  
cron 每 2 小時執行 `poll.py`，偵測到後寫入通知並推送 Discord。

查詢通知：
```bash
python scripts/cli.py notifications --session a1b2c3d4
```

**方式 B — 即時掃描：**

```bash
python scripts/cli.py check-feedback \
  --tickets /tmp/ja-tickets.json \
  --since "2024-01-15T10:00:00Z"
```

根據 `directive` 決定下一步：

| directive | 行動 |
|-----------|------|
| `approve-arch` | 更新 phase → 繼續步驟五 |
| `revise-arch: <描述>` | 返回步驟二修訂，重新 post-design |
| `question: <問題>` | Agent 回答問題後繼續等待 |

確認後更新 session phase：
```bash
python scripts/cli.py session update-phase --id a1b2c3d4 --phase awaiting_impl
```

---

### 步驟五：程式實作（Agent 推理）

Agent 根據已確認的架構設計，直接在 git repo 目錄中建立/修改程式碼。

實作完成後 commit 並 push：

```bash
python scripts/cli.py git-commit \
  --repo "/path/to/repo" \
  --branch "feature/hermes-PROJ-42-user-auth" \
  --message "feat(PROJ-42): implement user authentication system" \
  --push
```

輸出 JSON：
```json
{
  "commit_hash": "a1b2c3d4e5f6789...",
  "commit_short": "a1b2c3d4",
  "branch": "feature/hermes-PROJ-42-user-auth",
  "repo_url": "https://github.com/company/repo",
  "commit_url": "https://github.com/company/repo/commit/a1b2c3d4e5f6789"
}
```

---

### 步驟六：更新所有 Jira Tickets 進度

在**所有相關 tickets**（Epic + Story + Sub-task）貼上標準化的進度留言：

```bash
python scripts/cli.py update-progress \
  --tickets /tmp/ja-tickets.json \
  --repo-url "https://github.com/company/repo" \
  --commit "a1b2c3d4e5f6789..." \
  --branch "feature/hermes-PROJ-42-user-auth" \
  --summary "實作了使用者認證系統，包含 JWT token 管理、Email 登入 API endpoint 與 input validation。所有單元測試通過（15/15）。"
```

每個 ticket 會收到：
- 📋 更新摘要
- 🌿 branch 名稱
- 📝 commit hash（含 GitHub/GitLab 連結）
- 🔗 repo URL
- `@hermes` 回饋指引

---

### 步驟七：回饋循環

cron 每 2 小時自動執行 `poll.py`，有新回饋時寫入通知檔並推送 Discord。

查詢通知：
```bash
python scripts/cli.py notifications --session a1b2c3d4
```

根據回饋決定行動：

| directive | 行動 |
|-----------|------|
| `approve-impl` | ✅ 結束 session：`session close --id a1b2c3d4` |
| `fix: <描述>` | 🔧 修改程式碼，重新執行步驟五、六 |
| `revise-arch: <描述>` | 🔄 返回步驟二重新設計架構 |
| `question: <問題>` | ❓ Agent 回答問題，無需 git/jira 操作 |

結束 session（停止 polling）：
```bash
python scripts/cli.py session close --id a1b2c3d4
```

---

## 定時 Polling 設定

### 安裝 cron job

在 **host** 上執行（一次即可）：

```bash
POLL_CMD="0 */2 * * * docker exec -u hermes hermes-gateway python3 /opt/data/external-skills/jira-architect/scripts/poll.py --once >> /tmp/jira-architect-poll.log 2>&1"
(crontab -l 2>/dev/null | grep -v "jira-architect"; echo "$POLL_CMD") | crontab -
```

安裝後 cron 每 2 小時透過 `docker exec` 在 container 內執行 `poll.py`。效果：
- 掃描所有 active sessions 的 Jira tickets
- 將新的 `@hermes` 留言寫入 `~/.hermes/jira-architect/notifications.jsonl`
- 若設定了 Discord Webhook，主動推送通知

驗證安裝：
```bash
crontab -l | grep "jira-architect"
```

查看 log：
```bash
tail -f /tmp/jira-architect-poll.log
```

手動執行一次（測試用）：
```bash
docker exec -u hermes hermes-gateway python3 \
  /opt/data/external-skills/jira-architect/scripts/poll.py --once --verbose
```

### Discord Webhook（選配）

在設定時加入 webhook URL，有新 feedback 時會主動推送 Discord：

```bash
docker exec -u hermes hermes-gateway python3 \
  /opt/data/external-skills/jira-architect/scripts/cli.py config set \
  ... \
  --webhook "https://discord.com/api/webhooks/CHANNEL_ID/TOKEN"
```

建立 Webhook 步驟：Discord → 頻道右鍵 → **編輯頻道** → **整合** → **Webhooks** → **新增 Webhook** → 複製 URL

Discord 頻道會收到：
```
🤖 Hermes Jira Feedback — Session a1b2c3d4 (PROJ-42 auth system)
🕐 發現 2 條新的 @hermes 回饋：

• [PROJ-43] @hermes fix: login returns 500 on invalid email
• [PROJ-44] @hermes question: 為什麼選擇 JWT 而不是 session-based auth？

請在 Hermes 中輸入「check Jira feedback」查看詳情並處理。
```

---

## @hermes 回饋協議

在 Jira ticket 的**留言欄**輸入以下格式，Hermes 會在下一個 polling 週期（最多 2 小時）偵測並處理：

```
@hermes <指令>
@hermes <指令>: <說明>
```

`@hermes` 必須在該行最前面（可有空白縮排，不可有其他文字在前）。

### 指令一覽

| 指令 | 範例 | 說明 |
|------|------|------|
| `approve-arch` | `@hermes approve-arch` | ✅ 確認架構設計，請開始實作 |
| `revise-arch` | `@hermes revise-arch: 加入 Redis caching layer` | 🔄 要求修改架構 |
| `approve-impl` | `@hermes approve-impl` | ✅ 確認程式實作，可以 merge |
| `fix` | `@hermes fix: 密碼錯誤應回傳 401 而非 500` | 🔧 請求程式碼修正 |
| `question` | `@hermes question: 為何選 PostgreSQL 而非 MongoDB？` | ❓ 詢問設計/實作問題 |

### 一則留言多個指令

```
測試後發現以下問題：

@hermes fix: POST /api/login 在 email 格式錯誤時應回傳 422
@hermes fix: refresh token 的 cookie 缺少 SameSite=Strict
@hermes question: JWT secret 有從環境變數讀取嗎？
```

Hermes 會依序處理所有指令。

### 重要說明

- Hermes **自己發布的留言**（架構設計、進度更新）包含隱藏的 `<!-- hermes-marker: ... -->`，掃描時會自動排除，不會誤觸發回饋循環
- 一則留言可包含任意數量的 `@hermes` 指令
- 指令名稱大小寫不分（`Fix` 等同於 `fix`）

---

## CLI 指令參考

### `config`

```bash
# 儲存設定（第一次使用必執行）
python scripts/cli.py config set \
  --url "https://yourcompany.atlassian.net" \
  --email "user@company.com" \
  --token "YOUR_API_TOKEN" \
  --project "PROJ" \
  [--git-repo "/path/to/repo"] \
  [--git-remote "origin"] \
  [--branch-prefix "feature/hermes-"] \
  [--webhook "https://discord.com/api/webhooks/..."]

# 顯示目前設定（token 遮罩）
python scripts/cli.py config show

# 測試 Jira 連線
python scripts/cli.py config test
```

設定儲存於 `~/.hermes/jira-architect.json`（chmod 600）。

### `fetch`

```bash
python scripts/cli.py fetch --epic PROJ-42 --output /tmp/ja-tickets.json
python scripts/cli.py fetch --tickets PROJ-42,PROJ-43 --output /tmp/ja-tickets.json
python scripts/cli.py fetch --jql "sprint in openSprints() AND project=PROJ" --output /tmp/ja-tickets.json
```

遞迴抓取 Epic → Story → Sub-task，輸出為 JSON（`IssueTree` 格式）。

### `post-design`

```bash
python scripts/cli.py post-design \
  --tickets /tmp/ja-tickets.json \
  --design-file /tmp/ja-design.md
```

將架構設計 Markdown 發布到 root-level tickets 作為 Jira 留言，附上回饋指引。

### `check-feedback`

```bash
python scripts/cli.py check-feedback \
  --tickets /tmp/ja-tickets.json \
  [--since "2024-01-15T10:00:00Z"]
```

即時掃描所有 tickets 的 Jira 留言，回傳包含 `@hermes` 指令的 JSON 列表。

### `git-commit`

```bash
python scripts/cli.py git-commit \
  --branch "feature/hermes-PROJ-42-auth" \
  --message "feat(PROJ-42): implement auth" \
  [--repo "/path/to/repo"] \
  [--remote "origin"] \
  [--push]
```

建立 branch（若不存在）、stage all、commit，選擇性 push。輸出 Git 資訊 JSON。

### `update-progress`

```bash
python scripts/cli.py update-progress \
  --tickets /tmp/ja-tickets.json \
  --repo-url "https://github.com/company/repo" \
  --commit "a1b2c3d4..." \
  --branch "feature/hermes-PROJ-42-auth" \
  --summary "一段說明這次 commit 做了什麼的文字"
  [--commit-url "https://github.com/company/repo/commit/a1b2c3d4"]
```

在所有 tickets（Epic + Story + Sub-task）貼上標準化進度留言。

### `session`

```bash
# 建立 polling session（post-design 後執行）
python scripts/cli.py session start \
  --tickets /tmp/ja-tickets.json \
  --label "PROJ-42 auth system" \
  [--phase awaiting_arch]

# 列出所有 sessions
python scripts/cli.py session list

# 更新 workflow phase
python scripts/cli.py session update-phase --id a1b2c3d4 --phase awaiting_impl
# phases: awaiting_arch | awaiting_impl | done

# 關閉 session（停止 polling）
python scripts/cli.py session close --id a1b2c3d4
python scripts/cli.py session close --id a1b2c3d4 --delete  # 完全刪除
```

### `notifications`

```bash
# 讀取所有累積的 feedback 通知
python scripts/cli.py notifications

# 指定 session
python scripts/cli.py notifications --session a1b2c3d4

# 限制返回數量
python scripts/cli.py notifications --session a1b2c3d4 --last 5
```

---

## 檔案結構

```
jira-architect/
├── SKILL.md                        — Hermes agent 工作流程指令（給 AI 讀的）
├── README.md                       — 完整說明文件（本檔）
├── requirements.txt                — Python 依賴（pydantic, requests）
├── install-cron.sh                 — 一鍵安裝 cron job
│
├── scripts/
│   ├── cli.py                      — 獨立 CLI 入口（零 discord/hermes 依賴）
│   ├── poll.py                     — cron 定時 polling 腳本（每 2h）
│   └── jira_architect/
│       ├── config.py               — 設定讀寫（~/.hermes/jira-architect.json）
│       ├── jira_client.py          — Jira REST API v3（fetch/comment/ADF）
│       ├── git_client.py           — Git 操作 wrapper
│       ├── models.py               — Pydantic 資料模型
│       ├── feedback.py             — @hermes 指令解析器
│       ├── progress.py             — 留言格式化器
│       └── session.py              — Session 狀態管理
│
├── tests/
│   ├── test_feedback.py            — feedback 解析測試（12 個）
│   ├── test_progress.py            — 留言格式化測試（12 個）
│   └── test_session.py             — session 管理測試（9 個）
│
├── references/
│   └── FEEDBACK_PROTOCOL.md        — @hermes 協議說明（可分享給使用者）
│
└── examples/
    └── sample_tickets.json         — 範例 ticket tree JSON
```

### 執行時期狀態（`~/.hermes/jira-architect/`）

```
~/.hermes/jira-architect/
├── sessions/
│   └── a1b2c3d4.json               — 每個 active session 的狀態
├── notifications.jsonl             — 累積的 @hermes feedback 通知（JSONL 格式）
└── poll.log                        — cron 執行 log
```
