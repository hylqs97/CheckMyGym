# CheckMyGym

用于采集健身房实时人数数据，并在本地提供可视化面板（Flask + React + Material UI + Chart.js）。

## 功能概览

- 后端定时拉取健身房人数数据（APScheduler）
- 前端展示实时人数、按星期平均、按小时平均
- 当前在馆成员列表与收藏
- 数据以 JSONL 形式落盘（默认 `data/gym_data.jsonl`）
- 支持 Windows / Linux 前台运行
- 提供统一后台管理脚本：`scripts/run_daemon.py`

## 环境要求

- Python 3.10+

## 快速开始（Windows / Linux 通用）

### 1) 克隆代码

```bash
git clone https://github.com/<your-org>/CheckMyGym.git
cd CheckMyGym
```

### 2) 创建虚拟环境并安装依赖

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3) 前台运行（最简单）

Linux/macOS:

```bash
python3 app.py
```

Windows:

```powershell
python app.py
```

启动后访问：

- `http://127.0.0.1:6767`
- 或 `http://<你的机器IP>:6767`
- ? `http://<????>:6767`??? `hylqs.dynv6.net:6767`?

首次运行会自动生成 `config.json` 和数据目录。

## 统一后台管理脚本（Windows / Linux）

项目提供跨平台后台管理脚本：`scripts/run_daemon.py`

### 首次启动（交互配置）

```bash
python scripts/run_daemon.py start
```

首次启动可指定端口（默认 `6767`）：

```bash
python scripts/run_daemon.py start --port 6767
```

?????????? `dual`?????? IPv4+IPv6??

```bash
python scripts/run_daemon.py start --host dual
```

脚本会提示你输入（回车使用当前值）：

- `storage_dir`
- `poll_interval_minutes`
- `shop_id`
- `api_base`
- `open_hour_start`
- `open_hour_end`
- `host`?`dual` / `0.0.0.0` / `::` / `127.0.0.1`?

### 按现有配置直接启动（跳过交互）

```bash
python scripts/run_daemon.py start --use-defaults
```

???????????

```bash
python scripts/run_daemon.py start --use-defaults --host dual
```

### 状态与停止

```bash
# 查看状态
python scripts/run_daemon.py status

# 停止后台进程
python scripts/run_daemon.py stop
```

### 运行产物

- PID 文件：`.checkmygym.pid`
- 日志文件：`logs/checkmygym.log`

## Windows 开机自启（任务计划）

项目提供 PowerShell 脚本注册“用户登录时启动”的任务计划：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_autorun.ps1 -PythonExe ".\.venv\Scripts\python.exe"
```

默认会注册为启动：

```text
python scripts/run_daemon.py start --use-defaults
```

移除任务计划：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\remove_autorun.ps1
```

说明：

- 请先至少运行一次 `scripts/run_daemon.py start` 完成配置。
- `-PythonExe` 建议显式传入虚拟环境解释器，避免命中系统 `python` alias。

## Linux 开机自启（systemd，可选）

`systemd` 应直接托管前台进程（`app.py`），不要再通过后台脚本二次 fork。

创建服务文件：

```bash
sudo tee /etc/systemd/system/checkmygym.service >/dev/null <<'EOF'
[Unit]
Description=CheckMyGym Service
After=network.target

[Service]
Type=simple
User=<你的Linux用户名>
WorkingDirectory=/path/to/CheckMyGym
Environment=FLASK_DEBUG=0
ExecStart=/path/to/CheckMyGym/.venv/bin/python /path/to/CheckMyGym/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable checkmygym
sudo systemctl start checkmygym
```

查看状态与日志：

```bash
sudo systemctl status checkmygym
journalctl -u checkmygym -f
```

关闭开机自启：

```bash
sudo systemctl disable --now checkmygym
```

## 数据文件说明

- 数据文件路径：`<storage_dir>/gym_data.jsonl`
- 每行一条 JSON 记录，例如：

```json
{
  "timestamp": "2025-11-07 20:45:49",
  "people_num": 23,
  "using_man": []
}
```

## 兼容说明

- 旧命令 `python scripts/run_linux_daemon.py ...` 仍可用（内部已转发到 `run_daemon.py`）。
