"""Push daily report and index.html to GitHub Pages"""
import json
import base64
import requests as req
from datetime import datetime
from pathlib import Path

token_file = Path("D:/Projects/github/.github_token")
token = token_file.read_text(encoding="utf-8").strip()
username = "554022647henry-boop"
repo = "wc2026-predictions"
H = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

# Verify token
r = req.get("https://api.github.com/user", headers=H, timeout=10)
print(f"GitHub auth: {r.status_code}")

msg = f"Daily report 06.22 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
files = [
    ("web/daily_report_0622.html", "web/daily_report_0622.html"),
    ("web/index.html", "web/index.html"),
]

for local_rel, target_path in files:
    local_path = Path(local_rel)
    if not local_path.exists():
        print(f"  SKIP: {local_rel} not found")
        continue
    encoded = base64.b64encode(local_path.read_bytes()).decode()

    r2 = req.get(
        f"https://api.github.com/repos/{username}/{repo}/contents/{target_path}",
        headers=H, timeout=10,
    )
    sha = r2.json().get("sha", "") if r2.status_code == 200 else ""

    r3 = req.put(
        f"https://api.github.com/repos/{username}/{repo}/contents/{target_path}",
        headers=H,
        json={"message": msg, "content": encoded, **({"sha": sha} if sha else {})},
        timeout=30,
    )
    if r3.status_code in (200, 201):
        print(f"[OK] {target_path}")
    else:
        print(f"[FAIL] {target_path}: {r3.status_code} {r3.text[:120]}")

print(f"Done -> https://{username}.github.io/{repo}/")
