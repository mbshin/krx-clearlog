# KRX Message Parser — Design

Architectural design for the KRX clearing-and-settlement (청산결제)
message parser. Companion documents:

- [`messages.md`](./messages.md) — field-level layouts for every TR code.
- [`codes.md`](./codes.md) — enumerated code sets referenced by fields.

## 1. Purpose

Parse KRX 청산결제 DATA messages (margin rates, required amounts,
over/under notifications, intraday additional margin) from **log files
that the user pastes or uploads**, persist raw payloads and parsed
records (as JSON bodies) to SQLite, and provide a Streamlit UI for
users to **look up parsed data** — search, filter, and inspect.

SQLite was chosen over a client/server database because the workload
is single-tenant, air-gapped, and dominated by bulk inserts + ad-hoc
lookups. The SQLAlchemy/Alembic layer keeps the option open to swap to
Postgres later with a DSN change if concurrency needs grow.

## 2. Scope

In scope (v1):

- All TR codes listed in `messages.md` (TCSMIH41301, TCSMIH42101,
  TCSMIH42201, TCSMIH42301, TCSMIH42401, TCSMIH43101, TCSMIH43201,
  TCSMIH43301, TCSMIH43401, TCSMIH43501, TCSMIH43601).
- Fixed-width text parsing from pasted log content or uploaded files.
- SQLite persistence of raw + parsed records (single file under `data/`).
- Streamlit GUI for lookup (search/filter/inspect).
- Offline-installable Python distribution for RHEL 8 deployment.

Out of scope (v1):

- Real-time TCP / multicast feed ingestion.
- Order routing or trading logic.
- Authentication / multi-tenant access control.

## 3. User Flow

```text
┌───────────────────────────┐
│ User pastes / uploads     │
│ log text in Streamlit UI  │
└───────────┬───────────────┘
            │
            ▼
┌───────────────────────────┐          ┌────────────────────┐
│ Parser splits records,    │          │ raw_messages       │
│ dispatches on TR code,    │ ──────▶ │ (BLOB payload)     │
│ produces typed JSON body  │          │ parsed_messages    │
└───────────┬───────────────┘          │ (JSON body)        │
            │                          │ (SQLite: krx.db)   │
            │                          └────────────────────┘
            ▼
┌───────────────────────────┐
│ Streamlit lookup pages:   │
│ browse / filter / inspect │
└───────────────────────────┘
```

## 4. High-Level Architecture

```text
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Log text    │ →  │    Parser    │ →  │   SQLite     │
│  (paste/file)│    │  (Python)    │    │ (data/krx.db)│
└──────────────┘    └──────────────┘    └──────────────┘
                            ↑                   ↑
                    ┌───────┴───────────────────┴──────┐
                    │        Streamlit UI              │
                    │  (paste / lookup / inspect)      │
                    └──────────────────────────────────┘
```

Components:

- **Parser core** (`krx_parser/`) — pure-Python, no UI / DB deps.
- **Schema registry** — `TRANSACTION_CODE` → field layout (loaded from
  YAML files at startup).
- **Persistence layer** (`krx_parser/db/`) — SQLAlchemy models +
  repository; Alembic for migrations.
- **Streamlit app** (`app/`) — thin UI that calls parser + repository.

## 5. Technology Stack

| Layer       | Choice                           |
| ----------- | -------------------------------- |
| Language    | Python 3.11+                     |
| UI          | Streamlit                        |
| Database    | SQLite 3 (bundled with Python)   |
| ORM         | SQLAlchemy 2.x + Alembic         |
| Config      | pydantic-settings                |
| Testing     | pytest                           |
| Lint/format | ruff                             |

## 6. Log Input Format

A log file is an ASCII/EUC-KR text stream containing one or more KRX
records concatenated back-to-back. Each record is fixed-length
(determined by its TR code; filler fields pad the tail). The parser
handles both:

- **Paste mode** — user pastes raw text into a textarea; the parser
  iteratively reads 22 bytes at each offset to extract
  `TRANSACTION_CODE`, looks up its expected record length, and slices
  that many bytes.
- **Upload mode** — same logic applied to file bytes.

Open question: the source log may include line terminators (`\n` or
`\r\n`) or framing prefixes. The parser should be tolerant — strip line
terminators before slicing, and log any leftover bytes.

## 7. Schema Registry

Each TR code has a YAML file under `krx_parser/schemas/`. **Every field
carries a Korean description** so the Streamlit UI can render Korean
column labels without extra translation tables.

```yaml
transaction_code: TCSMIH42101
description: 거래증거금_종목별증거금률(증권시장)
market: equity
encoding: euc-kr
arrays:
  - name: issues
    count: 16
    member_fields: [MARKET_IDENTIFICATION, SECURITIES_GROUP_IDENTIFICATION,
                    ISSUE_CODE, ISU_KOR_ABBRV, TRD_MRGN_RT]
fields:
  - seq: 1
    name: MESSAGE_SEQUENCE_NUMBER
    kor_name: 메세지일련번호
    kor_description: 메시지 일련번호
    type: Long
    length: 11
  - seq: 2
    name: TRANSACTION_CODE
    kor_name: 트랜잭션코드
    kor_description: 거래 코드 (TCSMIH42101)
    type: String
    length: 11
  - seq: 3
    name: TRANSMIT_DATE
    kor_name: 전송일자
    kor_description: 전송일자 YYYYMMDD, 적용일 당일 15시 송신
    type: String
    length: 8
  # ...
  - seq: 9
    name: TRD_MRGN_RT
    kor_name: 거래증거금률
    kor_description: 종목별 거래증거금률 (단위 %, 6.6 포맷)
    type: Float
    length: 13
    int_digits: 6
    frac_digits: 6
  - seq: 10
    name: FILLER_VALUE
    kor_name: 필러값
    kor_description: 예비 영역
    type: String
    length: 49
```

Loader behaviour:

- Compute cumulative byte offsets.
- Validate sum of field lengths × repeat counts against declared record
  length.
- Expose a fast `[(name, kor_name, start, end, type, params)]` slicing
  table.

## 8. Parser Design

- `Parser.parse(raw: bytes) -> ParsedMessage`
  1. Read `TRANSACTION_CODE` at offset 11, length 11.
  2. Look up schema from registry.
  3. Slice bytes per field definition. For repeating groups, slice
     `count` times and emit a list of dicts.
  4. Decode text as EUC-KR, coerce `Long` → int, `Float` → `Decimal`
     using `int_digits`/`frac_digits` placement.
  5. Return `ParsedMessage(header, body)` where each body field carries
     its value along with a reference to its schema entry (so the UI
     can show the Korean label).
- Unknown `TRANSACTION_CODE` → `UnknownMessageType`; raw bytes retained.
- Pure function; persistence is a separate call.

### Field encoding rules

- **String**: right-padded with spaces; decode as EUC-KR, strip trailing
  spaces.
- **Long**: left-padded with `'0'`; parse to `int`.
- **Float**: fixed-length ASCII with **implied** decimal placement
  (`I.F` from source, e.g., `18.3`). Read integer value from slice,
  divide by `10^F` to produce `Decimal`. Stored as decimal-string
  inside the JSON body column (SQLite preserves it as text, avoiding
  binary-float precision loss).
- Text encoding is **EUC-KR** for all Korean fields (confirmed).

## 9. Database Schema

SQLite file at `data/krx.db` (overridable via `KRX_DATABASE_URL`).
Enable WAL journaling at startup for better concurrent-read behaviour
while the Streamlit app writes:

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
```

### `raw_messages`

| column       | type                              | notes                              |
| ------------ | --------------------------------- | ---------------------------------- |
| id           | INTEGER PRIMARY KEY AUTOINCREMENT |                                    |
| received_at  | TEXT                              | ISO-8601 UTC; default `datetime('now')` |
| source       | TEXT                              | filename / `paste`                 |
| payload      | BLOB                              | raw bytes as received              |
| parse_status | TEXT                              | `pending` \| `parsed` \| `error`   |
| error_detail | TEXT                              | null unless parse failed           |

### `parsed_messages`

| column           | type                              | notes                                |
| ---------------- | --------------------------------- | ------------------------------------ |
| id               | INTEGER PRIMARY KEY AUTOINCREMENT |                                      |
| raw_message_id   | INTEGER                           | FK → `raw_messages.id`               |
| transaction_code | TEXT                              | `TCSMIH...`                          |
| message_seq      | INTEGER                           |                                      |
| transmit_date    | TEXT                              | `YYYY-MM-DD`                         |
| emsg_complt_yn   | TEXT                              | `Y` / `N`                            |
| body             | TEXT                              | JSON-encoded typed body (arrays for repeating groups) |

Indexes (B-tree):

- `(transaction_code, transmit_date)`
- `(transmit_date)`
- `(raw_message_id)`

For frequently-filtered JSON fields, declare generated columns so
SQLite can index them. Example:

```sql
ALTER TABLE parsed_messages ADD COLUMN member_number TEXT
  GENERATED ALWAYS AS (json_extract(body, '$.MEMBER_NUMBER')) VIRTUAL;
CREATE INDEX ix_parsed_member_number ON parsed_messages(member_number);
```

Apply the same pattern for `UNDERLYING_ASSET_CODE` and any other hot
filter paths surfaced by the Lookup page. Ad-hoc queries over other
JSON paths rely on `json_extract(body, '$.X')` without an index — fast
enough for the expected data volume.

Migrations via Alembic (SQLite backend; use `batch_alter_table` for any
column changes, since SQLite's `ALTER TABLE` is limited).

## 10. Streamlit GUI

Pages:

1. **Paste / Upload** — textarea for pasted log content plus file
   upload; preview first N parsed records in a table with Korean column
   labels; **Save to DB** button commits to `raw_messages` +
   `parsed_messages`.
2. **Lookup (Browse)** — search and filter parsed records by TR code,
   transmit date range, issue code, member number, underlying asset.
   Paginated table with Korean column headers; each row links to the
   inspect page.
3. **Inspect** — header + typed body (repeating groups as sub-tables) +
   raw payload side-by-side. Displays Korean field name, English field
   name, and value per row.
4. **Schemas** — browse registered TR codes and their field layouts
   with Korean descriptions.

## 11. Deployment

### 11.1 Environments

| Env   | OS                 | Network     | Notes                          |
| ----- | ------------------ | ----------- | ------------------------------ |
| Local | macOS              | online      | Developer workstation.         |
| QA    | RHEL 8             | **air-gapped** | No internet; no package index. |
| Prod  | RHEL 8             | **air-gapped** | No internet; no package index. |

### 11.2 Offline Python distribution

Because QA and prod cannot reach PyPI, every Python dependency (plus
transitive deps) must travel with the release artifact.

**Build workflow (on macOS or a Linux build host with internet):**

1. Lock dependencies from `pyproject.toml` / `requirements.txt` into a
   fully pinned `requirements.lock` (e.g., `pip-compile` or `uv pip
   compile`).
2. Download platform-specific wheels for RHEL 8's target Python:
   - Use `manylinux2014_x86_64` / `manylinux_2_28_x86_64` wheels;
     matches RHEL 8 glibc (2.28).
   - `pip download -r requirements.lock -d wheels/ --platform
     manylinux2014_x86_64 --python-version 3.11
     --implementation cp --abi cp311 --only-binary=:all:`.
3. For any sdist-only dependency, pre-build a wheel on a RHEL 8
   builder (same glibc) and include it in `wheels/`.
4. Produce a release tarball containing:
   - `krx_parser/` package source
   - `app/` Streamlit source
   - `wheels/` — all pinned wheels
   - `requirements.lock`
   - `alembic/` migrations
   - `shl/` — operator scripts (`install.sh`, `start.sh`, `stop.sh`)

**Target install on RHEL 8 (air-gapped):**

```bash
tar xzf krx-clearlog-<version>.tar.gz
cd krx-clearlog-<version>
./shl/install.sh      # creates .venv/, pip --no-index --find-links=wheels/, alembic upgrade head
./shl/start.sh        # launches Streamlit in the background, writes .krx.pid
./shl/stop.sh         # SIGTERM → SIGKILL on timeout
```

### 11.3 Build / release guidance

- Pin Python to a single version (3.11) for reproducibility; the lock
  file and wheel set must match that version.
- CI step: run `pip install --no-index --find-links=wheels/` inside a
  RHEL 8 container to verify the bundle is truly self-contained before
  shipping.
- No external database daemon is required — SQLite is embedded in the
  Python stdlib. The DB file lives under `data/krx.db` by default;
  override via `KRX_DATABASE_URL=sqlite:////abs/path/krx.db` if the
  customer wants it on a specific volume. Back up the single file.
- No dynamic downloads at runtime — Streamlit telemetry must be
  disabled (`STREAMLIT_BROWSER_GATHER_USAGE_STATS=false`), and no
  component that fetches from a CDN may be used.

## 12. Project Layout

```text
krx-clearlog/
├── spec/
│   ├── design.md
│   ├── messages.md
│   └── codes.md
├── pyproject.toml
├── requirements.lock
├── alembic/
│   └── versions/
├── data/
│   └── krx.db           # SQLite file (created on first run; git-ignored)
├── krx_parser/
│   ├── __init__.py
│   ├── parser.py
│   ├── schemas/
│   │   ├── TCSMIH41301.yaml
│   │   ├── TCSMIH42101.yaml
│   │   ├── TCSMIH42201.yaml
│   │   ├── TCSMIH42301.yaml
│   │   ├── TCSMIH42401.yaml
│   │   ├── TCSMIH43101.yaml
│   │   ├── TCSMIH43201.yaml
│   │   ├── TCSMIH43301.yaml
│   │   ├── TCSMIH43401.yaml
│   │   ├── TCSMIH43501.yaml
│   │   ├── TCSMIH43601.yaml
│   │   └── registry.py
│   ├── codes/
│   │   └── enums.py
│   ├── models.py
│   └── db/
│       ├── __init__.py
│       └── repository.py
├── app/
│   ├── main.py
│   └── pages/
│       ├── 1_Paste_Upload.py
│       ├── 2_Lookup.py
│       ├── 3_Inspect.py
│       └── 4_Schemas.py
├── shl/
│   ├── install.sh       # offline install (QA + prod)
│   ├── start.sh         # launch Streamlit, write .krx.pid
│   └── stop.sh          # SIGTERM → SIGKILL on timeout
└── tests/
    ├── test_parser.py
    └── fixtures/
        └── <TR_code>_sample.dat
```

## 13. Configuration

Environment variables:

- `KRX_DATABASE_URL` — SQLAlchemy DSN (default `sqlite:///data/krx.db`).
- `KRX_LOG_LEVEL` — default `INFO`.
- `KRX_SCHEMA_DIR` — override default schema directory.
- `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false` — required for
  air-gapped environments.

## 14. Open Questions

- **Record framing (from sample inspection)** — the `.log.gz` files
  under `samples/` are the producer process's stdout/stderr stream
  (syslog-style lines like
  `HH:MM:SS.uuuuuu LibProcEnv.c :InitExeArg :0293] I START === …`),
  not raw record streams. TCSMIH records are embedded inside log
  lines wrapped as `[KMAPv2.<7-digit-length><envelope-bytes><record>]`
  (observed lengths include `0001200` and `0001624`). Two concerns:
  1. **Ingestion adapter** — the parser currently accepts a clean
     1,200-byte slice; a log-to-record extractor that recognises the
     `KMAPv2.` frame header and strips the envelope still needs to be
     built (belongs in M3/M4, not M2).
  2. **TR-code scope** — the samples contain heavy volumes of codes
     outside our 11 (e.g. `TCSMIH26901` 850k, `TCSMIH10501` / `10401`
     500k each, `TCSMIH23101` 2.8k). `spec/messages.md` only defines
     the 증거금 messages (TCSMIH41xxx–43xxx); confirm with the
     customer whether the non-증거금 codes are in-scope for v1 or
     whether the parser should just log `UnknownMessageType` and skip.
- **Float sign byte** — the parser currently interprets the single
  unaccounted byte in every Float field (e.g., length 11 vs `7.3`;
  length 22 vs `18.3`; length 10 vs `7.2`) as an optional leading
  sign (`' '`, `'+'`, `'0'`, `'-'`). Consistent across all 11 TR
  codes. Confirm against a live record before treating this as fact.
- **TCSMIH43601 seq 2** — source prints `TCSMIH43501`; likely a typo
  for `TCSMIH43601`. Confirm with a sample.
- **TCSMIH43501 seq 12/13** — source reuses seq numbers; treated as
  seq 14/15 in schema. Confirm with a sample.
- **Retention policy** for `raw_messages.payload` (keep forever vs TTL).
- **RHEL 8 target Python** — confirm 3.11 is available via the
  customer's internal repo, or whether a pre-built Python runtime must
  be bundled too.

## 15. Milestones

1. **M1 — Schema capture** ✅: all 11 YAML layouts under
   `krx_parser/schemas/` with Korean field names + descriptions, each
   validated to sum to 1,200 bytes.
2. **M2 — Parser** ✅: `krx_parser.Parser` dispatches on
   `TRANSACTION_CODE`, decodes Long / String / Float (with optional
   sign byte) and repeating groups, raises `UnknownMessageType` for
   unregistered codes. 34 pytest tests cover round-trip, negative
   values, unknown codes, and short input. Fixtures are built
   programmatically via `tests/builder.py` until live-record framing
   is resolved (see §14).
3. **M3 — Persistence**: SQLAlchemy models, Alembic baseline,
   repository round-trip tests.
4. **M4 — Streamlit MVP**: Paste/Upload + Lookup pages end-to-end with
   Korean column headers.
5. **M5 — Inspect/Schemas pages + hardening**: error reporting UI,
   bulk-load performance.
6. **M6 — Offline release pipeline**: release-tarball build script
   (TBD under `shl/`) that bundles `wheels/`, `requirements.lock`,
   `alembic/`, `shl/`, and the app sources; verified by running
   `./shl/install.sh` inside a RHEL 8 container.
