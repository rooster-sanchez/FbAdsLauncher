#!/usr/bin/env python3
"""Second recon pass:
1. Fetch exclusions from an active ABO ad set (canonical exclusion list)
2. Find any HiRise ad (regardless of spend) and pull its copy
"""
import json, sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all
from meta_api import BASE_URL, _meta_request

config = load_all("ts_twelve_south")
token = config["fb_access_token"]
act = f"act_{config['fb_ad_account_id']}"
TESTING_CAMPAIGN = "6691799568075"

print("=" * 60)
print(f"1. Ad sets in Testing campaign {TESTING_CAMPAIGN}")
print("=" * 60)
resp = _meta_request(
    "GET", f"{BASE_URL}/{TESTING_CAMPAIGN}/adsets",
    access_token=token,
    params={
        "access_token": token,
        "fields": "id,name,status,effective_status,daily_budget,excluded_custom_audiences,targeting",
        "limit": 50,
    },
)
adsets = resp.get("data", [])
# Sort by status so ACTIVE ones come first
adsets.sort(key=lambda a: (a.get("effective_status", "") != "ACTIVE", a.get("name", "")))
for a in adsets[:15]:
    print(f"  {a['id']}  {a.get('effective_status','')}  ${int(a.get('daily_budget','0'))/100:.0f}/d  {a.get('name','')[:80]}")

# Pick first active one and show its exclusions
active = next((a for a in adsets if a.get("effective_status") == "ACTIVE"), None)
if not active:
    active = adsets[0] if adsets else None

if active:
    print(f"\n  → Reading exclusions from ad set: {active['id']}  {active.get('name','')}")
    excl = active.get("excluded_custom_audiences") or []
    print(f"  Direct excluded_custom_audiences field ({len(excl)} audiences):")
    for e in excl:
        print(f"    {e.get('id')}  {e.get('name','')}")

    targeting = active.get("targeting") or {}
    excl_tgt = (targeting.get("exclusions") or {}).get("custom_audiences") or []
    print(f"  targeting.exclusions.custom_audiences ({len(excl_tgt)}):")
    for e in excl_tgt:
        print(f"    {e.get('id')}  {e.get('name','')}")

print("\n" + "=" * 60)
print("2. Any HiRise ads in the account (regardless of spend)")
print("=" * 60)
# Search ads by name
url = f"{BASE_URL}/{act}/ads"
params = {
    "access_token": token,
    "fields": "id,name,status,effective_status,created_time,adset{name,campaign{name}}",
    "filtering": json.dumps([{
        "field": "name",
        "operator": "CONTAIN",
        "value": "HiRise",
    }]),
    "limit": 100,
}
resp = _meta_request("GET", url, access_token=token, params=params)
ads = resp.get("data", [])
ads.sort(key=lambda a: a.get("created_time", ""), reverse=True)
for a in ads[:15]:
    camp_name = (a.get("adset") or {}).get("campaign", {}).get("name", "")
    print(f"  {a['id']}  {a.get('effective_status','')}  {a.get('created_time','')[:10]}  {a.get('name','')[:70]}  [{camp_name[:40]}]")

if ads:
    # Pull copy from the most recent HiRise ad
    top = ads[0]
    print(f"\n  → Reading copy from most recent HiRise ad: {top['id']}")
    cresp = _meta_request(
        "GET", f"{BASE_URL}/{top['id']}",
        access_token=token,
        params={
            "access_token": token,
            "fields": (
                "creative{object_story_spec{link_data{message,name,description},"
                "video_data{message,title,link_description}},"
                "asset_feed_spec{bodies,titles,descriptions}}"
            ),
        },
    )
    creative = cresp.get("creative", {}) or {}
    afs = creative.get("asset_feed_spec") or {}
    if afs:
        print(f"  asset_feed_spec bodies: {[b.get('text','')[:120] for b in (afs.get('bodies') or [])[:3]]}")
        print(f"  asset_feed_spec titles: {[t.get('text','') for t in (afs.get('titles') or [])[:3]]}")
        print(f"  asset_feed_spec descs:  {[d.get('text','') for d in (afs.get('descriptions') or [])[:3]]}")
    oss = creative.get("object_story_spec") or {}
    ld = oss.get("link_data") or {}
    vd = oss.get("video_data") or {}
    if ld or vd:
        print(f"  link_data.message:  {(ld.get('message') or '')[:300]}")
        print(f"  link_data.name:     {ld.get('name', '')}")
        print(f"  video_data.message: {(vd.get('message') or '')[:300]}")
        print(f"  video_data.title:   {vd.get('title', '')}")
        print(f"  video_data.link_description: {vd.get('link_description', '')}")

print("\nDone.")
