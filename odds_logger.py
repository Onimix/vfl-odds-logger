#!/usr/bin/env python3
"""
ODDS LOGGER — single snapshot mode for GitHub Actions
"""
import csv
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests

LOG_DIR = Path("odds_history")
LOG_DIR.mkdir(parents=True, exist_ok=True)

TZ_NG = timezone(timedelta(hours=1))
ODDS_URL  = "https://www.sportybet.com/api/ng/factsCenter/pcUpcomingEvents"
SPORT_ID  = "sr:sport:202120001"

LEAGUES = {
    "england": "sv:category:202120001",
    "spain":   "sv:category:202120002",
    "italy":   "sv:category:202120003",
    "germany": "sv:category:202120004",
    "france":  "sv:category:202120005",
}

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sportybet.com/ng/sport/vFootball",
    "Origin": "https://www.sportybet.com",
    "Current-Country": "NG",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SCORE_RE = re.compile(r"^\s*(\d+)\s*[:\-]\s*(\d+)\s*$")


def warmup():
    for u in ("https://www.sportybet.com/ng/",
              "https://www.sportybet.com/ng/sport/vFootball"):
        try:
            SESSION.get(u, timeout=20)
        except Exception:
            pass


def fetch_page(category_id, page_num):
    params = {
        "sportId": SPORT_ID,
        "marketId": "1,10,18,29,45",
        "pageSize": 100,
        "pageNum": page_num,
        "categoryId": category_id,
        "_t": int(time.time() * 1000),
    }
    try:
        r = SESSION.get(ODDS_URL, params=params, timeout=20)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def capture_league(category_id):
    tours, seen = {}, set()
    for p in range(1, 10):
        data = fetch_page(category_id, p)
        if not data or data.get("bizCode") != 10000:
            break
        payload = data.get("data") or {}
        tournaments = payload.get("tournaments") or []
        if not tournaments:
            break
        added = 0
        for t in tournaments:
            tid = t["id"]
            tours.setdefault(tid, {"events": []})
            for ev in t.get("events", []):
                if ev["eventId"] in seen:
                    continue
                seen.add(ev["eventId"])
                tours[tid]["events"].append(ev)
                added += 1
        if added == 0:
            break
        time.sleep(0.15)
    return {"tournaments": list(tours.values())}


def extract_odds(ev):
    out = {"1x2": {}, "under15": None, "over25": None,
           "btts_no": None, "btts_yes": None, "cs": {}}
    for mk in ev.get("markets", []):
        mid = str(mk.get("id"))
        spec = str(mk.get("specifier", ""))
        if mid == "1":
            for o in mk.get("outcomes", []):
                if o.get("isActive"):
                    d = str(o.get("desc", "")).lower()
                    if d in ("home", "draw", "away"):
                        out["1x2"][d] = float(o["odds"])
        elif mid == "18":
            if "total=1.5" in spec:
                for o in mk.get("outcomes", []):
                    if o.get("isActive") and str(o.get("desc","")).lower() in ("under 1.5","under"):
                        out["under15"] = float(o["odds"])
            if "total=2.5" in spec:
                for o in mk.get("outcomes", []):
                    if o.get("isActive") and str(o.get("desc","")).lower() in ("over 2.5","over"):
                        out["over25"] = float(o["odds"])
        elif mid == "29":
            for o in mk.get("outcomes", []):
                if o.get("isActive"):
                    d = str(o.get("desc","")).lower()
                    if d == "no":
                        out["btts_no"] = float(o["odds"])
                    elif d == "yes":
                        out["btts_yes"] = float(o["odds"])
        elif mid == "45":
            for o in mk.get("outcomes", []):
                if not o.get("isActive"):
                    continue
                m = SCORE_RE.match(str(o.get("desc", "")).strip())
                if m:
                    sc = f"{int(m.group(1))}-{int(m.group(2))}"
                    out["cs"][sc] = float(o["odds"])
    return out


def snapshot():
    snap = {}
    for league_name, cat_id in LEAGUES.items():
        cap = capture_league(cat_id)
        for tour in cap["tournaments"]:
            for ev in tour.get("events", []):
                home = ev.get("homeTeamName")
                away = ev.get("awayTeamName")
                if not home or not away:
                    continue
                ts = ev.get("estimateStartTime") or 0
                snap[ev["eventId"]] = {
                    "league": league_name,
                    "home": home,
                    "away": away,
                    "block": datetime.fromtimestamp(ts/1000, tz=TZ_NG).strftime("%H:%M") if ts else "?",
                    "start_ts": ts,
                    "odds": extract_odds(ev),
                }
    return snap


def main():
    print("ODDS LOGGER — single snapshot (GitHub Actions mode)")
    warmup()
    try:
        snap = snapshot()
        now = datetime.now(TZ_NG)
        fname = LOG_DIR / f"odds_{now.strftime('%Y-%m-%d_%H-%M-%S')}.json"
        with fname.open("w", encoding="utf-8") as f:
            json.dump({"timestamp": now.isoformat(), "matches": snap}, f)
        print(f"Saved {len(snap)} matches to {fname.name}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()