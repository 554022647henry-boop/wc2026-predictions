import json, requests as req, sys
from datetime import datetime, timezone
from pathlib import Path

today_utc = datetime.now(timezone.utc).strftime("%Y%m%d")
url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={today_utc}"
r = req.get(url, timeout=15)
data = r.json()

out = []
events = data.get("events", [])
out.append(f"Events: {len(events)}")
for ev in events:
    comps = ev.get("competitions", [])
    for c in comps:
        teams = c.get("competitors", [])
        if len(teams) >= 2:
            t1 = teams[0]["team"]["shortDisplayName"]
            t2 = teams[1]["team"]["shortDisplayName"]
            s1 = teams[0].get("score", "?")
            s2 = teams[1].get("score", "?")
            status = c["status"]["type"]["description"]
            out.append(f"{t1} {s1} - {s2} {t2} [{status}]")

Path("_results_out.txt").write_text("\n".join(out), encoding="utf-8")
print("OK - written to _results_out.txt")
