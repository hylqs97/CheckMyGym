这是一个用于「监控健身房实时人数、可视化趋势并存储数据」的项目。

## 功能概览
- Flask + React + Material UI + Chart.js 仪表盘，液态玻璃风格 UI。
- APScheduler 后台定时抓取，默认 5 分钟执行一次。
- 数据以 JSONL 形式存储在本地目录，可在界面随时切换存储路径、API、门店 ID 等。
- 支持 Windows 任务计划程序实现开机自启（可选）。

## 快速开始
1. 安装依赖（Python 3.10+）：`pip install -r requirements.txt`
2. 初始化配置与数据目录（自动创建 `config.json` 与 `data/`）：`python init_env.py`
   - 该脚本会调用 `ConfigManager` & `DataStore`，无配置文件和数据目录时会自动生成。
3. 启动服务：`python app.py`，浏览器访问 `http://localhost:8000`
4. 在页面右侧「配置」卡片中可以调整：
   - 数据存储目录（默认 `data`）
   - 轮询间隔（分钟）
   - 门店 ID（shop_id）
   - API 基地址
   保存后，后端会自动重启调度任务并使用新的设置。

> **提示**：直接运行 `python app.py` 也会在无配置文件时自动生成 `config.json`，但 `init_env.py` 方便在部署脚本或 CI 中单独初始化。

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
- `.gitignore` 已排除 `config.json`、`data/`、IDE 目录等敏感或无关文件，提交代码前确保未强制添加这些文件。
- 旧的 `demo_code.py` 仍可单独运行，用于写入 CSV，已改为使用项目内的 `data/gym_users_log.csv` 并自动创建目录。
- 若网络或 API 不可达，服务会在后台打印错误并继续下一轮调度，可自行接入 logging 或告警。
