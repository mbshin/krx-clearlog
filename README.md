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
  support, 34 pytest tests passing.
- M3–M6 — not started.

## Layout

```text
krx_parser/          # parser package (no UI/DB deps)
  schema.py          # Field / Array / Schema dataclasses
  registry.py        # SchemaRegistry, YAML loader
  parser.py          # Parser.parse(bytes) -> ParsedMessage
  codes/enums.py     # StrEnums for the code sets in spec/codes.md
  schemas/*.yaml     # one file per TR code
samples/             # drop real KRX log files here (gitignored)
shl/                 # operator scripts (install.sh / start.sh / stop.sh)
spec/                # message / code / regulation specs
tests/               # pytest suite; tests/builder.py is an inverse encoder
```

## Developing

Target Python is 3.11 for parity with the RHEL 8 deployment. Tests
pass on 3.11+ (no 3.12- or 3.13-specific features).

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
