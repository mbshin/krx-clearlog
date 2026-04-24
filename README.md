# krx-clearlog

Parser and Streamlit viewer for KRX 청산결제 (securities-market
clearing-and-settlement) log messages. Target deployment: air-gapped
RHEL 8.

See [`spec/design.md`](./spec/design.md) for architecture, scope, and
milestones; [`spec/messages.md`](./spec/messages.md) and
[`spec/codes.md`](./spec/codes.md) for the message specifications.

## Status

- **M1 — Schema capture** ✅ — 11 YAML schemas under
  `krx_parser/schemas/`, validated to 1,200 bytes each.
- **M2 — Parser** ✅ — `krx_parser.Parser` with repeating-group
  support.
- **M3 — Persistence** ✅ — SQLAlchemy + Alembic, `Repository`
  for ingest / search. SQLite file at `data/krx.db` by default.
- **M4 — Streamlit MVP** ✅ — `app/main.py` + 4 pages (Paste/Upload,
  Lookup, Inspect, Schemas) with Korean column labels.
- **M5 — Hardening** 🟡 partial — KMAPv2 frame extractor shipped
  (`krx_parser/frame.py` + Paste/Upload auto-detect). Decryption
  routine and bulk-load performance still outstanding (all TCSMIH
  frames in the real samples are `ENCRYPTED_YN=Y`; see
  `spec/design.md` §14).
- **M6 — Offline release pipeline** — not started.

53 pytest tests passing.

## Layout

```text
krx_parser/          # parser + persistence package (no UI deps)
  schema.py          # Field / Array / Schema dataclasses
  registry.py        # SchemaRegistry, YAML loader
  parser.py          # Parser.parse(bytes) -> ParsedMessage
  codes/enums.py     # StrEnums for the code sets in spec/codes.md
  schemas/*.yaml     # one file per TR code
  db/                # SQLAlchemy models, engine, Repository
  settings.py        # pydantic-settings (KRX_DATABASE_URL, …)
app/                 # Streamlit UI
  main.py            # landing page
  pages/             # 1_Paste_Upload, 2_Lookup, 3_Inspect, 4_Schemas
alembic/             # migrations; 0001_initial.py is the baseline
samples/             # drop real KRX log files here (gitignored)
shl/                 # operator scripts (install.sh / start.sh / stop.sh)
spec/                # message / code / regulation specs
tests/               # pytest suite; tests/builder.py is an inverse encoder
```

## Running the UI

```sh
alembic upgrade head                # create SQLite schema (first run)
streamlit run app/main.py           # launches on localhost:8501
```

Set `KRX_DATABASE_URL=sqlite:////abs/path/krx.db` to point the app at
an alternate SQLite file; the default is `sqlite:///data/krx.db`
relative to the process CWD.

## Developing

Target Python is 3.11 for parity with the RHEL 8 deployment.

```sh
python3 -m pytest            # run the test suite
python3 -m ruff check .      # lint
```

## Parsing a record

```python
from krx_parser import Parser, load_default_registry

parser = Parser(load_default_registry())
msg = parser.parse(raw_bytes)     # exactly 1,200 bytes per record
print(msg.transaction_code, msg.transmit_date)
print(msg.fields["MEMBER_NUMBER"])
for row in msg.arrays.get("issues", []):
    print(row["ISSUE_CODE"], row["TRD_MRGN_RT"])
```
