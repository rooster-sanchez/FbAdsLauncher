#!/usr/bin/env python3
"""Inspect the 2 live PP ad sets' targeting + existing ads' creative identity."""
import json
import sys
from pathlib import Path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from config_loader import load_all
from meta_api import _meta_request, BASE_URL

config = load_all("pp_primal_path")
token = config["fb_access_token"]

ADSETS = ["120238521835520227", "120236456109310227"]

for adset_id in ADSETS:
    print(f"\n═══ Ad set {adset_id} ═══")
    data = _meta_request("GET", f"{BASE_URL}/{adset_id}", access_token=token, params={
        "access_token": token,
        "fields": "id,name,status,targeting,promoted_object",
    })
    t = data.get("targeting", {})
    print(f"  name: {data.get('name')}")
    print(f"  publisher_platforms: {t.get('publisher_platforms')}")
    print(f"  facebook_positions: {t.get('facebook_positions')}")
    print(f"  instagram_positions: {t.get('instagram_positions')}")
    # Find existing ads on this adset and inspect creative
    ads = _meta_request("GET", f"{BASE_URL}/{adset_id}/ads", access_token=token, params={
        "access_token": token,
        "fields": "id,name,status,creative{id,object_story_spec,asset_feed_spec{link_urls}}",
        "limit": 5,
        "effective_status": json.dumps(["ACTIVE"]),
    }).get("data", [])
    print(f"  active ads: {len(ads)}")
    for a in ads[:3]:
        oss = (a.get("creative") or {}).get("object_story_spec") or {}
        print(f"    - {a['id']}  {a['name'][:60]}")
        print(f"      object_story_spec: {oss}")
