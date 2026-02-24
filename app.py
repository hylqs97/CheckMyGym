from __future__ import annotations

import os
import threading
from datetime import datetime

from flask import Flask, jsonify, render_template, request, current_app, has_app_context
from apscheduler.schedulers.background import BackgroundScheduler

from gym_service import ConfigManager, DataStore, fetch_gym_status


scheduler: BackgroundScheduler | None = None
store: DataStore | None = None
config_mgr = ConfigManager()


def get_favorite_ids() -> set[str]:
    cfg = config_mgr.load()
    favs = cfg.get("favorites") or []
    return {str(f) for f in favs if str(f)}


def save_favorite_ids(favs: set[str]) -> None:
    cfg = config_mgr.load().copy()
    cfg["favorites"] = sorted(list({str(f) for f in favs if str(f)}))
    config_mgr.save(cfg)


def is_within_hours(cfg: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    start = int(cfg.get("open_hour_start", 6))
    end = int(cfg.get("open_hour_end", 23))
    hour = now.hour
    if start <= end:
        return start <= hour < end
    # handle wrap-around (unlikely here but safe)
    return hour >= start or hour < end


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
        mutable_keys = (
            "storage_dir",
            "poll_interval_minutes",
            "shop_id",
            "api_base",
            "open_hour_start",
            "open_hour_end",
        )
        for key in mutable_keys:
            if key not in payload:
                continue
            value = payload[key]
            if key in {"poll_interval_minutes", "shop_id", "open_hour_start", "open_hour_end"}:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
                if key in {"open_hour_start", "open_hour_end"}:
                    value = max(0, min(23, value))
            if value != cfg.get(key):
                cfg[key] = value
                changed = True
        # ensure start < end default behavior
        if cfg.get("open_hour_start", 6) == cfg.get("open_hour_end", 23):
            cfg["open_hour_end"] = (cfg["open_hour_start"] + 1) % 24
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
        cfg = config_mgr.load()
        favorites = get_favorite_ids()
        summary = DataStore.summarize(entries)
        summary["favorites"] = sorted(list(favorites))
        summary["favorite_records"] = DataStore.summarize_favorite_records(entries, favorites, per_user_limit=5)
        for person in summary.get("current_people", []):
            pid = str(person.get("id") or "")
            person["favorite"] = pid in favorites
        summary["open_hours"] = {
            "start": int(cfg.get("open_hour_start", 6)),
            "end": int(cfg.get("open_hour_end", 23)),
        }
        return jsonify(summary)

    @app.post("/api/poll")
    def api_poll():
        # trigger one poll in a background thread to avoid blocking
        threading.Thread(target=do_poll, daemon=True).start()
        return jsonify({"ok": True})

    @app.get("/api/favorites")
    def api_get_favorites():
        return jsonify({"favorites": sorted(list(get_favorite_ids()))})

    @app.post("/api/favorites")
    def api_update_favorite():
        payload = request.get_json(force=True, silent=True) or {}
        user_id = payload.get("id")
        if not user_id:
            return jsonify({"ok": False, "error": "missing id"}), 400
        favorite = bool(payload.get("favorite"))
        favorites = get_favorite_ids()
        user_id = str(user_id)
        if favorite:
            favorites.add(user_id)
        else:
            favorites.discard(user_id)
        save_favorite_ids(favorites)
        return jsonify({"ok": True, "favorites": sorted(list(favorites))})

    return app


def do_poll() -> None:
    cfg = config_mgr.load()
    try:
        if not is_within_hours(cfg):
            return
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
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    cfg = config_mgr.load()
    port = int(cfg.get("port", 6767))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
