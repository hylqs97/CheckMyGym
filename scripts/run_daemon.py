#!/usr/bin/env python3
"""CheckMyGym 后台管理脚本（Windows / Linux）。"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
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
    if _is_windows():
        # os.kill(pid, 0) is unreliable on some Windows Python builds. Use WinAPI instead.
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return False

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            # Access denied usually means the process exists but is owned by another user/session.
            if err == 5:
                return True
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
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
            print("请输入整数。")
            continue
        if min_value is not None and value < min_value:
            print(f"请输入不小于 {min_value} 的数字。")
            continue
        if max_value is not None and value > max_value:
            print(f"请输入不大于 {max_value} 的数字。")
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
        print(f"首次运行：使用命令行端口 {init_port} 初始化配置。")
    elif (not is_first_run) and (init_port is not None):
        print("检测到 config.json 已存在，--port 参数将被忽略；如需改端口请手动编辑 config.json。")

    if init_host is not None:
        cfg["host"] = init_host.strip() or "dual"
        print(f"Using bind host from CLI: {cfg['host']}")

    if not use_defaults:
        print("\n请按提示输入参数（回车可使用当前值）：")
        cfg["storage_dir"] = _prompt_str("数据存储目录", str(cfg["storage_dir"]))
        cfg["poll_interval_minutes"] = _prompt_int("轮询间隔（分钟）", int(cfg["poll_interval_minutes"]), min_value=1)
        cfg["shop_id"] = _prompt_int("门店 ID", int(cfg["shop_id"]), min_value=1)
        cfg["api_base"] = _prompt_str("API 基地址", str(cfg["api_base"]))
        cfg["open_hour_start"] = _prompt_int("开始营业小时(0-23)", int(cfg.get("open_hour_start", 6)), 0, 23)
        cfg["open_hour_end"] = _prompt_int("结束营业小时(0-23)", int(cfg.get("open_hour_end", 23)), 0, 23)
        cfg["host"] = _prompt_str("Bind host (dual/0.0.0.0/::/127.0.0.1)", str(cfg.get("host", "dual")))
    else:
        print("使用已有配置直接启动（跳过交互输入）。")

    if cfg["open_hour_start"] == cfg["open_hour_end"]:
        cfg["open_hour_end"] = (cfg["open_hour_start"] + 1) % 24
        print(f"开始/结束小时不能相同，已自动设置结束小时为 {cfg['open_hour_end']}。")

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
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"CheckMyGym 已在后台运行，PID={pid}。")
        return

    cfg = configure(use_defaults=use_defaults, init_port=port, init_host=host)
    LOG_DIR.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, str(ROOT / "app.py")], **_build_popen_kwargs(log))
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    print(
        f"CheckMyGym started in background, PID={process.pid}, host={cfg.get('host', 'dual')}, port={cfg.get('port', 6767)}"
    )
    print(f"日志文件：{LOG_FILE}")


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
        print("未找到 PID 文件，服务可能未启动。")
        return
    if not _is_running(pid):
        print("PID 不存在，清理旧 PID 文件。")
        PID_FILE.unlink(missing_ok=True)
        return

    try:
        stopped = _stop_windows_process_tree(pid) if _is_windows() else _stop_posix_process_group(pid)
    except Exception as exc:
        print(f"停止失败：{exc}")
        sys.exit(1)

    PID_FILE.unlink(missing_ok=True)
    if stopped:
        print(f"已停止 CheckMyGym（PID={pid}）。")
    else:
        print("进程已不存在，已清理 PID 文件。")


def status() -> None:
    pid = _read_pid()
    if not pid:
        print("CheckMyGym 未运行。")
        return
    if _is_running(pid):
        print(f"CheckMyGym 正在运行，PID={pid}。")
    else:
        print("PID 文件存在但进程不在运行，建议执行 stop 清理。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CheckMyGym 后台管理脚本（Windows/Linux）")
    parser.add_argument("action", nargs="?", default="start", choices=["start", "stop", "status"])
    parser.add_argument("--use-defaults", action="store_true", help="启动时跳过交互提问，直接使用已有配置")
    parser.add_argument("--port", type=int, default=None, help="首次运行时设置端口，默认 6767")
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
        print("--port 必须在 1 到 65535 之间")
        sys.exit(1)
    if args.host is not None and not args.host.strip():
        print("--host cannot be empty")
        sys.exit(1)
    if args.action == "start":
        start(use_defaults=args.use_defaults, port=args.port, host=args.host)
    elif args.action == "stop":
        stop()
    elif args.action == "status":
        status()


if __name__ == "__main__":
    main()
