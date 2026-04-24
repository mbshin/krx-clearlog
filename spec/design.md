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

The file declares a `record_length` (total DATA-body bytes, excluding
the KMAPv2 envelope) and a single ordered `layout:` list of items;
each item is either a `kind: field` or a `kind: array` whose `fields:`
sub-list describes one array element. This keeps the file structure
aligned with the byte layout — offsets are computed left-to-right.

```yaml
transaction_code: TCSMIH42101
description: 거래증거금 — 종목별 증거금률 (증권시장)
market: equity
encoding: euc-kr
record_length: 1200

layout:
  - kind: field
    name: MESSAGE_SEQUENCE_NUMBER
    kor_name: 메세지일련번호
    kor_description: 메시지 일련번호
    type: Long
    length: 11
  - kind: field
    name: TRANSACTION_CODE
    kor_name: 트랜잭션코드
    kor_description: 거래 코드 (TCSMIH42101)
    type: String
    length: 11
  # ... seq 3, 4
  - kind: array
    name: issues
    count: 16
    fields:
      - name: MARKET_IDENTIFICATION
        kor_name: 시장ID
        kor_description: KRX 차세대 상품 ID체계 — 시장ID
        type: String
        length: 3
      # ... SECURITIES_GROUP_IDENTIFICATION, ISSUE_CODE, ISU_KOR_ABBRV
      - name: TRD_MRGN_RT
        kor_name: 거래증거금률
        kor_description: 단위 %; 6.6 포맷
        type: String
        length: 13
        int_digits: 6
        frac_digits: 6
  - kind: field
    name: FILLER_VALUE
    kor_name: 필러값
    kor_description: 예비 영역
    type: String
    length: 49
```

Numeric fields — whether declared `Float` or `String` with
`int_digits`/`frac_digits` — allow a single optional sign byte when
`length > int_digits + frac_digits` (`' '`/`'+'`/`'0'` → positive,
`'-'` → negative). This is consistent across every TR code we have
and is still awaiting confirmation against a live record (see §14).

Loader behaviour (`krx_parser.registry.load_registry`):

- Walk `layout` left-to-right, computing `offset` for each field.
- Validate sum of item lengths (flat fields + arrays × element
  length) equals the declared `record_length`.
- Validate each numeric field's `length - int_digits - frac_digits`
  is `0` or `1` (sign-byte budget).
- Expose `SchemaRegistry.get(tr_code) -> Schema` for parser dispatch.

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
│   ├── codes.md
│   ├── regulation.md
│   └── enforcement_rules.md
├── pyproject.toml
├── requirements.lock           # TBD: lockfile for offline install
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial.py
├── data/                       # SQLite DB (created on first run; git-ignored)
│   └── krx.db
├── samples/                    # real KRX log files (git-ignored)
├── krx_parser/
│   ├── __init__.py
│   ├── exceptions.py
│   ├── schema.py               # Field / Array / Schema dataclasses
│   ├── registry.py             # SchemaRegistry, YAML loader
│   ├── parser.py               # Parser.parse(bytes) -> ParsedMessage
│   ├── settings.py             # pydantic-settings
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
│   │   └── TCSMIH43601.yaml
│   ├── codes/
│   │   ├── __init__.py
│   │   └── enums.py            # StrEnums per spec/codes.md
│   └── db/
│       ├── __init__.py
│       ├── engine.py           # create_engine + WAL/foreign_keys pragmas
│       ├── models.py           # RawMessage / ParsedMessageRow
│       ├── repository.py       # Repository.ingest + .search
│       └── serialize.py        # JSON body (Decimal → str) round-trip
├── app/
│   ├── __init__.py
│   ├── main.py                 # nav shell — st.navigation entry
│   ├── home.py                 # landing page
│   ├── helpers.py              # cached registry/parser/engine + scopes
│   └── pages/
│       ├── 1_Paste_Upload.py
│       ├── 2_Lookup.py
│       ├── 3_Inspect.py
│       ├── 4_Schemas.py        # browse + Ace YAML editor (CRUD)
│       └── 5_Admin.py          # delete by TR / clear errors / truncate
├── shl/
│   ├── install.sh              # offline install (QA + prod)
│   ├── start.sh                # launch Streamlit, write .krx.pid
│   └── stop.sh                 # SIGTERM → SIGKILL on timeout
└── tests/
    ├── __init__.py
    ├── conftest.py             # shared registry fixture
    ├── builder.py              # inverse encoder — build_record(schema, …)
    ├── test_parser.py
    └── test_repository.py
```

## 13. Configuration

Environment variables:

- `KRX_DATABASE_URL` — SQLAlchemy DSN (default `sqlite:///data/krx.db`).
- `KRX_LOG_LEVEL` — default `INFO`.
- `KRX_SCHEMA_DIR` — override default schema directory.
- `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false` — required for
  air-gapped environments.

## 14. Open Questions

- **Frame extraction & decryption — resolved.** `krx_parser/frame.py`
  extracts KMAPv2 frames from arbitrary byte streams at ~370k
  frames/s (`samples/TR_001`: 37,713 frames in ~0.1 s). The scanner
  validates each frame's DATA against its envelope
  (`MSG_SEQ_NUM` = 11 ASCII digits followed by the declared
  `TRANSACTION_CODE`); this discards the `RECV_0 [KMAPv2.0…]`
  log-line echoes whose "DATA" is actually log text, leaving the
  `TG_DecryptLOG [KMAPv2.0…]` frames whose DATA is already plaintext
  (the producer decrypts before logging). **No external decryption
  primitive is needed** — the plaintext is already in the log
  stream. All 533 in-scope frames in TR_001 parse cleanly.
- **Numeric field format.** Real samples emit numeric-formatted
  fields (e.g. `TRD_MRGN_RT` in TCSMIH42101) with a **literal decimal
  point** (`000015.220000` for a 13-byte 6.6 field) rather than a
  sign byte. The parser now handles both: when
  `length == int_digits + frac_digits + 1` and the byte at offset
  `int_digits` is `.`, the dot is stripped and digits are
  concatenated; otherwise the extra byte is treated as a sign
  indicator. Negative values with `-` still round-trip.
- **TR-code scope.** The frame scan surfaces codes outside our 11:
  `SCHHEQ00000` ×15,702 and `SCHHER00000` ×10,468 (plaintext
  schedule/event messages) plus `TCSMIH26501`/`26201`/`20501`/
  `20301`/`70301`/`20701` ranging 4k–100 frames each. `spec/
  messages.md` only defines the 증거금 messages (TCSMIH41xxx–43xxx).
  `Repository.ingest_frames(..., skip_unknown_tr=True)` silently
  drops frames whose TR code isn't in the registry so the DB stays
  focused; flip the flag to store them as `raw_messages` for later
  triage. Confirm with the customer whether any non-증거금 codes
  should be brought in-scope.
- **Bulk-load throughput.** `iter_frames` takes `bytes`, so the
  1.6 GB TR_002 sample currently requires the full file in memory.
  A streaming scanner (chunked decompress + carry-over buffer) is
  still TBD.
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
3. **M3 — Persistence** ✅: SQLAlchemy 2.x models
   (`raw_messages` + `parsed_messages`) in `krx_parser/db/`, Alembic
   baseline (`alembic/versions/0001_initial.py`) with WAL +
   foreign_keys pragmas on first SQLite connect. `Repository` layer
   handles ingest + search by TR code / date range / MEMBER_NUMBER /
   UNDERLYING_ASSET_CODE. Decimals serialised as JSON strings to
   preserve precision. 6 repository tests added (40 total passing).
4. **M4 — Streamlit MVP** ✅: `app/main.py` landing + pages
   `1_Paste_Upload`, `2_Lookup`, `3_Inspect`, `4_Schemas`. Korean
   column labels throughout. Mixed-TR-code streams handled via
   `peek_transaction_code` + `record_length`. Run with
   `streamlit run app/main.py`; verified headless boot (HTTP 200).
5. **M5 — Hardening** 🟡 mostly shipped:
   - ✅ KMAPv2 frame extractor (`krx_parser/frame.py`) with
     `parse_header` / `parse_frame` / `iter_frames` scanner; DATA
     self-consistency validation rejects log-line echoes; verified
     against `samples/TR_001` at ~370k frames/s.
   - ✅ Decryption sidestepped — the producer's log already contains
     the decrypted DATA via `TG_DecryptLOG`; all 533 in-scope frames
     in TR_001 parse cleanly.
   - ✅ Numeric-field decimal-point format (`000015.220000`)
     supported alongside the sign-byte + implicit-decimal form.
   - ✅ `Repository.ingest_frame` + `ingest_frames(skip_unknown_tr=…)`.
   - ✅ Admin page: delete by TR code, clear error rows, truncate all.
   - ✅ Upload page: gzip auto-decompress, KMAPv2 auto-detect,
     per-TR-code breakdown before save.
   - ✅ Lookup + Inspect: per-row Open button, same-tab `st.switch_page`
     navigation, **← Back** button, URL-synced filter state.
   - ✅ Schemas page: Ace YAML editor with live preview + CRUD
     (`parse_schema_yaml`, `write_schema_text`, `delete_schema_file`).
   - 🔲 Streaming frame scanner (for the 1.6 GB TR_002 sample).
6. **M6 — Offline release pipeline**: release-tarball build script
   (TBD under `shl/`) that bundles `wheels/`, `requirements.lock`,
   `alembic/`, `shl/`, and the app sources; verified by running
   `./shl/install.sh` inside a RHEL 8 container.
