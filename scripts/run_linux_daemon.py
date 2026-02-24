#!/usr/bin/env python3
"""在 Linux 下通过交互式命令配置并后台启动 CheckMyGym。"""

from __future__ import annotations

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


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
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


def configure() -> dict:
    cfg_mgr = ConfigManager(str(ROOT / "config.json"))
    cfg = cfg_mgr.load().copy()

    print("\n请按提示输入参数（回车可使用当前值）：")
    cfg["storage_dir"] = _prompt_str("数据存储目录", str(cfg["storage_dir"]))
    cfg["poll_interval_minutes"] = _prompt_int("轮询间隔（分钟）", int(cfg["poll_interval_minutes"]), min_value=1)
    cfg["shop_id"] = _prompt_int("门店 ID", int(cfg["shop_id"]), min_value=1)
    cfg["api_base"] = _prompt_str("API 基地址", str(cfg["api_base"]))
    cfg["open_hour_start"] = _prompt_int("开始营业小时(0-23)", int(cfg.get("open_hour_start", 6)), 0, 23)
    cfg["open_hour_end"] = _prompt_int("结束营业小时(0-23)", int(cfg.get("open_hour_end", 23)), 0, 23)

    if cfg["open_hour_start"] == cfg["open_hour_end"]:
        cfg["open_hour_end"] = (cfg["open_hour_start"] + 1) % 24
        print(f"开始/结束小时不能相同，已自动设置结束小时为 {cfg['open_hour_end']}。")

    cfg_mgr.save(cfg)
    DataStore(cfg["storage_dir"])
    return cfg


def start() -> None:
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"CheckMyGym 已在后台运行，PID={pid}。")
        return

    configure()
    LOG_DIR.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "app.py")],
            cwd=str(ROOT),
            stdout=log,
            stderr=log,
            preexec_fn=os.setsid,
            env={**os.environ, "FLASK_DEBUG": "0"},
        )
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    print(f"✅ 已后台启动 CheckMyGym，PID={process.pid}")
    print(f"日志文件：{LOG_FILE}")


def stop() -> None:
    pid = _read_pid()
    if not pid:
        print("未找到 PID 文件，服务可能未启动。")
        return
    if not _is_running(pid):
        print("PID 不存在，清理旧 PID 文件。")
        PID_FILE.unlink(missing_ok=True)
        return

    os.killpg(pid, signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    print(f"✅ 已停止 CheckMyGym（PID={pid}）。")


def status() -> None:
    pid = _read_pid()
    if not pid:
        print("CheckMyGym 未运行。")
        return
    if _is_running(pid):
        print(f"CheckMyGym 正在运行，PID={pid}。")
    else:
        print("PID 文件存在但进程不在运行，建议执行 stop 清理。")


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action == "start":
        start()
    elif action == "stop":
        stop()
    elif action == "status":
        status()
    else:
        print("用法: python scripts/run_linux_daemon.py [start|stop|status]")
        sys.exit(1)


if __name__ == "__main__":
    main()
