# krx-clearlog

Parser and Streamlit viewer for KRX 청산결제 (securities-market
clearing-and-settlement) log messages. Target deployment: air-gapped
RHEL 8.

See [`spec/design.md`](./spec/design.md) for architecture, scope, and
milestones; [`spec/messages.md`](./spec/messages.md) and
[`spec/codes.md`](./spec/codes.md) for the message specifications.

## Quickstart

Requires Python **3.11** (matches the RHEL 8 deployment target).

```sh
# 1. Clone
git clone git@github.com:mbshin/krx-clearlog.git
cd krx-clearlog

# 2. Create + activate a virtualenv
python3.11 -m venv .venv
source .venv/bin/activate       # on Windows: .venv\Scripts\activate

# 3. Install runtime + dev deps (editable install)
pip install -e '.[dev]'

# 4. Create the SQLite schema (creates data/krx.db)
alembic upgrade head

# 5. Launch the Streamlit UI
streamlit run app/main.py --server.maxUploadSize=500
```

Streamlit prints a URL — open `http://localhost:8501` in the browser.

**Typical flow:**
1. Drop a KRX log (`.log` or `.log.gz`) into **📥 Upload** → *Save to
   database*.
2. Find records in **🔎 Lookup** — filters are mirrored in the URL so
   views are shareable.
3. Click **🔬 Open** on any row to jump to **🔬 Inspect** (same tab,
   **← Back** returns to the same filter view).
4. Edit schemas live in **📘 Schemas → Edit / Create** (Ace YAML
   editor with live validation).
5. **🧹 Admin** to clear rows (by TR, error-only, or full truncate).

### Air-gapped RHEL 8 install

`pip` above assumes internet access. For the customer deployment,
`shl/install.sh` does an offline install from a bundled `wheels/`
directory + `requirements.lock` — see `spec/design.md` §11.

```sh
./shl/install.sh        # offline install from wheels/
./shl/start.sh          # launches Streamlit in the background, writes .krx.pid
./shl/stop.sh           # SIGTERM → SIGKILL on timeout
```

### Useful env vars

| Var                | Default                 | Purpose                                                    |
| ------------------ | ----------------------- | ---------------------------------------------------------- |
| `KRX_DATABASE_URL` | `sqlite:///data/krx.db` | SQLAlchemy DSN. Use `sqlite:////abs/path/krx.db` for an absolute path. |
| `KRX_SCHEMA_DIR`   | `krx_parser/schemas/`   | Override where the registry reads/writes YAML schemas.     |
| `KRX_LOG_LEVEL`    | `INFO`                  | Python logging level name.                                 |
| `STREAMLIT_BROWSER_GATHER_USAGE_STATS` | *(unset)* | Set to `false` for air-gapped installs.        |

### Running the tests

```sh
pytest              # 61 tests; also validates all 11 YAML schemas on import
ruff check .        # lint
```

## Status

- **M1 — Schema capture** ✅ — 11 YAML schemas, validated to 1,200 bytes each.
- **M2 — Parser** ✅ — repeating-group support; numeric fields handle both
  implicit-decimal + sign-byte and literal-decimal-point formats (real
  samples emit `TRD_MRGN_RT = 000015.220000`).
- **M3 — Persistence** ✅ — SQLAlchemy + Alembic, `Repository` with
  ingest / search / delete.
- **M4 — Streamlit MVP** ✅ — 5 pages (Upload, Lookup, Inspect, Schemas,
  Admin) with Korean column labels, per-row Open buttons, URL-synced
  filters, Back navigation.
- **M5 — Hardening** 🟡 mostly shipped — KMAPv2 frame extractor with
  self-consistency validation, gzip auto-decompress on upload, Schema
  CRUD with Ace YAML editor. Decryption is not needed: the producer's
  log already contains the decrypted DATA via `TG_DecryptLOG`.
  Remaining: streaming scanner for the 1.6 GB TR_002 sample.
- **M6 — Offline release pipeline** — not started.

## Layout

```text
krx_parser/          # parser + persistence package (no UI deps)
  schema.py          # Field / Array / Schema dataclasses
  registry.py        # SchemaRegistry + YAML CRUD (read/write/delete)
  parser.py          # Parser.parse(bytes) -> ParsedMessage
  frame.py           # KMAPv2.0 envelope: parse_header / iter_frames
  codes/enums.py     # StrEnums for the code sets in spec/codes.md
  schemas/*.yaml     # one file per TR code (editable from the UI)
  db/                # SQLAlchemy models, engine, Repository
  settings.py        # pydantic-settings (KRX_DATABASE_URL, …)
app/                 # Streamlit UI
  main.py            # nav shell (st.navigation)
  home.py            # landing page
  helpers.py         # cached registry/parser/engine + scopes, extractors
  pages/             # 1_Paste_Upload, 2_Lookup, 3_Inspect, 4_Schemas, 5_Admin
alembic/             # migrations; 0001_initial.py is the baseline
samples/             # drop real KRX log files here (gitignored)
shl/                 # operator scripts (install.sh / start.sh / stop.sh)
spec/                # message / code / regulation specs
tests/               # pytest suite; tests/builder.py is an inverse encoder
```

## Pages

- **📑 Home** — status metrics and ingestion summary.
- **📥 Upload** — upload `.log` / `.log.gz` or paste record bytes.
  Auto-detects gzip and KMAPv2 framing; shows a per-TR-code breakdown;
  out-of-scope codes (SCHHE*, TCSMIH26xxx, …) are skipped; parseable
  frames are persisted.
- **🔎 Lookup** — filter parsed records by TR code, transmit date,
  회원번호, 기초자산코드. Filter state mirrors in the URL so any view
  is shareable. Per-row **🔬 Open** button navigates to Inspect.
- **🔬 Inspect** — full field-by-field breakdown (Korean labels,
  repeating-group sub-tables, raw payload hex+ASCII). **← Back**
  restores the previous filter view.
- **📘 Schemas** — two tabs: *Browse* (read-only view of a TR layout)
  and *Edit / Create* (Ace YAML editor with live preview, theme + font
  picker, save/reset/delete, cache invalidation on commit).
- **🧹 Admin** — delete rows by TR code, clear `parse_status='error'`
  rows, or truncate both tables (gated behind "type DELETE").

## Parsing a record programmatically

```python
from krx_parser import Parser, iter_frames, load_default_registry

registry = load_default_registry()
parser = Parser(registry)

# Option A — one clean DATA block (1,200 bytes for our 11 TR codes)
msg = parser.parse(raw_bytes)
print(msg.transaction_code, msg.fields["MEMBER_NUMBER"])
for row in msg.arrays.get("issues", []):
    print(row["ISSUE_CODE"], row["TRD_MRGN_RT"])

# Option B — a full log stream with KMAPv2 envelopes
for frame in iter_frames(stream_bytes):
    if frame.header.message_type in registry:
        parsed = parser.parse(frame.data)
        ...
```
