#!/usr/bin/env python3
"""Check exclusions actually applied to the newly created ad sets."""
import json, sys
from pathlib import Path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from config_loader import load_all
from meta_api import BASE_URL, _meta_request

config = load_all("ts_twelve_south")
token = config["fb_access_token"]

ADSETS = ["6909530076275", "6909530372475"]

for aid in ADSETS:
    print(f"\n═══ Ad set {aid} ═══")
    # Try every possibly relevant field
    for field_set in [
        "targeting",
        "targeting_expansion",
    ]:
        try:
            resp = _meta_request(
                "GET", f"{BASE_URL}/{aid}",
                access_token=token,
                params={"access_token": token, "fields": field_set},
            )
            print(f"  {field_set}:")
            print(json.dumps(resp, indent=2)[:3000])
        except Exception as e:
            print(f"  {field_set} error: {e}")
