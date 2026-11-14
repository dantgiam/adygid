"""Обновить цифры аудитории для /partners из Яндекс Метрики.

Токен — из YANDEX_METRIKA_TOKEN или YANDEX_OAUTH_TOKEN (нужно только чтение).
Без --write печатает цифры, с --write перезаписывает
site_app/data/partners_audience.json. Токен не печатается.

    python scripts/partners_audience_metrika.py --write
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

COUNTER = os.getenv("YANDEX_METRIKA_COUNTER", "111028002")
OUT = os.path.join(os.path.dirname(__file__), "..", "site_app", "data", "partners_audience.json")


def stat(token: str, d1: date, d2: date, dims: str | None = None) -> dict:
    p = {"ids": COUNTER, "metrics": "ym:s:users,ym:s:visits,ym:s:pageviews",
         "date1": d1.isoformat(), "date2": d2.isoformat(), "accuracy": "full"}
    if dims:
        p["dimensions"] = dims
    req = urllib.request.Request("https://api-metrika.yandex.net/stat/v1/data?" + urllib.parse.urlencode(p),
                                 headers={"Authorization": "OAuth " + token})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            # Метрика иногда отвечает 400/429 на частые запросы — пробуем ещё раз.
            if attempt == 3:
                raise SystemExit(f"Метрика ответила {e.code}: {e.read()[:300]!r}")
            time.sleep(2 + attempt * 3)


def main() -> None:
    token = os.getenv("YANDEX_METRIKA_TOKEN") or os.getenv("YANDEX_OAUTH_TOKEN")
    if not token:
        sys.exit("нет YANDEX_METRIKA_TOKEN / YANDEX_OAUTH_TOKEN")
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=29)
    cur = stat(token, start, end)["totals"]
    prev = stat(token, start - timedelta(days=30), start - timedelta(days=1))["totals"]
    total = stat(token, date(2026, 7, 1), end)["totals"]
    src = stat(token, start, end, "ym:s:lastTrafficSource")
    search_visits = sum(r["metrics"][1] for r in src["data"] if r["dimensions"][0].get("id") == "organic")
    old = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            old = json.load(fh)
    data = {
        "_comment": old.get("_comment", "Цифры аудитории для /partners из Яндекс Метрики."),
        "period_from": start.isoformat(), "period_to": end.isoformat(),
        "users_30d": int(cur[0]), "visits_30d": int(cur[1]), "pageviews_30d": int(cur[2]),
        "users_prev_30d": int(prev[0]), "users_total": int(total[0]), "total_since": "2026-07",
        "search_share_visits": int(search_visits * 100 // cur[1]) if cur[1] else 0,
        "top_regions": old.get("top_regions", ""), "updated": date.today().isoformat(),
    }
    print(json.dumps({k: v for k, v in data.items() if k != "_comment"}, ensure_ascii=False, indent=2))
    if "--write" in sys.argv:
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("записано:", os.path.relpath(OUT))


if __name__ == "__main__":
    main()
