# AI_SESSION_CONTEXT.md — TransitFlow

> **專案名稱：** TransitFlow — AI 智慧鐵路助理資料庫專案
> **最後更新：** 2026-05-23
> **維護者：** 呂沛珍（組長）

---

## 1. How to Use This File

> **每次請 AI 協助寫程式前，請將本文件完整貼入對話開頭。**

本文件記錄了 TransitFlow 專案所有已達成共識的 schema、命名規則、function signatures 與 coding conventions。

**目的：**
- 確保 AI 產生的程式碼符合團隊已決定的架構
- 避免 AI 憑空發明不存在的 table、column 或 function
- 統一全組程式碼風格

**使用規則：**
- 若 AI 產生了不符合本文件的程式碼，**必須修正後才可採用**
- 若 schema 或架構決策有變更，**必須先更新本文件**再使用 AI
- AI 只能提供建議與選項，**最終決策由團隊決定**

---

## 2. Project Overview

TransitFlow 是一個 Python-based AI chat assistant，透過 LLM Agent 查詢三種資料庫來回答使用者問題。

### 資料庫架構

| 資料庫 | 用途 | 涵蓋範圍 |
| --- | --- | --- |
| PostgreSQL | 關聯式業務資料 | Users、Stations、Schedules、Bookings、Payments、Feedback |
| PostgreSQL + pgvector | 政策文件語意搜尋 (RAG) | Refund Policy、Ticket Rules、Travel Policies 等政策文件 Embedding |
| Neo4j | 圖形路網資料庫 | Station nodes + Route / Interchange relationships |

### 系統運作方式

1. 使用者透過 Gradio UI 輸入自然語言問題
2. LLM Agent 判斷應該呼叫哪個 Tool
3. Tool 查詢對應的資料庫
4. Agent 將查詢結果組織成自然語言回覆使用者

---

## 3. Tech Stack

| 類別　　　　　　　| 技術　　　　　　　　　　　　　　|
| -------------------| ---------------------------------|
| 程式語言　　　　　| Python　　　　　　　　　　　　　|
| 關聯式資料庫　　　| PostgreSQL　　　　　　　　　　　|
| PostgreSQL Driver | psycopg2 + RealDictCursor　　　 |
| 向量搜尋　　　　　| pgvector (PostgreSQL extension) |
| 圖形資料庫　　　　| Neo4j　　　　　　　　　　　　　 |
| 前端 UI　　　　　 | Gradio　　　　　　　　　　　　　|
| AI 框架　　　　　 | LLM Agent (Tool-calling)　　　　|
| LLM Provider　　　| Ollama / Gemini　　　　　　　　 |

### LLM Provider / Vector Dimension 規則

1. **全組必須統一 LLM provider**，不可混用
2. 若使用 **Ollama**，`policy_documents.embedding` 應為 `vector(768)`
3. 若使用 **Gemini**，`policy_documents.embedding` 應為 `vector(3072)`
4. **不可一人用 Ollama seed vectors、另一人用 Gemini 查詢**，維度不同會導致查詢失敗
5. 若切換 provider，**必須重建資料庫並重新執行 `seed_vectors.py`**

---

## 4. Coding Conventions

### SQL 規範

1. Table name 與 column name 一律使用 **snake_case**
2. SQL 查詢**必須使用參數化查詢**（`%s` placeholder），禁止字串拼接
3. 範例：
   ```python
   cursor.execute("SELECT * FROM nr_bookings WHERE booking_id = %s", (booking_id,))
   ```

### Python 規範

1. Function name 與 variable name 一律使用 **snake_case**
2. 不可任意修改既有 function signature
3. PostgreSQL 查詢使用 `_connect()` helper 建立連線
4. PostgreSQL 查詢回傳型別：
   - 多筆結果：`list[dict]`
   - 單筆結果：`Optional[dict]`
   - 查不到資料時回傳 `[]` 或 `None`，**不要 raise exception**
5. Neo4j 查詢使用 `_driver()` helper 與 `session.run()`
6. Neo4j 查詢回傳型別：
   - `dict` 或 `list[dict]`，依照 docstring
7. Agent tool 回傳資料必須適合 LLM 使用，**不要回傳無法序列化的物件**

---

## 5. Agreed PostgreSQL Schema

> ⚠️ **以下 schema 為團隊已認可的設計，AI 產生的程式碼必須嚴格遵守。**

### 使用者相關

#### `registered_users` — 使用者基本資料表

- **來源：** `registered_users.json`
- **用途：** 儲存使用者個人基本資料
- **Key Constraints：**
  - `user_id` — **PRIMARY KEY**
  - `email` — **UNIQUE**
- **重要欄位：** user_id、email、first_name、last_name、date_of_birth (DATE)、phone_number
- **注意：**
  - 儲存 `date_of_birth` 為 DATE 型別，保留完整生日
  - `year_of_birth` 僅作為 `register_user()` 的輸入參數，內部轉換為 `MAKE_DATE(year_of_birth, 1, 1)`
  - `email` 必須設為 UNIQUE

#### `user_credentials` — 使用者認證資料表

- **來源：** `registered_users.json`
- **用途：** 儲存登入認證資訊，與 `registered_users` 拆開
- **Key Constraints：**
  - `user_id` — **PRIMARY KEY** 且 **FK → `registered_users(user_id)`**
- **重要欄位：** user_id、password_hash、secret_question、secret_answer
- **注意：**
  - 儲存 `password_hash`，**絕對不存 plaintext password**
  - **不重複儲存 `email`**，`email` 只存在 `registered_users`
  - `login_user(email, password)` 流程：
    1. 先用 `registered_users.email` 找到 `user_id`
    2. 再用 `user_id` 去 `user_credentials` 查 `password_hash`
    3. 驗證密碼後回傳 user profile
  - `query_user_profile()` **不應回傳 `password_hash` 或 `secret_answer`**

### 車站相關

#### `metro_stations` — 捷運站基本資料

- **來源：** `metro_stations.json`
- **用途：** 儲存捷運站靜態資料
- **Key Constraints：**
  - `station_id` — **PRIMARY KEY**
- **重要欄位：** station_id、name、zone
- **注意：** 不儲存 `adjacent_stations`，路網關係交給 Neo4j

#### `metro_station_lines` — 捷運站所屬路線

- **來源：** `metro_stations.json`
- **用途：** 一個捷運站可能屬於多條線，因此拆表
- **Key Constraints：**
  - **PRIMARY KEY (`station_id`, `line_name`)**
  - `station_id` — FK → `metro_stations(station_id)`
- **重要欄位：** station_id、line_name

#### `national_rail_stations` — 國鐵站基本資料

- **來源：** `national_rail_stations.json`
- **用途：** 儲存國鐵站靜態資料
- **Key Constraints：**
  - `station_id` — **PRIMARY KEY**
- **重要欄位：** station_id、name、zone

#### `nr_station_lines` — 國鐵站所屬路線

- **來源：** `national_rail_stations.json`
- **用途：** 一個國鐵站可能屬於多條線，因此拆表
- **Key Constraints：**
  - **PRIMARY KEY (`station_id`, `line_name`)**
  - `station_id` — FK → `national_rail_stations(station_id)`
- **重要欄位：** station_id、line_name

### 班次 / 時刻表相關

#### `metro_schedules` — 捷運班次主表

- **來源：** `metro_schedules.json`
- **用途：** 儲存捷運 schedule 基本資料
- **Key Constraints：**
  - `schedule_id` — **PRIMARY KEY**
- **重要欄位：** schedule_id、line、direction、operates_on
- **注意：** `operates_on` 使用 **`TEXT[]`** 型別，不要自行改成七個 boolean 欄位，除非團隊後續決定修改 schema

#### `metro_schedule_stops` — 捷運班次停靠站

- **來源：** `metro_schedules.json`
- **用途：** 記錄每個 schedule 的停靠站順序
- **Key Constraints：**
  - **PRIMARY KEY (`schedule_id`, `stop_order`)**
  - `schedule_id` — FK → `metro_schedules(schedule_id)`
  - `station_id` — FK → `metro_stations(station_id)`
- **重要欄位：** schedule_id、station_id、**stop_order**、arrival_time
- **注意：** 必須有 `stop_order`，用來判斷 origin 是否在 destination 之前

#### `nr_schedules` — 國鐵班次主表

- **來源：** `national_rail_schedules.json`
- **用途：** 儲存國鐵 schedule 基本資料
- **Key Constraints：**
  - `schedule_id` — **PRIMARY KEY**
- **重要欄位：** schedule_id、service_type、departure_time、operates_on
- **注意：** `operates_on` 使用 **`TEXT[]`** 型別，不要自行改成七個 boolean 欄位

#### `nr_schedule_stops` — 國鐵班次停靠站

- **來源：** `national_rail_schedules.json`
- **用途：** 記錄每個 schedule 經過的站點、順序、是否停靠
- **Key Constraints：**
  - **PRIMARY KEY (`schedule_id`, `stop_order`)**
  - `schedule_id` — FK → `nr_schedules(schedule_id)`
  - `station_id` — FK → `national_rail_stations(station_id)`
- **重要欄位：** schedule_id、station_id、**stop_order**、travel_time_from_origin_min、**is_stopping**
- **注意：**
  - 使用 `travel_time_from_origin_min`，不要寫成 `arrival_time`
  - Express 經過但不停靠的站設 `is_stopping = FALSE`
  - `is_stopping = FALSE` 且無時間資料時，`travel_time_from_origin_min` 可為 NULL

#### `nr_schedule_fare_classes` — 國鐵票價等級

- **來源：** `national_rail_schedules.json`
- **用途：** 儲存各 schedule 的票價資訊
- **Key Constraints：**
  - **PRIMARY KEY (`schedule_id`, `fare_class`)**
  - `schedule_id` — FK → `nr_schedules(schedule_id)`
- **重要欄位：** schedule_id、fare_class、base_fare_usd、per_stop_rate_usd

### 座位相關

#### `nr_seat_coaches` — 國鐵車廂資料

- **來源：** `national_rail_seat_layouts.json`
- **用途：** 儲存車廂資訊，與 schedule_id 綁定
- **Key Constraints：**
  - **PRIMARY KEY (`schedule_id`, `coach_number`)**
  - `schedule_id` — FK → `nr_schedules(schedule_id)`
- **重要欄位：** schedule_id、coach_number、fare_class

#### `nr_seats` — 國鐵座位資料

- **來源：** `national_rail_seat_layouts.json`
- **用途：** 儲存個別座位資料
- **Key Constraints：**
  - **PRIMARY KEY (`schedule_id`, `seat_id`)**
- **重要欄位：** schedule_id、seat_id、coach_number、seat_type、is_window、has_power_outlet
- **注意：** PK 使用 **(schedule_id, seat_id)**，因為 seat_id 可能在不同 schedule 中重複

### 訂票 / 旅程紀錄

#### `nr_bookings` — 國鐵訂票紀錄

- **來源：** `bookings.json`
- **用途：** 儲存國鐵訂票紀錄
- **Key Constraints：**
  - `booking_id` — **PRIMARY KEY**
  - `user_id` — FK → `registered_users(user_id)`
  - `schedule_id` — FK → `nr_schedules(schedule_id)`
- **重要欄位：** booking_id、user_id、schedule_id、departure_time、travel_date、amount_usd、status
- **注意：** 使用 `booking_id`，**不使用 `booking_ref`**

#### `metro_travel_history` — 捷運搭乘紀錄

- **來源：** `metro_travel_history.json`
- **用途：** 儲存捷運搭乘紀錄
- **Key Constraints：**
  - `trip_id` — **PRIMARY KEY**
  - `user_id` — FK → `registered_users(user_id)`
- **重要欄位：** trip_id、user_id、day_pass_ref、purchased_at、amount_usd
- **注意：** `purchased_at` 與 `amount_usd` **不應設為 NOT NULL**（部分紀錄可能無此資料）

### 付款 / 回饋

#### `payments` — 付款紀錄

- **來源：** `payments.json`
- **用途：** 儲存付款資訊
- **Key Constraints：**
  - `payment_id` — **PRIMARY KEY**
  - `nr_booking_id` — FK → `nr_bookings(booking_id)`，**NULLABLE**
  - `metro_trip_id` — FK → `metro_travel_history(trip_id)`，**NULLABLE**
  - **CHECK constraint：** `nr_booking_id` 與 `metro_trip_id` 必須**剛好一個非 NULL**
- **重要欄位：** payment_id、nr_booking_id、metro_trip_id、amount_usd、payment_method
- **CHECK 規則說明：**
  - 國鐵付款：`nr_booking_id IS NOT NULL` 且 `metro_trip_id IS NULL`
  - 捷運付款：`nr_booking_id IS NULL` 且 `metro_trip_id IS NOT NULL`
  - **不允許兩者都 NULL**
  - **不允許兩者都非 NULL**
  - SQL 範例：
    ```sql
    CHECK (
      (nr_booking_id IS NOT NULL AND metro_trip_id IS NULL) OR
      (nr_booking_id IS NULL AND metro_trip_id IS NOT NULL)
    )
    ```

#### `feedback` — 評價回饋

- **來源：** `feedback.json`
- **用途：** 儲存使用者評價與回饋
- **Key Constraints：**
  - `feedback_id` — **PRIMARY KEY**
  - `nr_booking_id` — FK → `nr_bookings(booking_id)`，**NULLABLE**
  - `metro_trip_id` — FK → `metro_travel_history(trip_id)`，**NULLABLE**
  - **CHECK constraint：** 與 `payments` 相同，`nr_booking_id` 與 `metro_trip_id` 必須**剛好一個非 NULL**
- **重要欄位：** feedback_id、nr_booking_id、metro_trip_id、rating、comment
- **CHECK 規則說明：**
  - 國鐵回饋：`nr_booking_id IS NOT NULL` 且 `metro_trip_id IS NULL`
  - 捷運回饋：`nr_booking_id IS NULL` 且 `metro_trip_id IS NOT NULL`
  - **不允許兩者都 NULL**
  - **不允許兩者都非 NULL**

### 命名規則摘要

| 概念 | 正確名稱 | 錯誤名稱 |
| --- | --- | --- |
| 國鐵訂票 ID | `booking_id` | ~~booking_ref~~ |
| 捷運旅程 ID | `trip_id` | ~~travel_id~~ |
| 付款關聯國鐵 | `nr_booking_id` | ~~booking_ref~~ |
| 付款關聯捷運 | `metro_trip_id` | ~~travel_id~~ |
| 座位 PK | `(schedule_id, seat_id)` | ~~seat_id alone~~ |
| 使用者生日 | `date_of_birth` (DATE) | ~~year_of_birth~~ |
| 密碼儲存 | `password_hash` | ~~password~~ |
| 營運日 | `operates_on` (TEXT[]) | ~~七個 boolean 欄位~~ |

### Key Constraints 摘要表

| Table | Primary Key | 備註 |
| --- | --- | --- |
| `registered_users` | `user_id` | `email` UNIQUE |
| `user_credentials` | `user_id` | FK → registered_users，不存 email |
| `metro_stations` | `station_id` | |
| `metro_station_lines` | `(station_id, line_name)` | |
| `national_rail_stations` | `station_id` | |
| `nr_station_lines` | `(station_id, line_name)` | |
| `metro_schedules` | `schedule_id` | |
| `metro_schedule_stops` | `(schedule_id, stop_order)` | |
| `nr_schedules` | `schedule_id` | |
| `nr_schedule_stops` | `(schedule_id, stop_order)` | |
| `nr_schedule_fare_classes` | `(schedule_id, fare_class)` | |
| `nr_seat_coaches` | `(schedule_id, coach_number)` | |
| `nr_seats` | `(schedule_id, seat_id)` | |
| `nr_bookings` | `booking_id` | |
| `metro_travel_history` | `trip_id` | |
| `payments` | `payment_id` | CHECK: 剛好一個 FK 非 NULL |
| `feedback` | `feedback_id` | CHECK: 剛好一個 FK 非 NULL |

---

## 6. Agreed Neo4j Graph Schema

### Node Labels

| Label | 說明 | 對應 PostgreSQL |
| --- | --- | --- |
| `MetroStation` | 捷運站節點 | `metro_stations` |
| `NationalRailStation` | 國鐵站節點 | `national_rail_stations` |

### Node Properties

| Property | 說明 |
| --- | --- |
| `station_id` | 與 PostgreSQL 完全一致（例如 MS01、NR01） |
| `name` | 站名 |
| `lines` | 所屬路線列表 |
| `is_interchange_*` | 是否為轉乘站（依類型標記） |

### Relationship Types

| Type | 說明 | 連接 |
| --- | --- | --- |
| `METRO_LINK` | 捷運站之間的直接連結 | MetroStation → MetroStation |
| `RAIL_LINK` | 國鐵站之間的直接連結 | NationalRailStation → NationalRailStation |
| `INTERCHANGE_TO` | 跨系統轉乘連結 | MetroStation ↔ NationalRailStation |

### Edge Properties

| Property | 說明 | 適用 |
| --- | --- | --- |
| `travel_time_min` | 行車或步行時間（統一 weight） | 所有 relationship |
| `line` | 所屬路線 | METRO_LINK、RAIL_LINK |
| `service_type` | 服務類型（Local / Express） | RAIL_LINK |
| `per_stop_rate_usd` | 每站費率 | RAIL_LINK |

### Graph Rules

1. `station_id` **必須與 PostgreSQL 完全一致**（例如 MS01、NR01）
2. `adjacent_stations` **不存 PostgreSQL**，路網關係只放 Neo4j
3. `INTERCHANGE_TO` 必須**雙向建立**：
   ```cypher
   (ms:MetroStation {station_id: "MS01"})-[:INTERCHANGE_TO]->(nr:NationalRailStation {station_id: "NR01"})
   (nr:NationalRailStation {station_id: "NR01"})-[:INTERCHANGE_TO]->(ms:MetroStation {station_id: "MS01"})
   ```
4. 所有 relationship 統一使用 `travel_time_min` 作為時間權重
5. `INTERCHANGE_TO` 的 `travel_time_min` 表示**轉乘步行時間**
6. 若要支援 cheapest route，可使用 edge 上的 `per_stop_rate_usd` 或 `cost_usd`
7. `base_fare_usd` **不放在每段 edge 重複加總**，應由 app 邏輯在最後加一次
8. Express rail service **只建立實際停靠站之間的 `RAIL_LINK`**，跳過的站不建邊

---

## 7. Query Stub Requirements

### `query_national_rail_availability`

**依賴的 Table：** `nr_schedules`、`nr_schedule_stops`、`nr_bookings`

**必要欄位：** `stop_order`、`is_stopping`、`travel_date`、`status`、`departure_time`

**業務規則：**
- 必須確認 `origin.stop_order < destination.stop_order`
- Origin 與 destination 都必須 `is_stopping = TRUE`
- `status = 'cancelled'` 的 booking 不計入已售座位

---

### `query_metro_schedules`

**依賴的 Table：** `metro_schedules`、`metro_schedule_stops`

**必要欄位：** `stop_order`、`operates_on`

**業務規則：**
- 必須確認 `origin.stop_order < destination.stop_order`

---

### `query_available_seats`

**依賴的 Table：** `nr_seat_coaches`、`nr_seats`、`nr_bookings`

**必要欄位：** `schedule_id`、`seat_id`、`travel_date`、`fare_class`、`status`

**業務規則：**
- `nr_seats` PK 使用 `(schedule_id, seat_id)`
- 若某 schedule 沒有 seat layout，**回傳 `[]`，不要 raise exception**

---

### `query_user_bookings`

**依賴的 Table：** `registered_users`、`nr_bookings`、`metro_travel_history`

**必要欄位：** `email`、`user_id`

**業務規則：**
- `registered_users.email` 必須 UNIQUE
- 透過 email 查找 user_id，再查詢相關 bookings / travel history

---

### `register_user` / `login_user`

**依賴的 Table：** `registered_users`、`user_credentials`

**必要欄位：** `email`、`password_hash`、`secret_question`、`secret_answer`、`date_of_birth`

**業務規則：**
- 不存 plaintext password
- `register_user(year_of_birth)` 內部轉換：`date_of_birth = MAKE_DATE(year_of_birth, 1, 1)`
- `login_user(email, password)` 流程：
  1. 用 `registered_users.email` 找到 `user_id`
  2. 用 `user_id` 去 `user_credentials` 查 `password_hash`
  3. 驗證密碼後回傳 user profile（不含 `password_hash` 與 `secret_answer`）

---

### `query_interchange_path`

**依賴的 Neo4j 元素：** `MetroStation`、`NationalRailStation`、`METRO_LINK`、`RAIL_LINK`、`INTERCHANGE_TO`

**必要 Property：** `travel_time_min`

**業務規則：**
- 使用 Dijkstra 或 shortest path 演算法
- Weight 統一使用 `travel_time_min`

---

## 8. Function Signatures

> ⚠️ **以下 function signatures 為團隊已固定的介面，AI 不可修改名稱、參數或回傳型態。**

### Relational Functions（`databases/relational/queries.py`）

```python
def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None
) -> list[dict]: ...

def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int
) -> Optional[dict]: ...

def query_metro_schedules(
    origin_id: str,
    destination_id: str
) -> list[dict]: ...

def query_metro_fare(
    schedule_id: str,
    stops_travelled: int
) -> Optional[dict]: ...

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str
) -> list[dict]: ...

def query_user_profile(
    user_email: str
) -> Optional[dict]: ...

def query_user_bookings(
    user_email: str
) -> dict: ...

def query_payment_info(
    booking_id: str
) -> Optional[dict]: ...

def execute_booking(
    user_id, schedule_id, origin_station_id, destination_station_id,
    travel_date, fare_class, seat_id, ticket_type="single"
) -> tuple[bool, dict | str]: ...

def execute_cancellation(
    booking_id: str,
    user_id: str
) -> tuple[bool, dict | str]: ...

def register_user(
    email, first_name, surname, year_of_birth,
    password, secret_question, secret_answer
) -> tuple[bool, str]: ...

def login_user(
    email: str,
    password: str
) -> Optional[dict]: ...

def get_user_secret_question(
    email: str
) -> Optional[str]: ...

def verify_secret_answer(
    email: str,
    answer: str
) -> bool: ...

def update_password(
    email: str,
    new_password: str
) -> bool: ...
```

### Graph Functions（`databases/graph/queries.py`）

```python
def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto"
) -> dict: ...

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard"
) -> dict: ...

def query_alternative_routes(
    origin_id, destination_id, avoid_station_id,
    network="auto", max_routes=3
) -> list[list[dict]]: ...

def query_interchange_path(
    origin_id: str,
    destination_id: str
) -> dict: ...

def query_delay_ripple(
    delayed_station_id: str,
    hops: int = 2
) -> list[dict]: ...

def query_station_connections(
    station_id: str
) -> list[dict]: ...
```

---

## 9. Function Signature Rules

1. **已定義的 function signature 不可任意修改**
2. 若 AI 建議新增 function，**必須先更新本文件**再實作
3. 若新增 tool，**必須確認 `agent.py` 是否有註冊**
4. 若 `agent.py` 未註冊某 function（例如 `query_payment_info`），**該 function 不應被假設為 Agent 可直接呼叫**
5. 所有 function 的回傳型別必須遵守 docstring 標註

---

## 10. Team Decisions Log

以下為團隊已達成共識的設計決策：

| # | 決策 | 說明 |
| --- | --- | --- |
| 1 | Schema-first 原則 | 先完成 schema.sql 並通過 review，再開始分工實作 |
| 2 | PostgreSQL + Neo4j 分工 | 結構化資料放 PostgreSQL，路網拓撲放 Neo4j |
| 3 | registered_users / user_credentials 拆表 | 認證資料與個人資料分離，提升安全性；email 只存 registered_users |
| 4 | schedule_stops 拆表 | 班次主表與停靠站分離，支援 stop_order 排序 |
| 5 | is_stopping 處理 express | Express 經過但不停靠的站標記 is_stopping = FALSE |
| 6 | nr_seats 複合 PK | 使用 (schedule_id, seat_id) 作為主鍵 |
| 7 | payments / feedback 排他性 FK | 雙 nullable FK + CHECK：剛好一個非 NULL |
| 8 | Neo4j 雙 Node Label | MetroStation 與 NationalRailStation 分開標記 |
| 9 | 三種 Relationship Type | METRO_LINK / RAIL_LINK / INTERCHANGE_TO |
| 10 | INTERCHANGE_TO 雙向建立 | 確保雙向轉乘查詢皆可運作 |
| 11 | travel_time_min 統一 weight | 所有 relationship 使用 travel_time_min 作為路徑權重 |
| 12 | operates_on 使用 TEXT[] | 不使用七個 boolean 欄位，除非團隊決議變更 |
| 13 | LLM provider 統一 | 全組統一 provider，切換時須重建向量資料庫 |

---

## 11. Prompts That Worked

> 此區塊記錄與 AI 互動時效果良好的 prompt，供團隊成員參考與複用。

<!-- 
格式範例：

### [日期] — [用途簡述]

```
你的 prompt 內容...
```

**效果：** 簡述 AI 回覆的品質與可用性。
-->

*（尚未新增，待團隊成員補充。）*

---

## 12. Notes for AI Assistants

> **如果你是正在閱讀此文件的 AI assistant，請遵守以下規則：**

1. **嚴格遵守上述 schema**。不要發明不存在的 table 或 column。
2. **使用正確的命名**。參照第 5 節的命名規則摘要表。
3. **SQL 必須使用參數化查詢**。禁止字串拼接。
4. **查不到資料時回傳空值**（`[]` 或 `None`），不要 raise exception。
5. **不要修改既有的 function signature**。參照第 8 節的固定 signatures。
6. **回傳資料必須可序列化**，適合 LLM Agent 使用。
7. **若不確定某 table 或 column 是否存在，請詢問使用者**，不要自行假設。
8. **若建議新增 function 或 table，請明確標示為「建議」**，由團隊決定是否採用。
9. **不可虛構資料**。若某欄位在 JSON mock data 中不存在，不得自行編造數值。
   - 例如 `is_stopping = FALSE` 的站若沒有 `travel_time_from_origin_min`，應設為 `NULL` 或詢問使用者
10. **不可自行產生不存在的 table、column 或 relationship property**。

---

> 本文件由組長呂沛珍負責維護。任何 schema 或架構決策變更，須同步更新本文件。
