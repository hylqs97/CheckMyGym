# CheckMyGym

CheckMyGym is a lightweight Flask dashboard for tracking gym occupancy. It polls the upstream gym API on a schedule, stores snapshots as JSONL, and serves a fast mobile-friendly dashboard.

## What Changed In This Version

- Replaced the heavy inline React/Babel dashboard with plain HTML, CSS, and vanilla JavaScript.
- Added a single `/api/bootstrap` endpoint so the first page load only needs one data request.
- Moved dashboard assets into dedicated static files:
  - `static/css/dashboard.css`
  - `static/js/dashboard.js`
- Added cached parsing and cached summary generation for `gym_data.jsonl` to reduce repeated disk reads.
- Reused a shared `requests.Session()` for upstream polling to reduce connection setup overhead.
- Hardened the daemon script so stale Windows PID files do not cause false "already running" results.

## Requirements

- Python 3.10+

## Install

```bash
python -m venv .venv
```

Linux / macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run In Foreground

```bash
python app.py
```

Default local URL:

- `http://127.0.0.1:6767`

The first run creates `config.json` automatically.

## Run In Background

Use the bundled daemon helper:

```bash
python scripts/run_daemon.py start --use-defaults
```

Useful variants:

```bash
python scripts/run_daemon.py start
python scripts/run_daemon.py start --use-defaults --host dual
python scripts/run_daemon.py status
python scripts/run_daemon.py stop
```

## Configuration

`config.json` is created automatically. Main fields:

- `storage_dir`: data directory for JSONL snapshots
- `poll_interval_minutes`: scheduler interval
- `shop_id`: upstream gym identifier
- `api_base`: upstream API base URL
- `open_hour_start`: dashboard hour filter start
- `open_hour_end`: dashboard hour filter end
- `host`: `dual`, `0.0.0.0`, `::`, or `127.0.0.1`
- `port`: HTTP listen port
- `favorites`: tracked member ids

## API Endpoints

- `GET /`: dashboard page
- `GET /api/bootstrap`: config + dashboard data for first paint
- `GET /api/config`: current config
- `POST /api/config`: update mutable config values
- `GET /api/data`: dashboard data only
- `POST /api/poll`: trigger one background poll
- `GET /api/favorites`: list favorite ids
- `POST /api/favorites`: add or remove a favorite
- `GET /api/health`: basic service status

## Project Layout

```text
CheckMyGym/
|-- app.py
|-- gym_service.py
|-- templates/
|   `-- index.html
|-- static/
|   |-- css/
|   |   `-- dashboard.css
|   `-- js/
|       `-- dashboard.js
|-- scripts/
|   |-- run_daemon.py
|   |-- run_linux_daemon.py
|   |-- setup_autorun.ps1
|   `-- remove_autorun.ps1
|-- data/
|-- logs/
|-- config.json
`-- requirements.txt
```

## Data Format

Snapshots are appended to:

- `<storage_dir>/gym_data.jsonl`

Each line is a JSON object, for example:

```json
{
  "timestamp": "2026-03-01 08:30:00",
  "people_num": 12,
  "using_man": []
}
```

## Windows Autorun

Register a scheduled task at user logon:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_autorun.ps1 -PythonExe ".\.venv\Scripts\python.exe"
```

Remove it:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\remove_autorun.ps1
```

## Linux Service

For Linux, prefer running `app.py` directly under `systemd` instead of double-forking through the daemon helper.

Example service:

```ini
[Unit]
Description=CheckMyGym
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/CheckMyGym
ExecStart=/path/to/CheckMyGym/.venv/bin/python /path/to/CheckMyGym/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Notes

- `scripts/run_linux_daemon.py` is kept only as a compatibility wrapper.
- `demo_code.py` is a legacy one-off fetch example and is not used by the dashboard.
