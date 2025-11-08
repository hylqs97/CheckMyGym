from __future__ import annotations

import os
import threading
from flask import Flask, jsonify, render_template, request, current_app, has_app_context
from apscheduler.schedulers.background import BackgroundScheduler

from gym_service import ConfigManager, DataStore, fetch_gym_status


scheduler: BackgroundScheduler | None = None
store: DataStore | None = None
config_mgr = ConfigManager()


def create_app() -> Flask:
    app = Flask(__name__)

    cfg = config_mgr.load()
    global store
    store = DataStore(cfg["storage_dir"])

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.get("/api/config")
    def get_config():
        return jsonify(config_mgr.load())

    @app.post("/api/config")
    def update_config():
        payload = request.get_json(force=True, silent=True) or {}
        cfg = config_mgr.load().copy()
        changed = False
        for key in ("storage_dir", "poll_interval_minutes", "shop_id", "api_base"):
            if key in payload and payload[key] != cfg.get(key):
                cfg[key] = payload[key]
                changed = True
        if changed:
            config_mgr.save(cfg)
            # Update datastore if storage changes
            global store
            store = DataStore(cfg["storage_dir"])  # recreate
            # reschedule job
            restart_scheduler(cfg)
        return jsonify({"ok": True, "config": cfg})

    @app.get("/api/data")
    def api_data():
        entries = store.load_all(limit=2000) if store else []
        summary = DataStore.summarize(entries)
        return jsonify(summary)

    @app.post("/api/poll")
    def api_poll():
        # trigger one poll in a background thread to avoid blocking
        threading.Thread(target=do_poll, daemon=True).start()
        return jsonify({"ok": True})

    return app


def do_poll() -> None:
    cfg = config_mgr.load()
    try:
        entry = fetch_gym_status(cfg["api_base"], int(cfg["shop_id"]))
        if store:
            store.append(entry)
    except Exception as e:
        # Log to console; in production, use proper logging
        print(f"Poll error: {e}")


def start_scheduler(app: Flask) -> None:
    global scheduler
    if scheduler and scheduler.running:
        return
    cfg = config_mgr.load()
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(do_poll, "interval", minutes=int(cfg["poll_interval_minutes"]), id="poll_job", replace_existing=True)
    scheduler.start()
    # first immediate poll
    with app.app_context():
        threading.Thread(target=do_poll, daemon=True).start()


def restart_scheduler(cfg: dict) -> None:
    global scheduler
    if scheduler:
        try:
            scheduler.remove_all_jobs()
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        scheduler = None
    # Start again with new interval
    app = current_app if has_app_context() else None
    if app is not None:
        start_scheduler(app)


def ensure_templates():
    # Make sure templates path exists when running from this repo structure
    templates_path = os.path.join(os.path.dirname(__file__), "templates")
    if not os.path.isdir(templates_path):
        os.makedirs(templates_path, exist_ok=True)


app = create_app()
start_scheduler(app)


if __name__ == "__main__":
    ensure_templates()
    app.run(host="0.0.0.0", port=8000, debug=True)
