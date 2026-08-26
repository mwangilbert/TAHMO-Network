#!/usr/bin/env python3
"""
Take one Pan-Africa network snapshot and append it to snapshots.json.

Runs headless (no server needed) -- it hits the same TAHMO APIs the proxy
relays, computes the same metrics tahmo_live.html shows on the Map tab, and
appends one entry in the exact shape the Trends tab already expects from a
manual "Save snapshot" click. Intended to run daily from a GitHub Action so
every visitor sees the same shared history instead of only-you localStorage
snapshots.

Usage:
    python scripts/take_snapshot.py [path/to/snapshots.json]
"""
import json
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

ENDPOINTS = {
    "open":     "https://tickets.tahmo.org/api/issues?status=open",
    "pending":  "https://tickets.tahmo.org/api/issues?status=pending",
    "stations": "https://datahub.tahmo.org/custom/stations/status",
}
EAT = timezone(timedelta(hours=3))  # East Africa Time, no DST


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TAHMO-Live/1.1"})
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        data = json.loads(r.read())
    return data["data"] if isinstance(data, dict) and "data" in data else data


def build_snapshot():
    open_t = fetch(ENDPOINTS["open"])
    pend_t = fetch(ENDPOINTS["pending"])
    stations = fetch(ENDPOINTS["stations"])

    by_station = {}
    for t in open_t:
        sid = t.get("station") or (t.get("site") or {}).get("SiteCode")
        if sid and sid not in by_station:
            by_station[sid] = "open"
    for t in pend_t:
        sid = t.get("station") or (t.get("site") or {}).get("SiteCode")
        if sid and sid not in by_station:
            by_station[sid] = "pending"

    total = len(stations)
    open_ids = [s["id"] for s in stations if by_station.get(s["id"]) == "open"]
    pend_ids = [s["id"] for s in stations if by_station.get(s["id"]) == "pending"]
    health = round((total - len(open_ids)) / total * 1000) / 10 if total else 0

    stamp = datetime.now(EAT).strftime("%Y-%m-%d %H:%M")
    return {
        "stamp": stamp,
        "scope": "Pan-Africa",
        "total": total,
        "openTk": len(open_t),
        "pendTk": len(pend_t),
        "openSites": len(open_ids),
        "pendSites": len(pend_ids),
        "health": health,
        "openIds": open_ids,
        "pendIds": pend_ids,
        "auto": True,
    }


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "snapshots.json"
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            snaps = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        snaps = []

    snap = build_snapshot()
    # Replace same-day auto entry instead of piling up duplicates on manual re-runs.
    snaps = [s for s in snaps if not (s.get("auto") and s.get("stamp", "")[:10] == snap["stamp"][:10])]
    snaps.append(snap)
    snaps.sort(key=lambda s: s["stamp"])

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snaps, f, indent=2)

    print(f"Snapshot saved: {snap['stamp']} EAT -- "
          f"{snap['total']} stations, {snap['openTk']} open / {snap['pendTk']} pending tickets, "
          f"{snap['health']}% health -- {len(snaps)} total snapshot(s) in {out_path}")


if __name__ == "__main__":
    main()
