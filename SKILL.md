---
name: jira-architect
description: "根據 Jira tickets 進行架構設計並發布到 Jira，使用者確認後自動實作程式碼並推上 Git，在所有相關 tickets 記錄進度（含 repo URL、commit、branch、摘要），並透過 Jira 留言的 @hermes 指令接收回饋，支援架構修訂與程式修正循環。"
version: 1.0.0
author: Alex Wong
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jira, git, architecture, coding, automation, devops, agile]
---

# Jira Architect & Auto-Coder (jira-architect)

讀取 Jira tickets → 生成架構設計 → 發布到 Jira 等待確認 → 實作程式碼 → 推上 Git → 更新所有 tickets 的進度留言（含 Git 資訊）→ 透過 `@hermes` 指令接收 Jira 回饋並循環修正。

---

## 何時使用

以下任何訊息都應觸發本技能：

- 「幫我根據 Jira tickets 做架構設計」
- 「根據 PROJ-42 進行系統設計然後開始實作」
- 「讀取這個 Epic 的所有 tickets 然後幫我規劃設計」
- 「Jira 上有 @hermes 的 feedback，幫我處理」
- 「check Jira 有沒有新的 feedback」
- 「根據 Jira 的 feedback 修改程式碼」

---

## 完整工作流程

### 步驟零：確認設定

執行：
```bash
python scripts/cli.py config show
```

若輸出 `No config found`，詢問使用者提供：
- Jira URL（例如 `https://yourcompany.atlassian.net`）
- Jira 帳號 Email 和 API Token（在 https://id.atlassian.com/manage-profile/security/api-tokens 建立）
- 預設 Project Key
- （選用）本地 Git repo 路徑 — 若不提供，未連結 repo 的 ticket 會由 `ensure-repo` 自動建立
- Git remote 名稱（預設 `origin`）
- Branch 前綴（預設 `feature/hermes-`）
- **GitHub Personal Access Token（`repo` scope，必填）** — 在 https://github.com/settings/tokens 建立；`ensure-repo` 自動建立/連結 repo 及後續 `git-commit --push` 驗證都需要

執行：
```bash
python scripts/cli.py config set \
  --url "https://yourcompany.atlassian.net" \
  --email "user@company.com" \
  --token "YOUR_API_TOKEN" \
  --project "PROJ" \
  --github-token "YOUR_GITHUB_PAT" \
  --git-repo "/path/to/local/repo" \
  --git-remote "origin" \
  --branch-prefix "feature/hermes-"
```

若使用者沒有現成的 Git repo（多數情況），可省略 `--git-repo`；`ensure-repo`（步驟五）會自動幫每個 Epic/ticket 建立新 repo 並連結。

測試連線：
```bash
python scripts/cli.py config test
```

若失敗，請使用者檢查 URL / Email / Token 並重新設定。

---

### 步驟一：Fetch Jira Tickets

根據使用者提供的 Epic key、ticket keys 或 JQL：

```bash
# 抓取一個 Epic 及其所有子 ticket（Story、Sub-task）
python scripts/cli.py fetch --epic PROJ-42 --output /tmp/ja-tickets.json

# 抓取指定的 tickets（逗號分隔）
python scripts/cli.py fetch --tickets PROJ-42,PROJ-43,PROJ-44 --output /tmp/ja-tickets.json

# 用 JQL 查詢（例如目前 sprint 中的所有 tickets）
python scripts/cli.py fetch --jql "sprint in openSprints() AND project=PROJ" --output /tmp/ja-tickets.json
```

CLI 輸出每個 issue 的 key、type 和 summary。**你必須讀取 /tmp/ja-tickets.json 理解所有 tickets 的需求。**

---

### 步驟二：生成架構設計

根據你對 tickets 的理解，**用你自己的推理能力**生成一份架構設計文件（Markdown 格式）。

架構設計文件應包含以下章節：

1. **系統概觀** — 一段話說明系統的目標與邊界
2. **技術選型** — 語言、框架、資料庫、外部服務及選擇理由
3. **系統架構** — Mermaid 或 ASCII 架構圖，說明各元件關係
4. **模組拆解** — 每個模組的職責、對外介面
5. **資料模型** — 主要 entities、schema 與關聯
6. **API 設計** — 主要 endpoint 或 interface 定義（含 HTTP method、path、request/response）
7. **非功能性需求** — 安全性、效能、擴展性、監控
8. **實作計畫** — 分階段的具體步驟

**將設計儲存到暫存檔：**
```python
# 用 python -c 或直接寫檔
with open('/tmp/ja-design.md', 'w', encoding='utf-8') as f:
    f.write("""<你生成的架構設計 Markdown>""")
```

---

### 步驟三：發布架構設計到 Jira

```bash
python scripts/cli.py post-design \
  --tickets /tmp/ja-tickets.json \
  --design-file /tmp/ja-design.md
```

CLI 會將設計發布到所有 root-level tickets（通常是 Epic）底下，並附上 `@hermes` 回饋指引。
輸出 JSON 包含 `posted_at` 時間戳，**記錄此時間**供後續 feedback 追蹤使用。

**啟動 polling session（讓 cron 定期掃描此批 tickets）：**

```bash
python scripts/cli.py session start \
  --tickets /tmp/ja-tickets.json \
  --label "PROJ-42 auth system" \
  --phase awaiting_arch
```

CLI 輸出 `session_id`（例如 `a1b2c3d4`）。**記錄此值**，查詢通知時使用。

若 cron 尚未安裝，提醒使用者執行一次（僅需安裝一次）：
```bash
bash install-cron.sh
```
cron 安裝後每 2 小時自動執行 `poll.py`，Jira 有新的 `@hermes` 留言時會：
1. 寫入 `~/.hermes/jira-architect/notifications.jsonl`
2. 若有設定 Discord Webhook，主動推送通知到 Discord 頻道

告知使用者：
> 「架構設計已發布到 Jira `{ticket_key}`，已啟動自動 polling（每 2 小時）。
> 請在 Jira 上回覆：
> - `@hermes approve-arch` — 確認設計，開始實作
> - `@hermes revise-arch: <描述>` — 要求修改架構」

---

### 步驟四：等待架構確認

有兩種確認方式：

**方式 A：cron 自動 polling + 通知檔（主要路徑）**

cron 每 2 小時執行 `poll.py`，將新 feedback 寫入通知檔。
使用者詢問「check Jira feedback」或 Discord 收到 Hermes 通知時，執行：

```bash
python scripts/cli.py notifications --session a1b2c3d4
```

解析輸出 JSON 的 `entries[].feedback[]` 陣列，根據 `directive` 決定下一步：

| directive | 行動 |
|-----------|------|
| `approve-arch` | 更新 session phase 為 awaiting_impl，繼續步驟五 ✅ |
| `revise-arch` | 讀取 `content`，返回步驟二修訂後重新 post-design 🔄 |
| `question` | 在 chat 回答問題，再詢問是否繼續 ❓ |

更新 session phase：
```bash
python scripts/cli.py session update-phase --id a1b2c3d4 --phase awaiting_impl
```

**方式 B：即時掃描（手動 or 使用者在 chat 中要求立即 check）**

```bash
python scripts/cli.py check-feedback \
  --tickets /tmp/ja-tickets.json \
  --since "2024-01-15T10:00:00Z"
```

`check-feedback` 直接呼叫 Jira API，適合需要即時結果的場合。

**方式 B：使用者在 chat 中直接確認**

若使用者在對話中說「設計沒問題」、「可以開始實作」等，直接進入步驟五，無需等待 Jira feedback。

---

### 步驟五：實作程式碼

**先確認 root ticket（通常是 Epic）是否已連結 GitHub repo：**

```bash
python scripts/cli.py ensure-repo --tickets /tmp/ja-tickets.json
```

CLI 行為：
1. 檢查 root ticket 上是否已有 Hermes 建立的 repo 連結（Jira remote link）。
2. **已連結** → clone 該 repo 到本地 workspace（若尚未 clone 過），直接使用。
3. **未連結** → 自動在 GitHub 建立一個新 repo（預設 private，名稱由 ticket key + summary 產生），clone 到本地，並把 repo URL 以 remote link 的形式連結回該 ticket。

輸出 JSON 範例：
```json
{
  "repos": [
    {"ticket": "PROJ-42", "repo_url": "https://github.com/alex85279/proj-42-user-auth", "local_path": "/home/hermes/.hermes/jira-architect/repos/proj-42-user-auth", "created": true}
  ]
}
```

**記錄 `local_path`**（每個 root ticket 對應一個 repo）供本步驟後續使用；`created: true` 時告知使用者已自動建立並連結新 repo。若 config 中沒有設定 `--git-repo`，一律以此步驟取得的 `local_path` 作為實作目標。

**決定 branch 名稱：**

格式：`{branch_prefix}{epic-key}-{short-slug}`
例如：`feature/hermes-PROJ-42-user-auth`

**你直接在 repo 目錄中建立/修改程式碼文件**，根據架構設計的「實作計畫」逐步完成。

實作完成後，執行（`--repo` 用步驟五開頭 `ensure-repo` 回傳的 `local_path`）：
```bash
python scripts/cli.py git-commit \
  --repo "{local_path}" \
  --branch "feature/hermes-PROJ-42-user-auth" \
  --message "feat(PROJ-42): implement user authentication system

- JWT token management
- Email/password login API endpoint
- Input validation middleware
- Unit tests for auth handlers" \
  --push
```

`--push` 會自動使用 config 中的 GitHub token 驗證（token 只透過單次指令的 `-c http.extraheader` 傳遞，不會寫入 `.git/config`）。

CLI 輸出 JSON 格式的 Git 資訊，包含 `commit_hash`、`commit_short`、`branch`、`repo_url`、`commit_url`。
**記錄這些值**供步驟六使用。

---

### 步驟六：更新所有 Jira Tickets 進度

使用步驟五取得的 Git 資訊，在**所有相關 tickets**（Epic + Story + Sub-task）貼上進度留言。

**每個 ticket 必須有自己專屬的更新訊息**，說明該 ticket 具體完成了什麼。使用 `--summaries` 傳入 JSON 物件：

```bash
python scripts/cli.py update-progress \
  --tickets /tmp/ja-tickets.json \
  --repo-url "https://github.com/company/repo" \
  --commit "a1b2c3d4e5f6789abcdef..." \
  --branch "feature/hermes-PROJ-42-user-auth" \
  --summaries '{
    "PROJ-42": "完成 Epic 整體進度：使用者認證系統主幹架構實作完成，子任務全部進入 Done。",
    "PROJ-43": "實作 JWT token 管理模組。支援 access token（30 分鐘）與 refresh token（7 天），附帶 token 輪換機制。",
    "PROJ-44": "完成登入 / 登出 API（POST /api/auth/login、POST /api/auth/logout），含完整 input validation middleware。所有單元測試通過（15/15）。"
  }'
```

- `--summaries` 接受 JSON 字串或檔案路徑（`@/tmp/summaries.json`）
- 若某個 ticket key 未出現在 `--summaries` 中，會 fallback 到 `--summary`（全域訊息）
- 若兩者都未提供，該 ticket 會被跳過（輸出會顯示 `⏭ Skipped`）

**規則**：每個 ticket 的訊息只描述**該 ticket 自身**的工作（不要把 Epic 的訊息複製給 sub-task）。

更新 session phase 為 `awaiting_impl`（讓 cron 繼續 polling 等待 code review 回饋）：
```bash
python scripts/cli.py session update-phase --id a1b2c3d4 --phase awaiting_impl
```

---

### 步驟七：回饋循環

**cron 每 2 小時自動執行**，有新 feedback 時寫入通知檔，並推送 Discord 通知。

使用者詢問或 Discord 收到通知時，查詢通知：

```bash
python scripts/cli.py notifications --session a1b2c3d4
```

根據 `entries[].feedback[]` 中的 `directive` 決定行動：

| directive | 行動 |
|-----------|------|
| `approve-impl` | ✅ 告知使用者實作已確認！執行 `session close --id a1b2c3d4` 結束 polling |
| `fix` | 🔧 讀取 `content`，修改程式碼，重新執行步驟五、六 |
| `revise-arch` | 🔄 讀取 `content`，返回步驟二重新設計架構，再重新 post-design |
| `question` | ❓ 在 chat 回答問題，不需要任何 git/jira 操作 |

實作確認後，結束 polling session：
```bash
python scripts/cli.py session close --id a1b2c3d4
```

若通知檔無新項目，告知使用者：「目前 Jira 上尚無新的 `@hermes` 回饋，下次 polling 在 2 小時內。」

---

## @hermes 回饋協議

> 這是在 Jira 留言中與 Hermes 溝通的標準格式。需要時可向使用者說明此協議。

使用者在任何相關 ticket 的**留言欄**輸入以下格式，即可觸發 Hermes 採取對應行動：

```
@hermes <指令>: <說明（若有）>
```

### 支援的指令

| 指令 | 範例 | 說明 |
|------|------|------|
| `approve-arch` | `@hermes approve-arch` | ✅ 確認架構設計，請開始實作 |
| `revise-arch` | `@hermes revise-arch: 請在 API 層加上 rate limiting，並改用 Redis 做 session 儲存` | 🔄 要求修改架構設計 |
| `approve-impl` | `@hermes approve-impl` | ✅ 確認程式實作沒問題，可以 merge |
| `fix` | `@hermes fix: /api/auth/login 沒有正確處理 email 格式錯誤，應回傳 400 而非 500` | 🔧 回報程式碼問題或請求修正 |
| `question` | `@hermes question: 為什麼選擇 JWT 而不是 session-based auth？` | ❓ 詢問設計或實作相關問題 |

### 重要規則

1. `@hermes` 必須在該行的**最前面**（可有空白縮排，但不可有其他文字）
2. 指令名稱不分大小寫（`Fix` 等同於 `fix`）
3. 一則留言可包含**多條** `@hermes` 指令（每條獨立一行）
4. 同一則留言若含有多個指令，Hermes 會依序處理

### 使用範例

```
我測試了登入功能，發現以下問題：

@hermes fix: 密碼錯誤時的錯誤訊息洩漏了「帳號不存在」vs「密碼錯誤」的資訊，應統一回傳「帳號或密碼錯誤」
@hermes fix: refresh token 的 httpOnly cookie 沒有設置 SameSite=Strict
@hermes question: JWT secret 是 hardcoded 還是從環境變數讀取？
```

Hermes 會：
1. 修正兩個安全性問題（fix）
2. 回答 JWT secret 的問題（question）
3. 重新 commit 並更新所有 tickets 的進度

---

## 錯誤處理

| 錯誤 | 處理方式 |
|------|---------|
| Jira 401 Unauthorized | Token 或 Email 錯誤 → 請使用者重新 `config set` |
| Jira 404 Issue not found | Ticket key 錯誤 → 請使用者確認 key |
| `ensure-repo` 報錯缺少 GitHub token | 請使用者到 https://github.com/settings/tokens 建立 PAT（`repo` scope），並執行 `config set --github-token ...` |
| GitHub 建立 repo 失敗（401/403） | GitHub token 無效或缺少 `repo` scope → 請使用者重新產生 token 並更新 config |
| Git push 失敗（non-fast-forward） | 需先 `git pull --rebase`，告知使用者手動解決後再試 |
| Git repo 路徑未設定 | 執行 `ensure-repo` 自動取得/建立，或用 `config set --git-repo` 指定既有路徑 |
| Nothing to commit | 實作後無文件變更 → 請確認文件是否已正確寫入 repo 目錄 |
| 沒有新 feedback | 告知使用者目前無 `@hermes` 回饋，提醒使用協議留言 |

---

## 檔案結構

```
scripts/
├── cli.py                          — 獨立執行入口（零 discord/hermes 依賴）
├── poll.py                         — cron 定時 polling 腳本（每 2h 執行）
└── jira_architect/
    ├── config.py                   — 設定讀寫（~/.hermes/jira-architect.json）
    ├── jira_client.py              — Jira REST API v3 client（fetch、comment、ADF、remote link）
    ├── github_client.py            — GitHub REST API client（建立 repo、查詢）
    ├── git_client.py               — Git 操作 wrapper（clone、branch、commit、push，token 驗證）
    ├── models.py                   — Pydantic 資料模型
    ├── feedback.py                 — @hermes 指令解析器
    ├── progress.py                 — 進度/設計留言格式化器
    └── session.py                  — Session 狀態管理（~/.hermes/jira-architect/sessions/）

install-cron.sh                     — 一鍵安裝 cron job（僅需執行一次）

references/
└── FEEDBACK_PROTOCOL.md            — @hermes 協議完整說明（供分享給使用者）

examples/
└── sample_tickets.json             — 範例 ticket tree JSON
```
