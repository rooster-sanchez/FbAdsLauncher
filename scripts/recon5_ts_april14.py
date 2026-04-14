#!/usr/bin/env python3
"""Inspect existing PowerBug flex ad and its ad set to understand configuration."""
import json, sys
from pathlib import Path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from config_loader import load_all
from meta_api import BASE_URL, _meta_request

config = load_all("ts_twelve_south")
token = config["fb_access_token"]

# Existing working flex static ad
FLEX_AD = "6902283466075"   # 04-06-26_POWERBUG_STATICS_FLEX ADS_ MARCH 30 BATCH_flex
NEW_ADSETS = ["6909530076275", "6909530372475"]  # HiRise + PowerBug we just created

print("═══ Existing flex ad config ═══")
resp = _meta_request(
    "GET", f"{BASE_URL}/{FLEX_AD}",
    access_token=token,
    params={
        "access_token": token,
        "fields": "id,name,adset_id,adset{id,name,is_dynamic_creative},creative{id,asset_feed_spec{asset_customization_rules,images,videos,ad_formats}}",
    },
)
print(f"Ad: {resp.get('name')}")
adset = resp.get("adset", {}) or {}
print(f"Ad set: {adset.get('id')}  {adset.get('name')}  is_dynamic_creative={adset.get('is_dynamic_creative')}")
creative = resp.get("creative") or {}
afs = creative.get("asset_feed_spec") or {}
print(f"Creative: {creative.get('id')}")
print(f"  ad_formats: {afs.get('ad_formats')}")
print(f"  images: {len(afs.get('images') or [])}")
print(f"  asset_customization_rules: {json.dumps(afs.get('asset_customization_rules') or [], indent=2)[:800]}")

# Count ads in that ad set
if adset.get("id"):
    resp2 = _meta_request(
        "GET", f"{BASE_URL}/{adset['id']}/ads",
        access_token=token,
        params={"access_token": token, "fields": "id,name,effective_status", "limit": 50},
    )
    ads = resp2.get("data", [])
    print(f"  Ad set has {len(ads)} ads total:")
    for a in ads:
        print(f"    {a['id']}  {a.get('effective_status')}  {a.get('name','')[:70]}")

print("\n═══ Our newly created ad sets ═══")
for aid in NEW_ADSETS:
    resp = _meta_request(
        "GET", f"{BASE_URL}/{aid}",
        access_token=token,
        params={
            "access_token": token,
            "fields": "name,is_dynamic_creative,destination_type",
        },
    )
    print(f"  {aid}  is_dynamic_creative={resp.get('is_dynamic_creative')}  destination_type={resp.get('destination_type')}  {resp.get('name','')[:80]}")
    ads = _meta_request(
        "GET", f"{BASE_URL}/{aid}/ads",
        access_token=token,
        params={"access_token": token, "fields": "id,name,effective_status"},
    )
    for a in ads.get("data", []):
        print(f"    ad: {a['id']}  {a.get('effective_status')}  {a.get('name','')[:70]}")
