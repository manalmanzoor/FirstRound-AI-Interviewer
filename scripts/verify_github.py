"""Phase 0 key check: confirm GITHUB_TOKEN is valid and authenticated
(5,000 req/hr) rather than falling back to the 60/hr unauthenticated limit.
Run: python scripts/verify_github.py
"""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get("GITHUB_TOKEN")

if not TOKEN:
    print("FAIL: GITHUB_TOKEN not set in .env")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
}

resp = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=10)

if resp.status_code != 200:
    print(f"FAIL: GitHub API returned {resp.status_code}: {resp.text[:200]}")
    sys.exit(1)

data = resp.json()
core = data["resources"]["core"]
print(f"OK  authenticated — rate limit {core['limit']}/hr, {core['remaining']} remaining")

if core["limit"] <= 60:
    print("WARN limit looks unauthenticated (<=60/hr) — check the token scope/validity")
else:
    print("OK  confirmed authenticated ceiling (>60/hr)")

# Confirm identity too, since a malformed/expired token can still hit rate_limit.
me = requests.get("https://api.github.com/user", headers=headers, timeout=10)
if me.status_code == 200:
    print(f"OK  token belongs to: {me.json().get('login')}")
else:
    print(f"WARN /user check failed ({me.status_code}) — token may be missing a scope")

print("GitHub key check complete.")
