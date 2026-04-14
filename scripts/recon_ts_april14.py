#!/usr/bin/env python3
"""Recon for 12 South April 14 launch.

- Finds the active Testing campaign
- Lists custom audiences matching the standard_exclusions
- Pulls top-performing primary text + headline for HiRise and Power Bug
  from the last 30 days (by purchases → then by spend → fallback to most recent)
"""
import json
import sys
from pathlib import Path
from datetime import date, timedelta

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all
from meta_api import (
    BASE_URL, _meta_request, search_campaigns, get_custom_audiences,
)

config = load_all("ts_twelve_south")
token = config["fb_access_token"]
act = f"act_{config['fb_ad_account_id']}"

print("=" * 60)
print("1. Campaigns with 'Testing' in the name:")
print("=" * 60)
camps = search_campaigns(config, "Testing")
for c in camps:
    print(f"  {c['id']}  {c['status']}  {c['name']}  ({c.get('objective','')})")

# Also try common alt labels
for alt in ("ABO", "Flex"):
    print(f"\n-- Also '{alt}' --")
    for c in search_campaigns(config, alt):
        print(f"  {c['id']}  {c['status']}  {c['name']}  ({c.get('objective','')})")

print("\n" + "=" * 60)
print("2. Custom audiences (looking for Klaviyo/Shopify/Purchase):")
print("=" * 60)
auds = get_custom_audiences(config)
keywords = ("klaviyo", "shopify", "purchase", "customer")
for a in auds:
    name = a.get("name", "")
    if any(k in name.lower() for k in keywords):
        lo = a.get("approximate_count_lower_bound", "?")
        hi = a.get("approximate_count_upper_bound", "?")
        print(f"  {a['id']}  [{a.get('subtype','')}]  {name}  (~{lo}-{hi})")

print("\n" + "=" * 60)
print("3. Top-performing ads (last 30d) per product:")
print("=" * 60)
since = (date.today() - timedelta(days=30)).isoformat()
until = date.today().isoformat()

# Pull insights for the entire ad account, one row per ad
url = f"{BASE_URL}/{act}/insights"
params = {
    "access_token": token,
    "level": "ad",
    "time_range": json.dumps({"since": since, "until": until}),
    "fields": "ad_id,ad_name,spend,actions",
    "filtering": json.dumps([{"field": "spend", "operator": "GREATER_THAN", "value": "0"}]),
    "limit": 500,
}
ads_data = []
next_url = url
while next_url:
    resp = _meta_request("GET", next_url, access_token=token, params=params if next_url == url else None)
    ads_data.extend(resp.get("data", []))
    paging = resp.get("paging", {})
    next_url = paging.get("next", "")
    params = None  # already embedded in next URL

def purchases(row):
    for a in row.get("actions", []) or []:
        if a.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"):
            try:
                return int(float(a.get("value", 0)))
            except Exception:
                return 0
    return 0

def product_of(name: str) -> str:
    n = name.lower()
    if "hirise" in n or "hi-rise" in n or "higher rise" in n or "higher-rise" in n:
        return "HiRise"
    if "powerbug" in n or "power bug" in n or "power-bug" in n:
        return "PowerBug"
    return ""

buckets = {"HiRise": [], "PowerBug": []}
for row in ads_data:
    p = product_of(row.get("ad_name", ""))
    if not p:
        continue
    row["_purchases"] = purchases(row)
    row["_spend"] = float(row.get("spend") or 0)
    buckets[p].append(row)

def fetch_ad_copy(ad_id: str) -> dict:
    """Pull creative primary text + headline for an ad."""
    resp = _meta_request(
        "GET", f"{BASE_URL}/{ad_id}",
        access_token=token,
        params={
            "access_token": token,
            "fields": (
                "id,name,creative{"
                "object_story_spec{link_data{message,name,description},"
                "video_data{message,title,link_description}},"
                "asset_feed_spec{bodies,titles,descriptions}}"
            ),
        },
    )
    creative = resp.get("creative", {}) or {}
    out = {"body": "", "title": "", "desc": ""}

    afs = creative.get("asset_feed_spec") or {}
    if afs:
        bodies = afs.get("bodies") or []
        titles = afs.get("titles") or []
        descs = afs.get("descriptions") or []
        if bodies: out["body"] = bodies[0].get("text", "")
        if titles: out["title"] = titles[0].get("text", "")
        if descs: out["desc"] = descs[0].get("text", "")
    if not out["body"]:
        oss = creative.get("object_story_spec", {}) or {}
        ld = oss.get("link_data", {}) or {}
        vd = oss.get("video_data", {}) or {}
        out["body"] = ld.get("message", "") or vd.get("message", "")
        out["title"] = ld.get("name", "") or vd.get("title", "")
        out["desc"] = ld.get("description", "") or vd.get("link_description", "")
    return out

for product, rows in buckets.items():
    print(f"\n─── {product} ─── ({len(rows)} ads with spend)")
    if not rows:
        print("  No ads found with that product tag in the last 30d.")
        continue

    # Rank: purchases desc, then spend desc
    rows.sort(key=lambda r: (r["_purchases"], r["_spend"]), reverse=True)
    for r in rows[:5]:
        print(f"  {r['ad_id']}  purchases={r['_purchases']}  spend=${r['_spend']:.0f}  {r.get('ad_name','')[:80]}")

    top = rows[0]
    copy = fetch_ad_copy(top["ad_id"])
    print(f"\n  TOP WINNER → ad_id {top['ad_id']}")
    print(f"  Primary text:  {copy['body'][:300]}")
    print(f"  Headline:      {copy['title']}")
    print(f"  Description:   {copy['desc']}")

print("\nDone.")
