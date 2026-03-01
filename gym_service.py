from __future__ import annotations

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
                self._config = DEFAULT_CONFIG.copy()
                self.save(self._config)
                return self._config

            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)

            merged = DEFAULT_CONFIG.copy()
            merged.update(data or {})
            merged["favorites"] = self._normalize_favorites(merged.get("favorites"))
            self._ensure_storage_dir(merged)
            self._config = merged
            return self._config

    def save(self, cfg: dict[str, Any]) -> None:
        with self._lock:
            normalized = DEFAULT_CONFIG.copy()
            normalized.update(cfg or {})
            normalized["favorites"] = self._normalize_favorites(normalized.get("favorites"))
            self._ensure_storage_dir(normalized)

            config_dir = os.path.dirname(os.path.abspath(self.path))
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)

            temp_path = f"{self.path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(normalized, handle, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.path)
            self._config = normalized

    @staticmethod
    def _normalize_favorites(values: Any) -> list[str]:
        if not values:
            return []
        return sorted({str(value) for value in values if str(value).strip()})

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


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
