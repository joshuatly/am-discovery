"""One-time script: backfill alt_name for watchlist artists using MY storefront name.

For each watchlist artist without an alt_name, fetches their name from the MY
(Malaysia) Apple Music storefront. If it differs from the stored name, sets it
as the alt_name via the deployed API.

Usage:
    uv run python backfill_alt_names.py [--api-base https://am.tly.jp] [--dry-run]
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--api-base", default="https://am.tly.jp", help="Base URL of the deployed API")
parser.add_argument("--storefront", default="my", help="Storefront to check names against (default: my)")
parser.add_argument("--dry-run", action="store_true", help="Print what would change without patching")
args = parser.parse_args()

API_BASE = args.api_base.rstrip("/")
STOREFRONT = args.storefront


def api_get(path):
    url = API_BASE + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def api_patch(path, body):
    url = API_BASE + path
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="PATCH",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------------------
# Step 1: get watchlist artists without alt_name
# ---------------------------------------------------------------------------
print(f"Fetching watchlist from {API_BASE}...")
watchlist = api_get("/api/watchlist")
missing = [a for a in watchlist if not (a.get("alt_name") or "").strip()]
print(f"  {len(watchlist)} total artists, {len(missing)} without alt_name\n")

if not missing:
    print("Nothing to do.")
    sys.exit(0)

# ---------------------------------------------------------------------------
# Step 2: use local AppleMusicClient to look up MY names
# ---------------------------------------------------------------------------
try:
    from client import AppleMusicClient
except ImportError:
    print("ERROR: Could not import client.py — run this from the project root with `uv run python backfill_alt_names.py`")
    sys.exit(1)

client = AppleMusicClient()

updated = 0
skipped = 0
errors = 0

for artist in missing:
    artist_id = artist["artist_id"]
    stored_name = artist["name"]

    try:
        info = client.get_artist_info_only(artist_id, STOREFRONT)
    except Exception as e:
        print(f"  [ERROR] {stored_name} ({artist_id}): {e}")
        errors += 1
        continue

    my_name = (info.get("name") or "").strip()
    if not my_name:
        print(f"  [SKIP ] {stored_name} ({artist_id}): no name returned from {STOREFRONT}")
        skipped += 1
        continue

    if my_name.lower() == stored_name.lower():
        print(f"  [SAME ] {stored_name} ({artist_id}): same in {STOREFRONT}")
        skipped += 1
        continue

    print(f"  [{'DRY ' if args.dry_run else 'PATCH'}] {stored_name} → alt_name: {my_name}  ({artist_id})")
    if not args.dry_run:
        try:
            api_patch(f"/api/watchlist/{artist_id}", {"alt_name": my_name})
            updated += 1
        except Exception as e:
            print(f"         PATCH failed: {e}")
            errors += 1
    else:
        updated += 1

print(f"\nDone. updated={updated}, skipped={skipped}, errors={errors}")
if args.dry_run:
    print("(dry-run — no changes were written)")
