# @hermes 回饋協議說明

本文件說明如何在 Jira 留言中向 Hermes 提供回饋，觸發架構修訂或程式碼更新。

---

## 基本格式

在 Jira ticket 的**留言欄**輸入：

```
@hermes <指令>
```

或：

```
@hermes <指令>: <說明內容>
```

`@hermes` 必須在該行的最前面（可有前置空白）。

---

## 指令一覽

### `approve-arch` — 確認架構設計

```
@hermes approve-arch
```

告訴 Hermes 架構設計沒問題，可以開始撰寫程式碼。

---

### `revise-arch` — 要求修改架構

```
@hermes revise-arch: <描述需要調整的地方>
```

範例：
```
@hermes revise-arch: 請在 Service 層和 Database 層之間加入 Cache 層（Redis），
所有讀取操作先查 cache，miss 才讀 DB
```

```
@hermes revise-arch: API Gateway 改用 Kong 而不是自建，並加上 OAuth2 驗證
```

---

### `approve-impl` — 確認程式實作

```
@hermes approve-impl
```

確認這次 commit 的實作內容沒問題，可以進行 code review 或 merge。

---

### `fix` — 請求程式碼修正

```
@hermes fix: <描述問題或要求>
```

範例：
```
@hermes fix: POST /api/users 在 email 格式不合法時應回傳 422 而非 500
```

```
@hermes fix: JWT secret 不應 hardcode，改從 process.env.JWT_SECRET 讀取
```

```
@hermes fix: 資料庫連線沒有做 connection pooling，高並發時會 exhausted
```

---

### `question` — 詢問問題

```
@hermes question: <你的問題>
```

範例：
```
@hermes question: 為什麼選擇 PostgreSQL 而非 MongoDB？NoSQL 不更適合這個 use case 嗎？
```

Hermes 會在 chat 中回答，不會觸發任何程式碼或 Jira 變更。

---

## 一則留言包含多個指令

一則留言可以有多條 `@hermes` 指令，每條獨立一行：

```
功能測試後發現以下問題：

@hermes fix: 密碼重設 token 有效期應為 15 分鐘，目前設定是 24 小時
@hermes fix: 登入失敗訊息不應區分「帳號不存在」與「密碼錯誤」（資安問題）
@hermes question: refresh token rotation 有實作嗎？
```

Hermes 會依序處理所有指令。

---

## 在哪個 ticket 留言都可以

相關 Epic 下的任何 Story 或 Sub-task 都可以留 `@hermes` 指令，
Hermes 在掃描 feedback 時會掃描所有相關 tickets。

---

## Hermes 自己的留言不會干擾

Hermes 發布的留言（架構設計、進度更新）都包含一個隱藏的 HTML 標記 `<!-- hermes-marker: ... -->`，
掃描時會自動排除，不會被誤判為使用者回饋。
