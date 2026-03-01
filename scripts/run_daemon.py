#!/usr/bin/env python3
"""CheckMyGym background management script for Windows / Linux."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gym_service import ConfigManager, DataStore  # noqa: E402

PID_FILE = ROOT / ".checkmygym.pid"
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "checkmygym.log"
CONFIG_FILE = ROOT / "config.json"


def _is_windows() -> bool:
    return os.name == "nt"


def _is_running(pid: int) -> bool:
    if pid <= 0:
        return False

    if _is_windows():
        # `tasklist` is more reliable than OpenProcess for stale/reused PIDs.
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return f'"{pid}"' in (result.stdout or "")

    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _load_runtime_config() -> dict:
    try:
        return ConfigManager(str(CONFIG_FILE)).load().copy()
    except Exception:
        return {"host": "dual", "port": 6767}


def _get_process_command(pid: int) -> str:
    if _is_windows():
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    f'$p = Get-CimInstance Win32_Process -Filter "ProcessId = {pid}" '
                    '-ErrorAction SilentlyContinue; if ($p) { [Console]::Out.Write($p.CommandLine) }'
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return (result.stdout or "").strip()

    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if proc_cmdline.exists():
        try:
            raw = proc_cmdline.read_bytes().replace(b"\x00", b" ").strip()
            if raw:
                return raw.decode("utf-8", errors="replace")
        except OSError:
            pass

    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout or "").strip()


def _is_checkmygym_process(pid: int) -> bool:
    command = _get_process_command(pid).lower()
    if not command:
        return False

    app_path = str(ROOT / "app.py").lower()
    root_path = str(ROOT).lower()
    return app_path in command or ("app.py" in command and root_path in command)


def _iter_probe_urls(host: str, port: int) -> list[str]:
    normalized = (host or "dual").strip().lower()
    urls: list[str] = []

    def add(url: str) -> None:
        if url not in urls:
            urls.append(url)

    if normalized in {"", "dual"}:
        add(f"http://127.0.0.1:{port}/")
        add(f"http://[::1]:{port}/")
    elif normalized == "0.0.0.0":
        add(f"http://127.0.0.1:{port}/")
    elif normalized == "::":
        add(f"http://[::1]:{port}/")
    elif ":" in normalized and not normalized.startswith("["):
        add(f"http://[{host}]:{port}/")
    else:
        add(f"http://{host}:{port}/")

    return urls


def _is_service_reachable(cfg: dict | None = None) -> bool:
    cfg = cfg or _load_runtime_config()
    port = int(cfg.get("port", 6767))
    host = str(cfg.get("host", "dual"))

    for base_url in _iter_probe_urls(host, port):
        url = base_url.rstrip("/") + "/api/config"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status != 200:
                    continue
                body = response.read(4096)
                if b'"shop_id"' in body and b'"open_hour_start"' in body:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue

    return False


def _prompt_str(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def _prompt_int(label: str, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("Please enter an integer.")
            continue
        if min_value is not None and value < min_value:
            print(f"Please enter a value greater than or equal to {min_value}.")
            continue
        if max_value is not None and value > max_value:
            print(f"Please enter a value less than or equal to {max_value}.")
            continue
        return value


def configure(
    use_defaults: bool = False,
    init_port: int | None = None,
    init_host: str | None = None,
) -> dict:
    is_first_run = not CONFIG_FILE.exists()
    cfg_mgr = ConfigManager(str(CONFIG_FILE))
    cfg = cfg_mgr.load().copy()

    if is_first_run and init_port is not None:
        cfg["port"] = init_port
        print(f"First run: initialized port from CLI to {init_port}.")
    elif (not is_first_run) and (init_port is not None):
        print("config.json already exists; ignoring --port. Edit config.json if you want to change the port.")

    if init_host is not None:
        cfg["host"] = init_host.strip() or "dual"
        print(f"Using bind host from CLI: {cfg['host']}")

    if not use_defaults:
        print("\nEnter values or press Enter to keep the current setting:")
        cfg["storage_dir"] = _prompt_str("Storage directory", str(cfg["storage_dir"]))
        cfg["poll_interval_minutes"] = _prompt_int(
            "Polling interval (minutes)",
            int(cfg["poll_interval_minutes"]),
            min_value=1,
        )
        cfg["shop_id"] = _prompt_int("Shop ID", int(cfg["shop_id"]), min_value=1)
        cfg["api_base"] = _prompt_str("API base URL", str(cfg["api_base"]))
        cfg["open_hour_start"] = _prompt_int("Opening hour start (0-23)", int(cfg.get("open_hour_start", 6)), 0, 23)
        cfg["open_hour_end"] = _prompt_int("Opening hour end (0-23)", int(cfg.get("open_hour_end", 23)), 0, 23)
        cfg["host"] = _prompt_str("Bind host (dual/0.0.0.0/::/127.0.0.1)", str(cfg.get("host", "dual")))
    else:
        print("Using existing config and skipping interactive prompts.")

    if cfg["open_hour_start"] == cfg["open_hour_end"]:
        cfg["open_hour_end"] = (cfg["open_hour_start"] + 1) % 24
        print(f"Opening and closing hours cannot be the same; adjusted closing hour to {cfg['open_hour_end']}.")

    cfg_mgr.save(cfg)
    DataStore(cfg["storage_dir"])
    return cfg


def _build_popen_kwargs(log):
    kwargs = {
        "cwd": str(ROOT),
        "stdout": log,
        "stderr": log,
        "env": {**os.environ, "FLASK_DEBUG": "0"},
    }
    if _is_windows():
        creationflags = 0
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if creationflags:
            kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    return kwargs


def start(use_defaults: bool = False, port: int | None = None, host: str | None = None) -> None:
    current_cfg = _load_runtime_config()
    pid = _read_pid()

    if pid:
        if _is_running(pid):
            if _is_checkmygym_process(pid) or _is_service_reachable(current_cfg):
                print(f"CheckMyGym is already running, PID={pid}.")
                return
            print("Found a stale or unrelated PID file. Cleaning it up before starting.")
            PID_FILE.unlink(missing_ok=True)
        else:
            print("Found a stale PID file. Cleaning it up before starting.")
            PID_FILE.unlink(missing_ok=True)
    elif _is_service_reachable(current_cfg):
        print("CheckMyGym is responding on the configured port, but the PID file is missing. Refusing to start a duplicate instance.")
        return

    cfg = configure(use_defaults=use_defaults, init_port=port, init_host=host)
    LOG_DIR.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, str(ROOT / "app.py")], **_build_popen_kwargs(log))
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    print(
        f"CheckMyGym started in background, PID={process.pid}, host={cfg.get('host', 'dual')}, port={cfg.get('port', 6767)}"
    )
    print(f"Log file: {LOG_FILE}")


def _stop_windows_process_tree(pid: int) -> bool:
    result = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return True
    if not _is_running(pid):
        return False
    output = (result.stdout or "") + (result.stderr or "")
    raise RuntimeError(output.strip() or f"taskkill failed with code {result.returncode}")


def _stop_posix_process_group(pid: int) -> bool:
    try:
        os.killpg(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        raise
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except ProcessLookupError:
            return False


def stop() -> None:
    pid = _read_pid()
    if not pid:
        if _is_service_reachable():
            print("CheckMyGym is responding, but the PID file is missing. Stop it manually if needed.")
        else:
            print("PID file not found; CheckMyGym may not be running.")
        return
    if not _is_running(pid):
        print("PID is not running. Cleaning up the stale PID file.")
        PID_FILE.unlink(missing_ok=True)
        return
    if not _is_checkmygym_process(pid):
        print("PID file points to a different process. Cleaning the PID file without killing anything.")
        PID_FILE.unlink(missing_ok=True)
        return

    try:
        stopped = _stop_windows_process_tree(pid) if _is_windows() else _stop_posix_process_group(pid)
    except Exception as exc:
        print(f"Failed to stop CheckMyGym: {exc}")
        sys.exit(1)

    PID_FILE.unlink(missing_ok=True)
    if stopped:
        print(f"Stopped CheckMyGym (PID={pid}).")
    else:
        print("Process was already gone; cleaned the PID file.")


def status() -> None:
    cfg = _load_runtime_config()
    pid = _read_pid()

    if pid and _is_running(pid) and _is_checkmygym_process(pid):
        print(f"CheckMyGym is running, PID={pid}.")
        return

    if _is_service_reachable(cfg):
        if pid:
            print("CheckMyGym is responding, but the PID file does not match the current process.")
        else:
            print("CheckMyGym is responding, but the PID file is missing.")
        return

    if pid:
        print("PID file exists, but the process is not running. Run `stop` to clean it up.")
    else:
        print("CheckMyGym is not running.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CheckMyGym background management script (Windows/Linux)")
    parser.add_argument("action", nargs="?", default="start", choices=["start", "stop", "status"])
    parser.add_argument(
        "--use-defaults",
        action="store_true",
        help="Skip interactive prompts and use the existing config",
    )
    parser.add_argument("--port", type=int, default=None, help="Port for first run initialization (default: 6767)")
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Bind host: dual / 0.0.0.0 / :: / 127.0.0.1",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.port is not None and not (1 <= args.port <= 65535):
        print("--port must be between 1 and 65535.")
        sys.exit(1)
    if args.host is not None and not args.host.strip():
        print("--host cannot be empty.")
        sys.exit(1)

    if args.action == "start":
        start(use_defaults=args.use_defaults, port=args.port, host=args.host)
    elif args.action == "stop":
        stop()
    elif args.action == "status":
        status()


if __name__ == "__main__":
    main()
