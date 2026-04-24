# krx-clearlog — Install & Run Guide

This document walks through every step needed to get the parser and
Streamlit UI running on a fresh machine. It covers three scenarios:

1. **Developer (online)** — macOS / Linux with internet access.
2. **Release bundle** — building an offline tarball on a builder host.
3. **Air-gapped RHEL 8 (QA / prod)** — installing the offline bundle
   on a host with no PyPI access.

Spec companion: [`../spec/design.md`](../spec/design.md) §11–§13 for
architecture context; [`../README.md`](../README.md) for a condensed
quickstart.

---

## 1. Prerequisites

| Requirement | Version | Notes |
| ----------- | ------- | ----- |
| Python      | **3.11** | Exact minor version. 3.12/3.13 work locally but deployment pins 3.11. |
| git         | any modern | Only needed for initial clone. |
| sqlite3     | bundled with Python | No external DB daemon. |
| Disk        | ~200 MB | Plus SQLite DB growth per ingested log. |
| RAM         | 2 GB min | 4 GB+ comfortable for the 77 MB TR_001 sample. |

**Optional but recommended for developers:**

- `pip-tools` — generate `requirements.lock` for the offline bundle.
- `watchdog` — faster Streamlit hot-reload.

On macOS:

```sh
brew install python@3.11 git
```

On RHEL 8:

```sh
sudo dnf install -y python3.11 git
```

If python 3.11 isn't in the customer's internal repos, ship a
pre-built interpreter in the release tarball (see §3.2).

---

## 2. Developer setup (online)

```sh
# 2.1 Clone
git clone git@github.com:mbshin/krx-clearlog.git
cd krx-clearlog

# 2.2 Create + activate virtualenv
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2.3 Install runtime + dev dependencies (editable)
pip install --upgrade pip
pip install -e '.[dev]'

# 2.4 Create the SQLite schema at data/krx.db
alembic upgrade head

# 2.5 Launch the Streamlit UI
streamlit run app/main.py --server.maxUploadSize=500
```

Streamlit prints a local URL (`http://localhost:8501` by default) —
open it in the browser.

### 2.1 Running the tests + lint

```sh
pytest                   # 61 tests; also validates every schema YAML
ruff check .
```

### 2.2 Common dev tasks

| Task                                | Command                                                        |
| ----------------------------------- | -------------------------------------------------------------- |
| Reset the DB                        | `rm data/krx.db && alembic upgrade head`                       |
| Generate a new Alembic migration    | `alembic revision --autogenerate -m "your message"`            |
| Apply a single migration            | `alembic upgrade +1`                                           |
| Roll back one migration             | `alembic downgrade -1`                                         |
| Format imports                      | `ruff check --fix .`                                           |
| Load a sample file for testing      | Use the UI's **📥 Upload** page, or place under `samples/`     |

### 2.3 Environment variables

All prefixed `KRX_`. Set in the current shell or via `.env` if you
add `pydantic-settings`' dotenv loader.

| Var                | Default                 | Purpose                                                    |
| ------------------ | ----------------------- | ---------------------------------------------------------- |
| `KRX_DATABASE_URL` | `sqlite:///data/krx.db` | SQLAlchemy DSN. Use `sqlite:////abs/path/krx.db` for an absolute path. |
| `KRX_SCHEMA_DIR`   | `krx_parser/schemas/`   | Override where the registry reads/writes YAML schemas.     |
| `KRX_LOG_LEVEL`    | `INFO`                  | Python logging level name.                                 |
| `STREAMLIT_BROWSER_GATHER_USAGE_STATS` | *(unset)* | Set to `false` to disable Streamlit telemetry (mandatory for air-gapped). |

`shl/start.sh` and `shl/install.sh` honour additional overrides
(`KRX_PYTHON`, `KRX_WHEELS_DIR`, `KRX_REQ_FILE`, `KRX_PORT`,
`KRX_HOST`, `KRX_APP_ENTRY`, `KRX_LOG_DIR`, `KRX_PID_FILE`,
`KRX_STOP_TIMEOUT`, `KRX_FORCE`).

---

## 3. Building an offline release bundle

Run on a **Linux x86_64 host with internet access** (e.g. a macOS
laptop will also work for most deps, but sdist-only packages may need
a RHEL 8 builder — see §3.3).

```sh
# 3.1 Freeze the current dependency set
pip install pip-tools
pip-compile -o requirements.lock --strip-extras pyproject.toml

# 3.2 Download manylinux2014 wheels for Python 3.11
mkdir -p wheels
pip download -r requirements.lock \
  --dest wheels/ \
  --platform manylinux2014_x86_64 \
  --python-version 3.11 \
  --implementation cp \
  --abi cp311 \
  --only-binary=:all:

# 3.3 Any sdist-only packages?  Build their wheels on a RHEL 8 builder
#     (same glibc as target) and drop the resulting .whl into wheels/.

# 3.4 Verify the bundle is self-contained by installing into a clean
#     venv:
python3.11 -m venv /tmp/verify-venv
source /tmp/verify-venv/bin/activate
pip install --no-index --find-links=wheels/ --upgrade pip
pip install --no-index --find-links=wheels/ -r requirements.lock
deactivate && rm -rf /tmp/verify-venv

# 3.5 Assemble the tarball
tar czf krx-clearlog-$(git rev-parse --short HEAD).tar.gz \
  krx_parser/ app/ alembic/ alembic.ini \
  shl/ wheels/ requirements.lock pyproject.toml \
  README.md docs/ spec/
```

Ship that single tarball to QA / prod.

---

## 4. Air-gapped RHEL 8 install

Assumes the tarball from §3 has already been copied to the target
host (scp, USB, etc.).

```sh
# 4.1 Extract
tar xzf krx-clearlog-<version>.tar.gz
cd krx-clearlog-<version>

# 4.2 Run the offline installer — creates .venv/ from wheels/,
#     runs alembic upgrade head
./shl/install.sh

# 4.3 Start the app in the background (writes .krx.pid + logs/app.log)
./shl/start.sh

# 4.4 Confirm it's serving
curl -sf http://localhost:8501/_stcore/health && echo ok
```

To stop: `./shl/stop.sh` (SIGTERM → SIGKILL after `KRX_STOP_TIMEOUT`
seconds).

To wipe + reinstall from scratch:

```sh
KRX_FORCE=1 ./shl/install.sh
```

### 4.1 Where things live

```text
<install-root>/
  .venv/          # created by install.sh
  wheels/         # shipped in the tarball; referenced during install
  data/krx.db     # SQLite file (created on first run)
  logs/app.log    # Streamlit stdout/stderr
  .krx.pid        # running process id
```

### 4.2 Runtime config

The scripts honour these env vars (override via `/etc/default/krx-clearlog`
or a systemd `EnvironmentFile=`):

| Var               | Default                 |
| ----------------- | ----------------------- |
| `KRX_PYTHON`      | `python3.11`            |
| `KRX_WHEELS_DIR`  | `wheels`                |
| `KRX_REQ_FILE`    | `requirements.lock`     |
| `KRX_APP_ENTRY`   | `app/main.py`           |
| `KRX_PORT`        | `8501`                  |
| `KRX_HOST`        | `0.0.0.0`               |
| `KRX_LOG_DIR`     | `logs`                  |
| `KRX_PID_FILE`    | `.krx.pid`              |
| `KRX_STOP_TIMEOUT`| `15` (seconds)          |
| `KRX_FORCE`       | unset (set `1` to re-install) |

### 4.3 systemd unit (optional)

```ini
# /etc/systemd/system/krx-clearlog.service
[Unit]
Description=KRX 청산결제 Log Viewer
After=network.target

[Service]
Type=forking
WorkingDirectory=/opt/krx-clearlog
EnvironmentFile=/etc/default/krx-clearlog
ExecStart=/opt/krx-clearlog/shl/start.sh
ExecStop=/opt/krx-clearlog/shl/stop.sh
PIDFile=/opt/krx-clearlog/.krx.pid
Restart=on-failure
User=krx
Group=krx

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now krx-clearlog
sudo journalctl -u krx-clearlog -f
```

---

## 5. Upgrading

### Developer

```sh
git pull
pip install -e '.[dev]'      # picks up any new deps
alembic upgrade head         # applies new migrations if any
```

### Air-gapped deployment

1. Build a new tarball (§3) including any new / updated wheels.
2. `scp` it to the target.
3. Stop the service, extract over the previous install root (or into a
   new `<version>/` dir with a `current -> <version>/` symlink),
   run `./shl/install.sh`, start it again.

```sh
./shl/stop.sh
tar xzf krx-clearlog-<new>.tar.gz
cd krx-clearlog-<new>
./shl/install.sh    # re-creates .venv, runs alembic upgrade head
./shl/start.sh
```

The Alembic `batch_alter_table` pattern is used for any SQLite
schema change that touches existing columns; migrations are
idempotent.

---

## 6. Troubleshooting

| Symptom                                                    | Likely cause / fix                                                                 |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `ModuleNotFoundError: streamlit_ace`                       | Re-run `pip install -e '.[dev]'` or `./shl/install.sh`.                            |
| `alembic upgrade head` fails with "no such table"          | First-run DB creation; run from repo root so `data/` resolves correctly.           |
| Upload page says "Could not detect any KMAPv2 frames"      | File is probably a process stdout log — verify it contains `KMAPv2.0` byte sequences. |
| "0 parsed records, N in-scope frames failed"               | DATA is still cipher-text (RECV echo) — ensure you're uploading the log containing the `TG_DecryptLOG` entries. |
| Streamlit port already in use                              | `KRX_PORT=8502 ./shl/start.sh`                                                     |
| `./shl/start.sh: already running`                          | `./shl/stop.sh` first, or `rm .krx.pid` if a previous run crashed.                 |
| Large uploads time out                                     | `--server.maxUploadSize=500` is set by the Quickstart; bump higher if needed. The 1.6 GB TR_002 sample currently requires a future streaming scanner. |
| Schema edits disappear after restart                       | `KRX_SCHEMA_DIR` points at a tmp dir — set it explicitly or leave default.         |
| `ERROR: wheels not found`                                  | `install.sh` expects a `wheels/` next to itself; was the tarball partially extracted? |

### Checking health

```sh
# Process
cat .krx.pid; ps -p $(cat .krx.pid)

# HTTP
curl -sf http://localhost:8501/_stcore/health

# Tail the app log
tail -f logs/app.log

# Inspect the DB
sqlite3 data/krx.db '.tables'
sqlite3 data/krx.db 'SELECT transaction_code, COUNT(*) FROM parsed_messages GROUP BY 1'
```

---

## 7. Uninstall

```sh
./shl/stop.sh
cd ..
rm -rf krx-clearlog-<version>
# If a systemd unit was installed:
sudo systemctl disable --now krx-clearlog
sudo rm /etc/systemd/system/krx-clearlog.service
sudo systemctl daemon-reload
```

The SQLite DB is a single file (`data/krx.db`) — back up or delete as
you see fit.
