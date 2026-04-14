#!/usr/bin/env python3
"""Check exclusion audiences across all ACTIVE ad sets in the Testing campaign,
plus a few recent PAUSED ones to find the canonical exclusion set."""
import json, sys
from pathlib import Path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from config_loader import load_all
from meta_api import BASE_URL, _meta_request

config = load_all("ts_twelve_south")
token = config["fb_access_token"]
TESTING_CAMPAIGN = "6691799568075"

ids = [
    "6885172141475",  # ACTIVE AIRFLY
    "6891670962475",  # ACTIVE AIRFLY MIX
    "6902281384075",  # ACTIVE AIRFLY STATICS FLEX
    "6867182241275",  # PAUSED POWERBUG
    "6876553941075",  # PAUSED POWERBUG FLEXADS
]

for aid in ids:
    resp = _meta_request(
        "GET", f"{BASE_URL}/{aid}",
        access_token=token,
        params={
            "access_token": token,
            "fields": "name,status,effective_status,targeting",
        },
    )
    print(f"\n─── {aid}  {resp.get('effective_status','')}  {resp.get('name','')}")
    targeting = resp.get("targeting") or {}
    excl_t = (targeting.get("exclusions") or {}).get("custom_audiences") or []
    print(f"  targeting.exclusions.custom_audiences ({len(excl_t)}):")
    for e in excl_t:
        print(f"    {e.get('id')}  {e.get('name','')}")
    # Also check for the newer top-level excluded_custom_audiences on the adset read
    # (Meta has deprecated reads of this field; try targeting first which is authoritative)
