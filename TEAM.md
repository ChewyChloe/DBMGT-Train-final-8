# TEAM.md — TransitFlow

> **專案名稱：** TransitFlow — AI 智慧鐵路助理資料庫專案
> **建立日期：** 2026-05-23
> **維護者：** 呂沛珍（組長）

---

## 1. Project Overview

TransitFlow 是一個結合三種資料庫技術與 LLM Agent 的智慧鐵路助理系統，涵蓋訂票、路線規劃與政策查詢等核心功能。

### 使用資料庫

| 資料庫 | 用途 | 涵蓋範圍 |
| --- | --- | --- |
| PostgreSQL | 關聯式業務資料 | Users、Stations、Schedules、Bookings、Payments、Feedback 等結構化資料 |
| PostgreSQL + pgvector | 政策文件 RAG / 語意搜尋 | Refund Policy、Ticket Rules、Travel Policies 等政策文件向量化檢索 |
| Neo4j | 圖形路網資料庫 | Metro / National Rail 車站節點與路線關係 |

---

## 2. Team Members and Responsibilities

| 成員 | 角色 | 主要戰略方向 | 核心負責模組 |
| --- | --- | --- | --- |
| 呂沛珍 | 組長 | 關聯式核心 + Agent 總整合 | PostgreSQL 業務邏輯 + LLM Agent 整合 |
| 陳宇緹 | 組員 | 圖形演算法引擎 | Neo4j 拓撲路網 + 路線搜尋演算法 |
| 楊依純 | 組員 | 知識庫向量化 + 展示情境設計 | pgvector 政策 RAG + Demo QA 測試 |

### 呂沛珍（組長）— PostgreSQL Relational Core、Integration Lead、Agent Coordination

**具體任務與實作內容：**

1. 設計 PostgreSQL 關聯式資料模型，包含 users、credentials、stations、lines、schedules、schedule stops、fare classes、seats、bookings、payments、feedback、policy_documents 等資料表。
2. 撰寫並維護 `databases/relational/schema.sql`，設計 PK / FK / unique constraints / indexes，並確保資料符合 referential integrity。
3. 實作與維護 `skeleton/seed_postgres.py`，支援 bulk seed，並使用 conflict handling 確保 seed script 可重複執行。
4. 實作 PostgreSQL 查詢功能，例如：
   - `login_user`
   - `query_user_profile`
   - `query_national_rail_availability`
   - `query_national_rail_fare`
   - `query_available_seats`
   - `query_metro_schedules`
   - `query_metro_fare`
   - `query_payment_info`
   - `query_user_bookings`
   - `execute_booking`
   - `execute_cancellation`
5. 實作使用者認證相關邏輯，包含密碼雜湊、登入驗證、使用者狀態檢查等。
6. 實作 National Rail booking transaction，確保 booking、seat assignment、payment creation 在同一個 database transaction 中完成。
7. 實作 cancellation / refund 相關資料庫邏輯，確保訂票狀態與付款狀態可以一致更新。
8. 協助 Agent tool integration，確認 PostgreSQL tools 可被 Agent 呼叫，並測試 payment、availability、booking 等 runtime cases。
9. 負責 final backend integration testing，整合 PostgreSQL、Neo4j、RAG / Vector 三個 backend 模組。
10. Review 組員 PR，包括 Neo4j graph PR 與 RAG seeder PR，協助測試 edge cases 並回報修正建議。
11. 整理 final testing evidence、known issues、setup steps，協助文件與交付前檢查。

**預期交付成果：**

1. PostgreSQL schema 可成功建立，且資料表具有完整 PK / FK / constraints。
2. `seed_postgres.py` 可成功 bulk seed 且可重複執行。
3. PostgreSQL 查詢功能可支援登入、查班次、查票價、查座位、訂票、付款、取消訂票等核心流程。
4. Booking / payment / cancellation 相關操作具備 transaction safety。
5. PostgreSQL、Neo4j、RAG backend 可在最新 main branch 上共同運作並完成 integration test。
6. Agent 可成功載入 PostgreSQL tools，並已完成部分 runtime 測試與 known issue 記錄。

### 陳宇緹 — 圖形演算法引擎

**具體任務與實作內容：**

1. 研讀測資，設計 Metro 與 National Rail 的圖形資料庫節點與關係
2. 撰寫 `seed.cypher` 與實作 `seed_neo4j.py`
3. 實作圖形查詢（Dijkstra 最短路徑、替代路線、跨系統轉乘、特定車站關閉的動態繞道邏輯）

**預期交付成果：**

1. Neo4j Browser 可視覺化雙鐵路網
2. 複雜的路線規劃工具可被 Agent 正確調用並返回最佳路徑

### 楊依純 — 知識庫向量化 + 展示情境設計

**具體任務與實作內容：**

1. 擴充並維護政策 JSON 檔案（退票規則、行李、遺失物、寵物政策等）
2. 實作 `seed_vectors.py` 進行 Embedding 並處理向量相似度查詢
3. 負責設計與測試 Demo 用的 Q&A 劇本，並協助將新的政策查詢註冊進 Agent
4. 輔助陳宇緹進行 Neo4j 相關工作

**預期交付成果：**

1. 政策文件可透過 pgvector 進行語意搜尋
2. 產出流暢的展示 Demo 問題集，確保 AI 回答政策時不會產生幻覺

---

## 3. File Ownership

每位成員對所負責檔案擁有主要修改權。修改他人負責的檔案前，須先知會該檔案負責人。

### 呂沛珍

| 檔案路徑 | 說明 |
| --- | --- |
| `databases/relational/schema.sql` | PostgreSQL 資料表定義 |
| `skeleton/seed_postgres.py` | PostgreSQL 資料匯入腳本 |
| `databases/relational/queries.py` | PostgreSQL 查詢函式 |
| `skeleton/agent.py` | LLM Agent 主程式與工具註冊 |
| `TEAM.md` | 團隊協作規範文件 |
| `AI_SESSION_CONTEXT.md` | AI 輔助開發上下文文件 |

### 陳宇緹

| 檔案路徑 | 說明 |
| --- | --- |
| `databases/graph/seed.cypher` | Neo4j 圖形資料定義與匯入 |
| `skeleton/seed_neo4j.py` | Neo4j 資料匯入腳本 |
| `databases/graph/queries.py` | Neo4j 圖形查詢函式 |

### 楊依純

| 檔案路徑 | 說明 |
| --- | --- |
| `train-mock-data/refund_policy.json` | 退票政策資料 |
| `train-mock-data/ticket_types.json` | 票種規則資料 |
| `train-mock-data/booking_rules.json` | 訂票規則資料 |
| `train-mock-data/travel_policies.json` | 旅行政策資料 |
| `skeleton/seed_vectors.py` | pgvector 向量匯入腳本 |
| Demo 測試題整理 | Demo 展示用 Q&A 問題集 |

---

## 4. Git Workflow

### Branch 策略

- `main` 分支**只放穩定版本**，不可直接 push
- 每位成員須建立個人 feature branch 進行開發
- 開始工作前**必須**先同步最新 main：

```bash
git checkout main
git pull origin main
git checkout -b feature/<name>/<feature>
```

### Branch 命名規範

| 成員 | Branch 命名範例 |
| --- | --- |
| 呂沛珍 | `feature/peizhen/relational-schema` |
| 陳宇緹 | `feature/yuti/neo4j-graph` |
| 楊依純 | `feature/yichun/vector-rag` |

### Commit 規範

- 每位成員**都必須有自己的 commit 紀錄**
- 禁止他人代為 commit
- Commit message 須清楚描述修改內容

---

## 5. Pull Request Rules

1. 完成功能後須開 **Pull Request (PR)** 請求合併至 `main`
2. PR 至少需要 **一位組員 review 並 approve** 後才可合併
3. PR 標題須清楚描述本次修改範圍
4. PR 描述中應列出：
   - 修改了哪些檔案
   - 新增或變更了哪些功能
   - 是否影響其他模組

---

## 6. Schema Change Rules

> ⚠️ `schema.sql` 是全組共用的核心檔案，任何變更都會影響所有成員的開發環境。

1. `schema.sql` 的任何變更**必須通知全組**
2. 變更前須開 PR 並經過 review
3. 變更合併後，**所有成員必須重建 / 重新 seed database**
4. 若新增或修改 table / column，須同步更新 `AI_SESSION_CONTEXT.md`
5. 禁止未經討論擅自修改已確定的 schema 結構

---

## 7. AI Collaboration Rules

本專案允許使用 AI 工具輔助開發，但須遵守以下規範：

1. **每次使用 AI 前，必須先貼上 `AI_SESSION_CONTEXT.md`**，確保 AI 了解當前專案架構
2. **不可直接接受 AI 產生的程式碼**，須逐行檢查後再採用
3. AI 產出的 table / column / function 名稱**必須符合已決定的 schema**
4. 若 AI 產生了**不存在的 table 或 column**，必須修正為正確名稱
5. 若 schema 或架構決策改變，**必須同步更新 `AI_SESSION_CONTEXT.md`**
6. AI 只能提供選項與建議，**最終決策由團隊共同決定**

---

## 8. Development Workflow

開發依照以下順序進行：

```
schema.sql 設計 → PR Review → 合併 → 分工實作 → 整合測試 → Demo
```

### 詳細步驟

1. **Phase 1 — Schema 設計**
   - 完成 `schema.sql` 設計
   - 開 PR 並通過全組 review
   - 合併至 `main`

2. **Phase 2 — 分工實作**
   - Schema 合併後，各成員開始各自模組的開發：
     - 呂沛珍：PostgreSQL seed / queries / Agent integration
     - 陳宇緹：Neo4j seed / graph queries
     - 楊依純：Policy JSON 擴充 / vector seed / Demo QA 設計

3. **Phase 3 — 整合測試**
   - 各模組完成後進行跨模組整合測試
   - 確認 Agent 可正確調用三種資料庫的查詢工具

4. **Phase 4 — Demo 測試**
   - 依照楊依純設計的 Q&A 劇本進行完整 Demo 測試
   - 修正幻覺、錯誤回應等問題
   - 確認展示流程順暢

---

## 9. Final Notes

- 遇到問題優先在群組討論，避免各做各的導致衝突
- 修改共用檔案前務必通知相關成員
- 定期同步進度，確保三個資料庫模組能順利整合
- 所有成員須熟悉本文件內容並遵守相關規範

---

> 本文件由組長呂沛珍負責維護，如有更新將通知全組。
