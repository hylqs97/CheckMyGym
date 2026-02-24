import json
import os
from datetime import datetime
from typing import Any, Dict, List

import requests


DEFAULT_CONFIG = {
    "storage_dir": "data",
    "poll_interval_minutes": 5,
    "shop_id": 218,
    "api_base": "http://106.55.236.110:8999",
    "open_hour_start": 6,
    "open_hour_end": 23,
    "port": 6767,
    "favorites": [],
}


class ConfigManager:
    def __init__(self, path: str = "config.json") -> None:
        self.path = path
        self._config = None

    def load(self) -> Dict[str, Any]:
        if self._config is not None:
            return self._config
        if not os.path.exists(self.path):
            self._config = DEFAULT_CONFIG.copy()
            self.save(self._config)
            return self._config
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # merge defaults
        merged = DEFAULT_CONFIG.copy()
        merged.update(data or {})
        if "favorites" not in merged:
            merged["favorites"] = []
        self._config = merged
        # ensure storage dir exists
        os.makedirs(self._config["storage_dir"], exist_ok=True)
        return self._config

    def save(self, cfg: Dict[str, Any]) -> None:
        # ensure storage dir exists when saving
        storage = cfg.get("storage_dir", DEFAULT_CONFIG["storage_dir"]) or DEFAULT_CONFIG["storage_dir"]
        os.makedirs(storage, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        if "favorites" not in cfg:
            cfg["favorites"] = []
        self._config = cfg


class DataStore:
    def __init__(self, storage_dir: str) -> None:
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.data_file = os.path.join(self.storage_dir, "gym_data.jsonl")

    def append(self, entry: Dict[str, Any]) -> None:
        with open(self.data_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_all(self, limit: int | None = None) -> List[Dict[str, Any]]:
        if not os.path.exists(self.data_file):
            return []
        items: List[Dict[str, Any]] = []
        with open(self.data_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if limit:
            return items[-limit:]
        return items

    @staticmethod
    def summarize(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Aggregate by weekday and hour
        by_weekday: Dict[int, List[int]] = {i: [] for i in range(7)}
        by_hour: Dict[int, List[int]] = {i: [] for i in range(24)}
        hour_by_weekday: Dict[int, Dict[int, List[int]]] = {
            day: {hour: [] for hour in range(24)} for day in range(7)
        }
        series = []
        latest_entry = entries[-1] if entries else None
        for e in entries:
            ts = e.get("timestamp")
            people = int(e.get("people_num", 0))
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                # try common format
                try:
                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
            by_weekday[dt.weekday()].append(people)
            by_hour[dt.hour].append(people)
            hour_by_weekday[dt.weekday()][dt.hour].append(people)
            series.append({"t": ts, "people_num": people})

        def avg(vals: List[int]) -> float:
            return round(sum(vals) / len(vals), 2) if vals else 0.0

        weekday_avg = {str(k): avg(v) for k, v in by_weekday.items()}
        hour_avg = {str(k): avg(v) for k, v in by_hour.items()}
        current_people: List[Dict[str, Any]] = []
        if latest_entry:
            for person in latest_entry.get("using_man", []) or []:
                current_people.append(
                    {
                        "id": person.get("id"),
                        "name": person.get("nickname") or person.get("name") or "匿名用户",
                        "avatar": person.get("avatar"),
                        "minutes": person.get("minutes", 0),
                    }
                )
        weekday_hour_avg = {
            str(day): {str(hour): avg(vals) for hour, vals in by_hours.items()}
            for day, by_hours in hour_by_weekday.items()
        }

        return {
            "series": series[-288:],  # last ~24h if sampled every 5min
            "weekday_avg": weekday_avg,
            "hour_avg": hour_avg,
            "current_people": current_people,
            "last_timestamp": latest_entry.get("timestamp") if latest_entry else None,
            "weekday_hour_avg": weekday_hour_avg,
        }


def build_url(api_base: str, shop_id: int) -> str:
    return f"{api_base}/auth/run/queryShopDetail?page=1&pageSize=10&shopId={shop_id}"


def fetch_gym_status(api_base: str, shop_id: int) -> Dict[str, Any]:
    url = build_url(api_base, shop_id)
    headers = {
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
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", {})
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    people_num = data.get("people_num", 0)
    using_man = data.get("using_man", [])
    return {
        "timestamp": timestamp,
        "people_num": people_num,
        "using_man": using_man,
    }
