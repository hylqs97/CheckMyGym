from __future__ import annotations

from copy import deepcopy
import json
import os
import threading
from datetime import datetime
from typing import Any

import requests

DEFAULT_CONFIG = {
    "storage_dir": "data",
    "poll_interval_minutes": 5,
    "shop_id": 218,
    "api_base": "http://106.55.236.110:8999",
    "open_hour_start": 6,
    "open_hour_end": 23,
    "host": "dual",
    "port": 6767,
    "favorites": [],
    "qq_notification": {
        "enabled": False,
        "endpoint": "",
        "access_token": "",
        "target_type": "private",
        "target_id": "",
        "timeout_seconds": 10,
        "cooldown_minutes": 15,
        "low_traffic": {
            "enabled": False,
            "threshold": 4,
            "start_time": "00:00",
            "end_time": "00:00",
            "message_template": "健身房当前人数 {current_count}，已低于阈值 {threshold}。时间：{timestamp}",
        },
        "user_arrival_rules": [],
    },
}

_API_HEADERS = {
    "Host": "106.55.236.110:8999",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14; LE2100 Build/UKQ1.230924.001; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/137.0.7151.115 Mobile Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate",
    "Origin": "http://www.hehacat.com",
    "X-Requested-With": "com.hehacat",
    "Referer": "http://www.hehacat.com/",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,zh-TW;q=0.6",
}

_HTTP_LOCAL = threading.local()


class ConfigManager:
    def __init__(self, path: str = "config.json") -> None:
        self.path = path
        self._config: dict[str, Any] | None = None
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if self._config is not None:
                return self._config

            if not os.path.exists(self.path):
                self._config = deepcopy(DEFAULT_CONFIG)
                self.save(self._config)
                return self._config

            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)

            merged = deepcopy(DEFAULT_CONFIG)
            merged.update(data or {})
            self._normalize_config(merged)
            self._ensure_storage_dir(merged)
            self._config = merged
            return self._config

    def save(self, cfg: dict[str, Any]) -> None:
        with self._lock:
            normalized = deepcopy(DEFAULT_CONFIG)
            normalized.update(cfg or {})
            self._normalize_config(normalized)
            self._ensure_storage_dir(normalized)

            config_dir = os.path.dirname(os.path.abspath(self.path))
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)

            temp_path = f"{self.path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(normalized, handle, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.path)
            self._config = normalized

    @classmethod
    def _normalize_config(cls, cfg: dict[str, Any]) -> None:
        cfg["favorites"] = cls._normalize_favorites(cfg.get("favorites"))
        cfg["qq_notification"] = cls._normalize_qq_notification(cfg.get("qq_notification"))

    @staticmethod
    def _normalize_favorites(values: Any) -> list[str]:
        if not values:
            return []
        return sorted({str(value) for value in values if str(value).strip()})

    @classmethod
    def _normalize_qq_notification(cls, values: Any) -> dict[str, Any]:
        normalized = deepcopy(DEFAULT_CONFIG["qq_notification"])
        if isinstance(values, dict):
            normalized.update(values)

        low_traffic = deepcopy(DEFAULT_CONFIG["qq_notification"]["low_traffic"])
        if isinstance(normalized.get("low_traffic"), dict):
            low_traffic.update(normalized["low_traffic"])

        normalized["enabled"] = bool(normalized.get("enabled"))
        normalized["endpoint"] = str(normalized.get("endpoint") or "").strip()
        normalized["access_token"] = str(normalized.get("access_token") or "").strip()
        normalized["target_type"] = cls._normalize_target_type(normalized.get("target_type"))
        normalized["target_id"] = str(normalized.get("target_id") or "").strip()
        normalized["timeout_seconds"] = cls._clamp_int(normalized.get("timeout_seconds"), 10, 3, 60)
        normalized["cooldown_minutes"] = cls._clamp_int(normalized.get("cooldown_minutes"), 15, 0, 24 * 60)

        low_traffic["enabled"] = bool(low_traffic.get("enabled"))
        low_traffic["threshold"] = max(0, cls._clamp_int(low_traffic.get("threshold"), 4, 0, 9999))
        low_traffic["start_time"] = _normalize_time_text(
            low_traffic.get("start_time"),
            fallback="00:00",
            legacy_hour=low_traffic.get("start_hour"),
        )
        low_traffic["end_time"] = _normalize_time_text(
            low_traffic.get("end_time"),
            fallback="00:00",
            legacy_hour=low_traffic.get("end_hour"),
        )
        low_traffic["message_template"] = (
            str(low_traffic.get("message_template") or "").strip()
            or DEFAULT_CONFIG["qq_notification"]["low_traffic"]["message_template"]
        )
        low_traffic["message_template"] = cls._repair_message_template(low_traffic["message_template"], "low_traffic")
        normalized["low_traffic"] = low_traffic

        rules: list[dict[str, Any]] = []
        for raw_rule in normalized.get("user_arrival_rules") or []:
            if not isinstance(raw_rule, dict):
                continue
            user_ids = _normalize_user_id_list(raw_rule.get("user_ids") or raw_rule.get("user_id"))
            if not user_ids:
                continue
            user_id_text = ", ".join(user_ids)
            rules.append(
                {
                    "user_id": user_id_text,
                    "user_ids": user_ids,
                    "label": str(raw_rule.get("label") or "").strip(),
                    "enabled": bool(raw_rule.get("enabled", True)),
                    "require_low_traffic": bool(raw_rule.get("require_low_traffic", False)),
                    "message_template": str(raw_rule.get("message_template") or "").strip()
                    or "用户 {user_id} 来健身房了，当前人数 {current_count}。时间：{timestamp}",
                }
            )
            rules[-1]["message_template"] = cls._repair_message_template(
                rules[-1]["message_template"],
                "arrival",
                user_id=user_id_text,
            )
        normalized["user_arrival_rules"] = rules
        return normalized

    @staticmethod
    def _repair_message_template(template: str, template_kind: str, user_id: str = "") -> str:
        cleaned = str(template or "").strip()
        low_traffic_default = "健身房当前人数 {current_count}，已低于阈值 {threshold}。时间：{timestamp}"
        arrival_default = "用户 {user_id} 来健身房了，当前人数 {current_count}。时间：{timestamp}"

        broken_markers = ("????", "???", "鍋ヨ韩", "鏉ュ仴", "褰撳墠", "鏃堕棿", "锛", "銆")
        if not cleaned or any(marker in cleaned for marker in broken_markers):
            return low_traffic_default if template_kind == "low_traffic" else arrival_default
        return cleaned

    @staticmethod
    def _normalize_target_type(value: Any) -> str:
        target_type = str(value or "").strip().lower()
        if target_type not in {"private", "group"}:
            return "private"
        return target_type

    @staticmethod
    def _clamp_int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return fallback
        return max(minimum, min(maximum, number))

    @staticmethod
    def _ensure_storage_dir(cfg: dict[str, Any]) -> None:
        storage_dir = cfg.get("storage_dir") or DEFAULT_CONFIG["storage_dir"]
        cfg["storage_dir"] = storage_dir
        os.makedirs(storage_dir, exist_ok=True)


class DataStore:
    def __init__(self, storage_dir: str) -> None:
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.data_file = os.path.join(self.storage_dir, "gym_data.jsonl")
        self._lock = threading.RLock()
        self._entries_cache: list[dict[str, Any]] = []
        self._entries_signature: tuple[int, int] | None = None
        self._summary_cache: dict[int | None, tuple[tuple[int, int] | None, dict[str, Any]]] = {}

    def append(self, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with open(self.data_file, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
            self._entries_signature = None
            self._summary_cache.clear()

    def load_all(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._read_entries_locked())
        if limit is None:
            return entries
        return entries[-limit:]

    def get_base_summary(self, limit: int | None = None) -> dict[str, Any]:
        with self._lock:
            signature = self._file_signature()
            cached = self._summary_cache.get(limit)
            if cached and cached[0] == signature:
                return self._clone_summary(cached[1])

            entries = list(self._read_entries_locked())
            if limit is not None:
                entries = entries[-limit:]
            summary = self.summarize(entries)
            self._summary_cache[limit] = (signature, summary)
            return self._clone_summary(summary)

    def build_dashboard_payload(
        self,
        favorite_ids: set[str],
        limit: int = 2000,
        per_user_limit: int = 5,
    ) -> dict[str, Any]:
        entries = self.load_all(limit=limit)
        summary = self.get_base_summary(limit=limit)
        favorites = sorted({str(value) for value in favorite_ids if str(value).strip()})

        summary["favorites"] = favorites
        summary["favorite_records"] = self.summarize_favorite_records(entries, set(favorites), per_user_limit=per_user_limit)

        for person in summary.get("current_people", []):
            person_id = str(person.get("id") or "")
            person["favorite"] = person_id in favorite_ids

        return summary

    def _read_entries_locked(self) -> list[dict[str, Any]]:
        signature = self._file_signature()
        if signature == self._entries_signature:
            return self._entries_cache

        if not os.path.exists(self.data_file):
            self._entries_cache = []
            self._entries_signature = None
            return self._entries_cache

        items: list[dict[str, Any]] = []
        with open(self.data_file, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        self._entries_cache = items
        self._entries_signature = signature
        return self._entries_cache

    def _file_signature(self) -> tuple[int, int] | None:
        if not os.path.exists(self.data_file):
            return None
        stat = os.stat(self.data_file)
        return (int(stat.st_mtime_ns), int(stat.st_size))

    @staticmethod
    def _clone_summary(summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "series": [dict(item) for item in summary.get("series", [])],
            "weekday_avg": dict(summary.get("weekday_avg", {})),
            "hour_avg": dict(summary.get("hour_avg", {})),
            "current_people": [dict(item) for item in summary.get("current_people", [])],
            "last_timestamp": summary.get("last_timestamp"),
            "weekday_hour_avg": {
                str(day): dict(hours)
                for day, hours in (summary.get("weekday_hour_avg", {}) or {}).items()
            },
            "current_count": int(summary.get("current_count", 0)),
            "sample_count": int(summary.get("sample_count", 0)),
        }

    @staticmethod
    def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
        by_weekday: dict[int, list[int]] = {index: [] for index in range(7)}
        by_hour: dict[int, list[int]] = {index: [] for index in range(24)}
        hour_by_weekday: dict[int, dict[int, list[int]]] = {
            day: {hour: [] for hour in range(24)}
            for day in range(7)
        }

        series: list[dict[str, Any]] = []
        latest_entry = entries[-1] if entries else None

        for entry in entries:
            timestamp = entry.get("timestamp")
            people = _to_int(entry.get("people_num"), 0)
            parsed_time = _parse_timestamp(timestamp)
            if parsed_time is None:
                continue

            by_weekday[parsed_time.weekday()].append(people)
            by_hour[parsed_time.hour].append(people)
            hour_by_weekday[parsed_time.weekday()][parsed_time.hour].append(people)
            series.append({"t": timestamp, "people_num": people})

        weekday_avg = {str(day): _avg(values) for day, values in by_weekday.items()}
        hour_avg = {str(hour): _avg(values) for hour, values in by_hour.items()}

        current_people: list[dict[str, Any]] = []
        if latest_entry:
            for person in latest_entry.get("using_man", []) or []:
                current_people.append(
                    {
                        "id": person.get("id"),
                        "name": person.get("nickname") or person.get("name") or "Anonymous",
                        "avatar": person.get("avatar"),
                        "minutes": _to_int(person.get("minutes"), 0),
                    }
                )

        weekday_hour_avg = {
            str(day): {str(hour): _avg(values) for hour, values in by_hours.items()}
            for day, by_hours in hour_by_weekday.items()
        }

        latest_people = 0
        if latest_entry:
            latest_people = _to_int(latest_entry.get("people_num"), len(current_people))

        return {
            "series": series[-288:],
            "weekday_avg": weekday_avg,
            "hour_avg": hour_avg,
            "current_people": current_people,
            "last_timestamp": latest_entry.get("timestamp") if latest_entry else None,
            "weekday_hour_avg": weekday_hour_avg,
            "current_count": latest_people,
            "sample_count": len(entries),
        }

    @staticmethod
    def summarize_favorite_records(
        entries: list[dict[str, Any]],
        favorite_ids: set[str],
        per_user_limit: int = 5,
    ) -> list[dict[str, Any]]:
        favorites = {str(value) for value in favorite_ids if str(value).strip()}
        if not favorites:
            return []

        profiles: dict[str, dict[str, Any]] = {
            favorite_id: {
                "id": favorite_id,
                "name": None,
                "avatar": None,
                "last_seen": None,
                "last_minutes": 0,
                "is_current": False,
            }
            for favorite_id in favorites
        }
        sessions_by_user: dict[str, list[dict[str, Any]]] = {favorite_id: [] for favorite_id in favorites}
        active_sessions: dict[str, dict[str, Any]] = {}

        def start_session(timestamp: str, minutes: int) -> dict[str, Any]:
            return {
                "start": timestamp,
                "end": timestamp,
                "minutes_start": minutes,
                "minutes_end": minutes,
                "max_minutes": minutes,
                "samples": 1,
                "current": False,
            }

        def close_missing(seen_ids: set[str]) -> None:
            for person_id in list(active_sessions.keys()):
                if person_id in seen_ids:
                    continue
                sessions_by_user.setdefault(person_id, []).append(active_sessions.pop(person_id))

        for entry in entries:
            timestamp = str(entry.get("timestamp") or "")
            people = entry.get("using_man", []) or []
            seen_in_entry: set[str] = set()

            for person in people:
                person_id = str(person.get("id") or "")
                if person_id not in favorites:
                    continue
                seen_in_entry.add(person_id)

                minutes = _to_int(person.get("minutes"), 0)
                name = person.get("nickname") or person.get("name")
                avatar = person.get("avatar")
                profile = profiles[person_id]
                if name:
                    profile["name"] = name
                if avatar:
                    profile["avatar"] = avatar
                if timestamp:
                    profile["last_seen"] = timestamp
                profile["last_minutes"] = minutes

                active = active_sessions.get(person_id)
                if active is None or minutes + 5 < _to_int(active.get("minutes_end"), 0):
                    if active is not None:
                        sessions_by_user[person_id].append(active)
                    active = start_session(timestamp, minutes)
                    active_sessions[person_id] = active
                else:
                    active["end"] = timestamp
                    active["minutes_end"] = minutes
                    active["max_minutes"] = max(_to_int(active.get("max_minutes"), 0), minutes)
                    active["samples"] = _to_int(active.get("samples"), 0) + 1

            close_missing(seen_in_entry)

        for person_id, session in list(active_sessions.items()):
            session["current"] = True
            sessions_by_user[person_id].append(session)
            profiles[person_id]["is_current"] = True

        items: list[dict[str, Any]] = []
        for favorite_id in favorites:
            sessions = sessions_by_user.get(favorite_id, [])
            recent = list(reversed(sessions[-per_user_limit:])) if sessions else []
            profile = profiles.get(favorite_id, {})
            items.append(
                {
                    "id": favorite_id,
                    "name": profile.get("name") or f"ID {favorite_id}",
                    "avatar": profile.get("avatar"),
                    "last_seen": profile.get("last_seen"),
                    "last_minutes": _to_int(profile.get("last_minutes"), 0),
                    "is_current": bool(profile.get("is_current")),
                    "recent_records": recent,
                    "record_count": len(sessions),
                }
            )

        items.sort(
            key=lambda item: (
                1 if item.get("is_current") else 0,
                item.get("last_seen") or "",
                item.get("record_count") or 0,
            ),
            reverse=True,
        )
        return items


class QQNotificationManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    def handle_snapshot(self, cfg: dict[str, Any], previous_entry: dict[str, Any] | None, current_entry: dict[str, Any]) -> None:
        qq_cfg = ConfigManager._normalize_qq_notification(cfg.get("qq_notification"))
        if not qq_cfg.get("enabled"):
            return
        if not previous_entry:
            return
        if not qq_cfg.get("endpoint") or not qq_cfg.get("target_id"):
            return

        events = self._build_events(qq_cfg, previous_entry, current_entry)
        if not events:
            return

        state_path = os.path.join(str(cfg.get("storage_dir") or DEFAULT_CONFIG["storage_dir"]), "notification_state.json")
        cooldown_seconds = max(0, _to_int(qq_cfg.get("cooldown_minutes"), 15) * 60)

        with self._lock:
            state = self._load_state(state_path)
            changed = False
            now = datetime.now()

            for event in events:
                if not self._can_send(state, event["key"], now, cooldown_seconds):
                    continue
                self._send_message(qq_cfg, event["message"])
                state.setdefault("sent_at", {})[event["key"]] = now.isoformat()
                changed = True

            if changed:
                self._save_state(state_path, state)

    def _build_events(
        self,
        qq_cfg: dict[str, Any],
        previous_entry: dict[str, Any],
        current_entry: dict[str, Any],
    ) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        previous_people = self._people_map(previous_entry.get("using_man"))
        current_people = self._people_map(current_entry.get("using_man"))
        previous_count = _entry_people_count(previous_entry, previous_people)
        current_count = _entry_people_count(current_entry, current_people)
        current_time = _entry_timestamp(current_entry) or datetime.now()
        previous_time = _entry_timestamp(previous_entry) or current_time
        timestamp = str(current_entry.get("timestamp") or current_time.strftime("%Y-%m-%d %H:%M:%S"))

        low_traffic = qq_cfg.get("low_traffic") or {}
        low_traffic_context = self._low_traffic_context(low_traffic, current_count, timestamp)
        threshold = _to_int(low_traffic.get("threshold"), 4)
        current_low_traffic = self._matches_low_traffic(low_traffic, current_count, current_time)
        previous_low_traffic = self._matches_low_traffic(low_traffic, previous_count, previous_time)

        if bool(low_traffic.get("enabled")) and current_low_traffic and not previous_low_traffic:
            events.append(
                {
                    "key": (
                        f"low_traffic:{threshold}:"
                        f"{low_traffic_context['window_start']}:{low_traffic_context['window_end']}"
                    ),
                    "message": self._render_message(
                        str(low_traffic.get("message_template") or ""),
                        low_traffic_context,
                    ),
                }
            )

        for rule in qq_cfg.get("user_arrival_rules") or []:
            if not rule.get("enabled"):
                continue
            candidate_ids = _normalize_user_id_list(rule.get("user_ids") or rule.get("user_id"))
            if bool(rule.get("require_low_traffic")) and not current_low_traffic:
                continue

            for user_id in candidate_ids:
                if user_id in previous_people or user_id not in current_people:
                    continue

                person = current_people[user_id]
                display_name = str(person.get("nickname") or person.get("name") or rule.get("label") or f"ID {user_id}")
                event_values = {
                    "user_id": user_id,
                    "user_name": display_name,
                    "label": str(rule.get("label") or ""),
                    "minutes": _to_int(person.get("minutes"), 0),
                    "current_count": current_count,
                    "timestamp": timestamp,
                    "threshold": threshold,
                    "window_start": low_traffic_context["window_start"],
                    "window_end": low_traffic_context["window_end"],
                }
                events.append(
                    {
                        "key": (
                            f"user_arrival:{user_id}:"
                            f"rule-{','.join(candidate_ids)}:"
                            f"label-{str(rule.get('label') or '')}:"
                            f"lt-{1 if bool(rule.get('require_low_traffic')) else 0}:"
                            f"{low_traffic_context['window_start']}:{low_traffic_context['window_end']}:{threshold}"
                        ),
                        "message": self._render_message(
                            str(rule.get("message_template") or ""),
                            event_values,
                        ),
                    }
                )

        return events

    @staticmethod
    def _people_map(people: Any) -> dict[str, dict[str, Any]]:
        items: dict[str, dict[str, Any]] = {}
        for person in people or []:
            person_id = str((person or {}).get("id") or "").strip()
            if person_id:
                items[person_id] = person
        return items

    @staticmethod
    def _render_message(template: str, values: dict[str, Any]) -> str:
        safe_values = {key: str(value) for key, value in values.items()}
        try:
            return template.format_map(_SafeFormatDict(safe_values))
        except Exception:
            return template

    @staticmethod
    def _matches_low_traffic(low_traffic: dict[str, Any], current_count: int, current_time: datetime) -> bool:
        threshold = _to_int(low_traffic.get("threshold"), 4)
        start_time = _normalize_time_text(low_traffic.get("start_time"), fallback="00:00")
        end_time = _normalize_time_text(low_traffic.get("end_time"), fallback="00:00")
        return current_count <= threshold and _is_within_time_range(current_time, start_time, end_time)

    @staticmethod
    def _low_traffic_context(low_traffic: dict[str, Any], current_count: int, timestamp: str) -> dict[str, Any]:
        start_time = _normalize_time_text(low_traffic.get("start_time"), fallback="00:00")
        end_time = _normalize_time_text(low_traffic.get("end_time"), fallback="00:00")
        return {
            "current_count": current_count,
            "threshold": _to_int(low_traffic.get("threshold"), 4),
            "timestamp": timestamp,
            "window_start": start_time,
            "window_end": end_time,
        }

    @staticmethod
    def _load_state(path: str) -> dict[str, Any]:
        if not os.path.exists(path):
            return {"sent_at": {}}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {"sent_at": {}}
        if not isinstance(payload, dict):
            return {"sent_at": {}}
        sent_at = payload.get("sent_at")
        if not isinstance(sent_at, dict):
            sent_at = {}
        return {"sent_at": {str(key): str(value) for key, value in sent_at.items()}}

    @staticmethod
    def _save_state(path: str, payload: dict[str, Any]) -> None:
        temp_path = f"{path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)

    @staticmethod
    def _can_send(state: dict[str, Any], key: str, now: datetime, cooldown_seconds: int) -> bool:
        if cooldown_seconds <= 0:
            return True
        last_sent = str((state.get("sent_at") or {}).get(key) or "").strip()
        if not last_sent:
            return True
        parsed = _parse_timestamp(last_sent)
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(last_sent)
            except ValueError:
                return True
        return (now - parsed).total_seconds() >= cooldown_seconds

    def _send_message(self, qq_cfg: dict[str, Any], message: str) -> None:
        url, payload = self._build_request(qq_cfg, message)
        headers = {}
        access_token = str(qq_cfg.get("access_token") or "").strip()
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=_to_int(qq_cfg.get("timeout_seconds"), 10),
        )
        response.raise_for_status()
        try:
            response_payload = response.json()
        except ValueError:
            return
        status = str(response_payload.get("status") or "").lower()
        retcode = response_payload.get("retcode")
        if (status and status != "ok") or (retcode not in (None, 0)):
            raise RuntimeError(f"QQ notification failed: {response_payload}")

    @staticmethod
    def _build_request(qq_cfg: dict[str, Any], message: str) -> tuple[str, dict[str, Any]]:
        endpoint = str(qq_cfg.get("endpoint") or "").rstrip("/")
        target_type = str(qq_cfg.get("target_type") or "private")
        target_id = _coerce_target_id(qq_cfg.get("target_id"))

        if endpoint.endswith("/send_msg"):
            payload = {
                "message_type": target_type,
                "message": message,
                "auto_escape": False,
            }
            payload["user_id" if target_type == "private" else "group_id"] = target_id
            return endpoint, payload

        if endpoint.endswith("/send_private_msg") or endpoint.endswith("/send_group_msg"):
            payload = {"message": message, "auto_escape": False}
            if endpoint.endswith("/send_private_msg"):
                payload["user_id"] = target_id
            else:
                payload["group_id"] = target_id
            return endpoint, payload

        if target_type == "group":
            return f"{endpoint}/send_group_msg", {"group_id": target_id, "message": message, "auto_escape": False}
        return f"{endpoint}/send_private_msg", {"user_id": target_id, "message": message, "auto_escape": False}


class _SafeFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def build_url(api_base: str, shop_id: int) -> str:
    return f"{api_base}/auth/run/queryShopDetail?page=1&pageSize=10&shopId={shop_id}"


def fetch_gym_status(api_base: str, shop_id: int, timeout: int = 10) -> dict[str, Any]:
    response = _get_http_session().get(build_url(api_base, shop_id), timeout=timeout)
    response.raise_for_status()
    payload = response.json().get("data", {})
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "timestamp": timestamp,
        "people_num": _to_int(payload.get("people_num"), 0),
        "using_man": payload.get("using_man", []) or [],
        "raw": payload,
    }


def _entry_people_count(entry: dict[str, Any], people_map: dict[str, dict[str, Any]] | None = None) -> int:
    if people_map is None:
        people_map = QQNotificationManager._people_map(entry.get("using_man"))
    return _to_int(entry.get("people_num"), len(people_map))


def _entry_timestamp(entry: dict[str, Any] | None) -> datetime | None:
    if not entry:
        return None
    return _parse_timestamp(entry.get("timestamp"))


def _normalize_user_id_list(value: Any) -> list[str]:
    if isinstance(value, list):
        source = [str(item or "").strip() for item in value]
    else:
        source = str(value or "").split(",")
    items = [item.strip() for item in source if item and item.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _coerce_target_id(value: Any) -> int | str:
    text = str(value or "").strip()
    if text.isdigit():
        try:
            return int(text)
        except ValueError:
            return text
    return text


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_time_text(value: Any, fallback: str = "00:00", legacy_hour: Any | None = None) -> str:
    text = str(value or "").strip()
    if text:
        parts = text.split(":", 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            hour = max(0, min(23, int(parts[0])))
            minute = max(0, min(59, int(parts[1])))
            return f"{hour:02d}:{minute:02d}"
        if text.isdigit():
            hour = max(0, min(23, int(text)))
            return f"{hour:02d}:00"

    if legacy_hour is not None and str(legacy_hour).strip():
        try:
            hour = max(0, min(23, int(legacy_hour)))
            return f"{hour:02d}:00"
        except (TypeError, ValueError):
            pass

    return fallback


def _time_text_to_minutes(value: Any) -> int:
    normalized = _normalize_time_text(value)
    hour_text, minute_text = normalized.split(":", 1)
    return int(hour_text) * 60 + int(minute_text)


def _is_within_time_range(moment: datetime, start_time: str, end_time: str) -> bool:
    current_minutes = (moment.hour * 60) + moment.minute
    start_minutes = _time_text_to_minutes(start_time)
    end_minutes = _time_text_to_minutes(end_time)
    if start_minutes == end_minutes:
        return True
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


def _get_http_session() -> requests.Session:
    session = getattr(_HTTP_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(_API_HEADERS)
        _HTTP_LOCAL.session = session
    return session


def _avg(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    for parser in (datetime.fromisoformat, lambda raw: datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")):
        try:
            return parser(text)
        except ValueError:
            continue
    return None
