#!/usr/bin/env python3
"""Patch HiRise + PowerBug ad sets: add excluded_custom_audiences INSIDE
the targeting JSON (the field is silently dropped when sent top-level).
"""
import json, sys
from pathlib import Path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from config_loader import load_all
from meta_api import BASE_URL, _meta_request

DRY_RUN = "--dry-run" in sys.argv

config = load_all("ts_twelve_south")
token = config["fb_access_token"]

EXCL_IDS = [
    "6606781459475",  # Klaviyo - MMS - All clients all time
    "6301185183875",  # 12S - Purchases 180 Days
    "6802575466475",  # TS - Existing Customers Shopify Export
    "6576843032475",  # Shopify Export | Lapsed Customers 12M
    "6576842535475",  # Shopify Export | HV Lapsed Customers 12M
]
ADSETS = ["6909530076275", "6909530372475"]

for aid in ADSETS:
    print(f"\n═══ Ad set {aid} ═══")
    current = _meta_request(
        "GET", f"{BASE_URL}/{aid}",
        access_token=token,
        params={"access_token": token, "fields": "name,targeting"},
    )
    print(f"  {current.get('name')}")
    targeting = current.get("targeting", {}) or {}

    # Inject excluded_custom_audiences inside the targeting object
    targeting["excluded_custom_audiences"] = [{"id": i} for i in EXCL_IDS]
    targeting.setdefault("targeting_automation", {"advantage_audience": 0})

    if DRY_RUN:
        print(f"  [DRY] Would PATCH with {len(EXCL_IDS)} exclusions inside targeting")
        continue

    resp = _meta_request(
        "POST", f"{BASE_URL}/{aid}", access_token=token,
        data={"access_token": token, "targeting": json.dumps(targeting)},
    )
    print(f"  PATCH: {resp}")

    # Verify
    v = _meta_request(
        "GET", f"{BASE_URL}/{aid}", access_token=token,
        params={"access_token": token, "fields": "targeting"},
    )
    excl = (v.get("targeting", {}) or {}).get("excluded_custom_audiences", []) or []
    print(f"  Verified: {len(excl)} exclusions now stored:")
    for e in excl:
        print(f"    - {e.get('id')}  {e.get('name','')}")
