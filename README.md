这是一个用于「监控健身房实时人数、可视化趋势并存储数据」的项目。

## 功能概览
- Flask + React + Material UI + Chart.js 仪表盘，液态玻璃风格 UI。
- APScheduler 后台定时抓取，默认 5 分钟执行一次。
- 数据以 JSONL 形式存储在本地目录，可在界面随时切换存储路径、API、门店 ID 等。
- 支持 Linux 下一条命令交互式配置并后台运行。
- 支持 Windows 任务计划程序实现开机自启（可选）。

## Linux 新用户快速开始
### 1) 通过 Git 拉取代码
```bash
git clone https://github.com/<your-org>/CheckMyGym.git
cd CheckMyGym
```

### 2) 安装依赖（Python 3.10+）
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) 一条命令交互式配置并后台运行
```bash
python scripts/run_linux_daemon.py start
```
执行后会自动提示你输入（回车可使用默认值）：
- 数据存储目录（`storage_dir`）
- 轮询间隔（分钟）
- 门店 ID（`shop_id`）
- API 基地址（`api_base`）
- 开始/结束营业小时

脚本会自动：
- 写入或更新 `config.json`
- 确保存储目录存在
- 以后台进程启动 `python app.py`
- 输出 PID 和日志路径 `logs/checkmygym.log`

### 4) 常用管理命令
```bash
# 查看状态
python scripts/run_linux_daemon.py status

# 停止后台服务
python scripts/run_linux_daemon.py stop
```

### 5) 访问页面
启动成功后浏览器访问：
- `http://127.0.0.1:8000`
- 或 `http://<你的服务器IP>:8000`

## 图表 & 数据
- 实时曲线：最近一段时间的人数走向。
- 按星期平均：展示周一到周日的平均人数柱状图。
- 按小时平均：新增周一至周日切换标签，查看各小时平均人数。
- 当前在馆成员：展示头像/昵称/停留时长。
- 数据文件：`<storage_dir>/gym_data.jsonl`，每行结构：
  ```json
  {
    "timestamp": "2025-11-07 20:45:49",
    "people_num": 23,
    "using_man": [ ...原始用户列表... ]
  }
  ```

## 开机自启（可选）
1. 在 PowerShell（建议管理员）执行：`powershell -ExecutionPolicy Bypass -File scripts/setup_autorun.ps1`
   - 将注册任务 `CheckMyGym`，在用户登录后自动运行 `python app.py`。
2. 取消自启：`powershell -ExecutionPolicy Bypass -File scripts/remove_autorun.ps1`

## 其他说明
- `.gitignore` 已排除 `config.json`、`data/`、`logs/`、IDE 目录等敏感或无关文件，提交代码前确保未强制添加这些文件。
- 旧的 `demo_code.py` 仍可单独运行，用于写入 CSV，已改为使用项目内的 `data/gym_users_log.csv` 并自动创建目录。
- 若网络或 API 不可达，服务会在后台打印错误并继续下一轮调度，可自行接入 logging 或告警。
