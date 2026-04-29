from __future__ import annotations

from copy import deepcopy
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, make_response, render_template, request
from werkzeug.serving import make_server

from gym_service import ConfigManager, DataStore, QQNotificationManager, fetch_gym_status

LOGGER = logging.getLogger("checkmygym")
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

APP_DATA_LIMIT = 2000
scheduler: BackgroundScheduler | None = None
store: DataStore | None = None
config_mgr = ConfigManager()
notification_mgr = QQNotificationManager()
_runtime_lock = threading.Lock()
_runtime_started = False


def get_favorite_ids() -> set[str]:
    cfg = config_mgr.load()
    return {str(value) for value in cfg.get("favorites", []) if str(value).strip()}


def save_favorite_ids(favorites: set[str]) -> None:
    cfg = deepcopy(config_mgr.load())
    cfg["favorites"] = sorted({str(value) for value in favorites if str(value).strip()})
    config_mgr.save(cfg)


def is_within_hours(cfg: dict[str, Any], now: datetime | None = None) -> bool:
    now = now or datetime.now()
    start = int(cfg.get("open_hour_start", 6))
    end = int(cfg.get("open_hour_end", 23))
    hour = now.hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def _get_store() -> DataStore:
    global store
    if store is None:
        cfg = config_mgr.load()
        store = DataStore(str(cfg["storage_dir"]))
    return store


def build_dashboard_payload(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or config_mgr.load()
    payload = _get_store().build_dashboard_payload(get_favorite_ids(), limit=APP_DATA_LIMIT, per_user_limit=5)
    payload["open_hours"] = {
        "start": int(cfg.get("open_hour_start", 6)),
        "end": int(cfg.get("open_hour_end", 23)),
    }
    return payload


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        response = make_response(render_template("index.html"))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/api/bootstrap")
    def api_bootstrap():
        cfg = config_mgr.load()
        return jsonify({"config": cfg, "data": build_dashboard_payload(cfg)})

    @app.get("/api/config")
    def api_get_config():
        return jsonify(config_mgr.load())

    @app.post("/api/config")
    def api_update_config():
        payload = request.get_json(force=True, silent=True) or {}
        cfg = deepcopy(config_mgr.load())
        changed = False

        for key in ("storage_dir", "poll_interval_minutes", "shop_id", "api_base", "open_hour_start", "open_hour_end"):
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

        if "qq_notification" in payload and isinstance(payload.get("qq_notification"), dict):
            if payload["qq_notification"] != cfg.get("qq_notification"):
                cfg["qq_notification"] = payload["qq_notification"]
                changed = True

        if cfg.get("open_hour_start", 6) == cfg.get("open_hour_end", 23):
            adjusted_end = (int(cfg["open_hour_start"]) + 1) % 24
            if adjusted_end != cfg.get("open_hour_end"):
                cfg["open_hour_end"] = adjusted_end
                changed = True

        if changed:
            config_mgr.save(cfg)
            global store
            store = DataStore(str(cfg["storage_dir"]))
            restart_scheduler()
            cfg = config_mgr.load()

        return jsonify({"ok": True, "config": cfg})

    @app.get("/api/data")
    def api_data():
        cfg = config_mgr.load()
        return jsonify(build_dashboard_payload(cfg))

    @app.post("/api/poll")
    def api_poll():
        threading.Thread(target=do_poll, daemon=True, name="manual-poll").start()
        return jsonify({"ok": True})

    @app.get("/api/favorites")
    def api_get_favorites():
        return jsonify({"favorites": sorted(get_favorite_ids())})

    @app.post("/api/favorites")
    def api_update_favorite():
        payload = request.get_json(force=True, silent=True) or {}
        user_id = str(payload.get("id") or "").strip()
        if not user_id:
            return jsonify({"ok": False, "error": "missing id"}), 400

        favorites = get_favorite_ids()
        if bool(payload.get("favorite")):
            favorites.add(user_id)
        else:
            favorites.discard(user_id)
        save_favorite_ids(favorites)
        return jsonify({"ok": True, "favorites": sorted(favorites)})

    @app.get("/api/health")
    def api_health():
        cfg = config_mgr.load()
        return jsonify(
            {
                "ok": True,
                "scheduler_running": bool(scheduler and scheduler.running),
                "port": int(cfg.get("port", 6767)),
                "host": str(cfg.get("host", "dual")),
            }
        )

    return app


def do_poll() -> None:
    cfg = config_mgr.load()
    if not is_within_hours(cfg):
        return

    try:
        previous_entries = _get_store().load_all(limit=1)
        previous_entry = previous_entries[-1] if previous_entries else None
        entry = fetch_gym_status(str(cfg["api_base"]), int(cfg["shop_id"]))
        _get_store().append(entry)
        try:
            notification_mgr.handle_snapshot(cfg, previous_entry, entry)
        except Exception:
            LOGGER.exception("QQ notification dispatch failed")
    except Exception:
        LOGGER.exception("Polling failed")


def start_scheduler() -> None:
    global scheduler
    if scheduler and scheduler.running:
        return

    cfg = config_mgr.load()
    interval = max(1, int(cfg.get("poll_interval_minutes", 5)))
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        do_poll,
        "interval",
        minutes=interval,
        id="poll_job",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=30,
    )
    scheduler.start()
    threading.Thread(target=do_poll, daemon=True, name="initial-poll").start()


def restart_scheduler() -> None:
    global scheduler
    if scheduler:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            LOGGER.exception("Failed to stop scheduler cleanly")
        scheduler = None
    start_scheduler()


def ensure_runtime_started() -> None:
    global _runtime_started
    if _runtime_started:
        return

    with _runtime_lock:
        if _runtime_started:
            return
        _get_store()
        start_scheduler()
        _runtime_started = True


def _normalize_host(value: str | None) -> str:
    host = (value or "").strip()
    if not host:
        return "dual"
    if host.lower() in {"dual", "both"}:
        return "dual"
    return host


def _run_dual_stack(app: Flask, port: int) -> None:
    servers: list[tuple[str, Any]] = []
    bind_errors: list[str] = []

    for bind_host in ("::", "0.0.0.0"):
        try:
            server = make_server(bind_host, port, app, threaded=True)
            servers.append((bind_host, server))
        except OSError as exc:
            bind_errors.append(f"{bind_host}:{port} -> {exc}")

    if not servers:
        details = "; ".join(bind_errors) if bind_errors else "unknown bind error"
        raise RuntimeError(f"Failed to bind any listener on port {port}: {details}")

    for bind_host, server in servers:
        threading.Thread(target=server.serve_forever, daemon=True, name=f"http-{bind_host}-{port}").start()
        if ":" in bind_host:
            LOGGER.info("Listening on http://[%s]:%s", bind_host, port)
        else:
            LOGGER.info("Listening on http://%s:%s", bind_host, port)

    if bind_errors:
        LOGGER.warning("Bind warnings: %s", " | ".join(bind_errors))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for _, server in servers:
            try:
                server.shutdown()
            except Exception:
                LOGGER.exception("Failed to shut down listener cleanly")


def run_http_server(app: Flask, host: str, port: int, debug_mode: bool) -> None:
    if host == "dual":
        if debug_mode:
            LOGGER.info("FLASK_DEBUG=1 with dual mode disables the Flask reloader.")
        _run_dual_stack(app, port)
        return
    app.run(host=host, port=port, debug=debug_mode)


app = create_app()
ensure_runtime_started()


if __name__ == "__main__":
    cfg = config_mgr.load()
    host = _normalize_host(os.getenv("CHECKMYGYM_HOST") or str(cfg.get("host", "dual")))
    port = int(os.getenv("CHECKMYGYM_PORT") or cfg.get("port", 6767))
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    run_http_server(app, host=host, port=port, debug_mode=debug_mode)
