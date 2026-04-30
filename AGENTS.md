# AGENTS.md

Guidance for automated coding agents working in this repository.

## Project Overview

CheckMyGym is a lightweight Flask dashboard for tracking gym occupancy. The server polls an upstream gym API on a schedule, appends snapshots to a local JSONL file, summarizes cached data for the dashboard, and can send QQ notifications through a OneBot-compatible HTTP endpoint.

## Repository Layout

- `app.py` — Flask app, API routes, scheduler startup, polling orchestration, and HTTP server binding.
- `gym_service.py` — core service layer:
  - `DEFAULT_CONFIG` and `ConfigManager` for config defaults, persistence, and normalization.
  - `DataStore` for JSONL append/load/cache/summary logic.
  - `QQNotificationManager` for low-traffic and watched-arrival notifications.
  - `fetch_gym_status()` for upstream API polling using a shared `requests.Session()`.
- `templates/index.html` — dashboard markup.
- `static/js/dashboard.js` — vanilla JavaScript dashboard behavior and API calls.
- `static/css/dashboard.css` — dashboard styling.
- `scripts/run_daemon.py` — cross-platform background start/status/stop helper.
- `scripts/run_linux_daemon.py` — compatibility wrapper; prefer `app.py` under `systemd` on Linux.
- `init_env.py` — bootstrap helper that creates `config.json` and the configured data directory.
- `demo_code.py` — legacy one-off fetch example; not used by the dashboard.

## Runtime and Local State

Local runtime files are intentionally ignored by Git:

- `config.json`
- `data/` including `gym_data.jsonl` and notification state
- `logs/`
- `.checkmygym.pid`
- Python cache files

Do not delete, rewrite, or commit user-local data/log/config files unless explicitly requested. Treat `data/gym_data.jsonl` as user data.

## Setup and Run Commands

Use Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run in the foreground:

```bash
python app.py
```

Prepare local config/data without starting the server:

```bash
python init_env.py
```

Use the daemon helper:

```bash
python scripts/run_daemon.py start --use-defaults
python scripts/run_daemon.py status
python scripts/run_daemon.py stop
```

Default URL: `http://127.0.0.1:6767`.

## Validation

There is currently no configured automated test suite or lint configuration. For Python changes, at minimum run syntax checks:

```bash
python -m py_compile app.py gym_service.py init_env.py scripts/run_daemon.py scripts/run_linux_daemon.py demo_code.py
```

If you change runtime behavior, also smoke-test the relevant path manually where practical. Be aware that starting `app.py`, hitting `/api/poll`, or calling `fetch_gym_status()` can make outbound HTTP requests to the configured upstream API. QQ notification code can make outbound HTTP requests to the configured bot endpoint when enabled and a qualifying event occurs.

## API Surface

Primary Flask endpoints in `app.py`:

- `GET /` — dashboard page.
- `GET /api/bootstrap` — config plus dashboard data for first paint.
- `GET /api/config` — current config.
- `POST /api/config` — update mutable config values and restart the scheduler.
- `GET /api/data` — dashboard summary only.
- `POST /api/poll` — trigger one background poll.
- `GET /api/favorites` — list favorite member IDs.
- `POST /api/favorites` — add or remove a favorite.
- `GET /api/health` — basic service status.

When changing endpoints, update `static/js/dashboard.js`, `README.md`, and any related config normalization together.

## Configuration Notes

- Defaults live in `gym_service.DEFAULT_CONFIG`.
- `ConfigManager.load()` creates `config.json` if it is missing.
- `ConfigManager.save()` normalizes config and writes atomically through a temporary file.
- If you add config fields, update:
  - `DEFAULT_CONFIG`
  - `ConfigManager` normalization where needed
  - `app.py` config update handling if the value is editable through the API
  - `templates/index.html` and `static/js/dashboard.js` if exposed in the UI
  - `README.md`

## Data Model Notes

Snapshots are appended as one JSON object per line to `<storage_dir>/gym_data.jsonl`. Typical fields:

- `timestamp` — local timestamp string, usually `%Y-%m-%d %H:%M:%S`.
- `people_num` — current occupancy count.
- `using_man` — list of current member objects from the upstream API.
- `raw` — raw upstream payload.

`DataStore` caches parsed entries and summaries using file size and mtime. If you change append/load behavior, preserve cache invalidation and avoid full-file rewrites of user data.

## Coding Conventions

- Keep Python compatible with Python 3.10+ and preserve existing type-hint style.
- Prefer small, focused functions and standard-library solutions unless an existing dependency already covers the need.
- Keep Flask route responses JSON-serializable and stable for the dashboard.
- Preserve the vanilla JavaScript approach in `static/js/dashboard.js`; do not introduce frontend build tooling unless explicitly requested.
- Avoid broad reformatting. Match the surrounding style and indentation.
- Do not hard-code secrets, QQ tokens, user IDs, or environment-specific paths.

## Operational Cautions

- Importing `app.py` currently creates the Flask app and starts runtime scheduling via `ensure_runtime_started()`. Prefer importing `gym_service.py` for isolated service-layer checks.
- `do_poll()` skips polling outside configured open hours but performs an upstream request during open hours.
- Notification dispatch is server-side and may call external OneBot-compatible endpoints. Tests or smoke checks should disable QQ notifications unless explicitly testing them.
- The daemon helper writes `.checkmygym.pid` and logs to `logs/checkmygym.log`; avoid committing those files.

## Documentation Updates

Whenever behavior changes, update `README.md` with user-facing setup, configuration, endpoint, or notification changes. Keep this file updated when agent-specific workflow or repository conventions change.
