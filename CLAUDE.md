# krx-clearlog

Parser for KRX securities-market clearing-and-settlement (청산결제)
messages. A Streamlit UI lets users paste or upload log text, parses
the fixed-width records, persists the raw + parsed payloads, and
supports lookup/inspection. Deployment target: air-gapped RHEL 8.

## Spec files

Read these before starting work:

- [`spec/design.md`](./spec/design.md) — architecture, tech stack, project layout, deployment strategy, open issues.
- [`spec/messages.md`](./spec/messages.md) — field layouts for every TR code (Korean field names preserved).
- [`spec/codes.md`](./spec/codes.md) — enumerated code sets referenced by fields.
- [`spec/regulation.md`](./spec/regulation.md) — upstream regulation: 증권시장 청산결제 업무규정 (제2287호).
- [`spec/enforcement_rules.md`](./spec/enforcement_rules.md) — enforcement rules (제2297호), 별표 1~6, 별지 제1~5호 서식.

## Ops scripts

Shell scripts live in `shl/`.

- `shl/install.sh` — offline install (QA + prod share it). Uses local
  `wheels/` and `requirements.lock` to populate `.venv`, then runs
  `alembic upgrade head`. Re-runnable; pass `KRX_FORCE=1` to wipe and
  recreate `.venv` from scratch.
- `shl/start.sh` — launches Streamlit in the background, writes
  `.krx.pid`.
- `shl/stop.sh` — reads `.krx.pid`, sends SIGTERM, then SIGKILL on
  timeout.

Environment overrides: `KRX_PYTHON`, `KRX_WHEELS_DIR`, `KRX_REQ_FILE`,
`KRX_PORT`, `KRX_HOST`, `KRX_APP_ENTRY`, `KRX_LOG_DIR`, `KRX_PID_FILE`,
`KRX_STOP_TIMEOUT`, `KRX_FORCE` (prod re-install).

## Language

- **English** for all project docs, code, comments, commit messages,
  and conversational output.
- **Korean** only for:
  - The body of regulation / enforcement-rule articles in
    `spec/regulation.md` and `spec/enforcement_rules.md` (원문 preserved
    verbatim — never translated).
  - Korean field names / descriptions in message schemas, which the
    Streamlit UI renders directly as column labels.

## Conventions

- Schema YAMLs keep each field's Korean description alongside the
  English identifier so the UI can show Korean labels without a
  separate translation table.
- Text encoding for message payloads is EUC-KR (per the message spec).
- Float fields use implied decimal placement (e.g. `18.3` format) —
  declare `int_digits` / `frac_digits` in YAML.
- Target Python is 3.11 (reproducibility + RHEL 8 deployment).
