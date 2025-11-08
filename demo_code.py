import csv
import os
from datetime import datetime

import requests

url = "http://106.55.236.110:8999/auth/run/queryShopDetail?page=1&pageSize=10&shopId=218"

headers = {
    'Host': "106.55.236.110:8999",
    'User-Agent': "Mozilla/5.0 (Linux; Android 14; LE2100 Build/UKQ1.230924.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/137.0.7151.115 Mobile Safari/537.36",
    'Accept': "application/json, text/plain, */*",
    'Accept-Encoding': "gzip, deflate",
    'Origin': "http://www.hehacat.com",
    'X-Requested-With': "com.hehacat",
    'Referer': "http://www.hehacat.com/",
    'Accept-Language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,zh-TW;q=0.6"
}

LOG_DIR = os.path.join(os.path.dirname(__file__), "data")
LOG_PATH = os.path.join(LOG_DIR, "gym_users_log.csv")


def ensure_log_path():
    os.makedirs(LOG_DIR, exist_ok=True)


def query_and_log():
    response = requests.get(url, headers=headers)
    data = response.json().get("data", {})
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    people_num = data.get("people_num", 0)
    using_man = data.get("using_man", [])

    ensure_log_path()
    with open(LOG_PATH, "a", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        if using_man:
            for man in using_man:
                writer.writerow([
                    timestamp,
                    man.get("id"),
                    man.get("nickname"),
                    man.get("minutes"),
                    man.get("avatar"),
                    people_num
                ])
        else:
            # 没有用户时，记录一行总人数信息，用户字段填空
            writer.writerow([
                timestamp,
                "",
                "",
                "",
                "",
                people_num
            ])

if __name__ == "__main__":
    query_and_log()
