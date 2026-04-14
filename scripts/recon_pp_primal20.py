#!/usr/bin/env python3
"""Recon for Primal Path PRIMAL20 launch.

1. Find ABO PP Sales campaign
2. List ACTIVE ad sets
3. Pull existing active ads' creatives + copy + URL
4. Pull last-30-day insights, identify top-performer by purchases / ROAS
"""
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all
from meta_api import _meta_request, search_campaigns, search_adsets, BASE_URL

CLIENT_SLUG = "pp_primal_path"
config = load_all(CLIENT_SLUG)
token = config["fb_access_token"]

print("═══ Finding campaign 'ABO PP Sales' ═══")
camps = search_campaigns(config, "PP")
for c in camps:
    print(f"  {c['id']}  {c['status']:10}  {c['name']}")

# The active sales campaign is 04-22_ABO_PP_SALES (id 120221445770860227)
SALES_CAMPAIGN_ID = "120221445770860227"
sales = [c for c in camps if c["id"] == SALES_CAMPAIGN_ID]
if not sales:
    print("No exact match for 'ABO PP Sales' — pick from above.")
    sys.exit(1)
campaign = sales[0]
print(f"\n→ Using campaign: {campaign['id']} ({campaign['status']}) {campaign['name']}")

print("\n═══ Ad sets in campaign ═══")
adsets = search_adsets(config, campaign["id"])
live_adsets = []
for a in adsets:
    budget = a.get("daily_budget")
    budget_str = f"${int(budget)/100:.0f}/day" if budget else "-"
    print(f"  {a['id']}  {a['status']:10}  {budget_str:10}  {a['name']}")
    if a["status"] == "ACTIVE":
        live_adsets.append(a)

print(f"\n→ {len(live_adsets)} ACTIVE ad sets")

# Fetch all ads in the campaign with creatives + insights
print("\n═══ Ads in campaign (ACTIVE only) ═══")
url = f"{BASE_URL}/{campaign['id']}/ads"
data = _meta_request(
    "GET", url, access_token=token,
    params={
        "access_token": token,
        "fields": "id,name,status,adset_id,creative{id,body,title,object_story_spec,asset_feed_spec,effective_object_story_id,link_url,object_url}",
        "effective_status": json.dumps(["ACTIVE"]),
        "limit": 200,
    },
)
ads = data.get("data", [])
print(f"Found {len(ads)} ACTIVE ads")

# Collect URLs + copy
urls_seen = {}
ad_copy_blocks = []
for ad in ads:
    c = ad.get("creative", {}) or {}
    oss = c.get("object_story_spec") or {}
    link_data = oss.get("link_data") or {}
    video_data = oss.get("video_data") or {}
    afs = c.get("asset_feed_spec") or {}

    # URL sources
    for u in [link_data.get("link"), video_data.get("link_destination"),
              video_data.get("call_to_action", {}).get("value", {}).get("link") if isinstance(video_data.get("call_to_action"), dict) else None,
              c.get("link_url"), c.get("object_url")]:
        if u:
            urls_seen[u] = urls_seen.get(u, 0) + 1

    # From asset_feed_spec (dynamic / PAC)
    if afs:
        for linkurl in (afs.get("link_urls") or []):
            u = linkurl.get("website_url")
            if u:
                urls_seen[u] = urls_seen.get(u, 0) + 1

    bodies = []
    titles = []
    descs = []
    if c.get("body"): bodies.append(c["body"])
    if c.get("title"): titles.append(c["title"])
    if link_data.get("message"): bodies.append(link_data["message"])
    if link_data.get("name"): titles.append(link_data["name"])
    if link_data.get("description"): descs.append(link_data["description"])
    if video_data.get("message"): bodies.append(video_data["message"])
    if video_data.get("title"): titles.append(video_data["title"])
    if afs:
        for b in (afs.get("bodies") or []):
            if b.get("text"): bodies.append(b["text"])
        for t in (afs.get("titles") or []):
            if t.get("text"): titles.append(t["text"])
        for d in (afs.get("descriptions") or []):
            if d.get("text"): descs.append(d["text"])

    ad_copy_blocks.append({
        "ad_id": ad["id"],
        "ad_name": ad["name"],
        "adset_id": ad["adset_id"],
        "bodies": bodies,
        "titles": titles,
        "descs": descs,
    })

print("\n═══ Destination URLs seen (count) ═══")
for u, n in sorted(urls_seen.items(), key=lambda x: -x[1]):
    print(f"  {n:3}×  {u}")

# Insights last 30 days — find top ad by purchases
print("\n═══ Last 30d insights — top ads by purchases ═══")
url = f"{BASE_URL}/{campaign['id']}/insights"
insights = _meta_request(
    "GET", url, access_token=token,
    params={
        "access_token": token,
        "level": "ad",
        "date_preset": "last_30d",
        "fields": "ad_id,ad_name,adset_id,spend,impressions,ctr,actions,action_values,purchase_roas",
        "limit": 500,
    },
).get("data", [])

rows = []
for row in insights:
    purchases = 0
    for a in (row.get("actions") or []):
        if a.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"):
            purchases = max(purchases, int(float(a.get("value", 0))))
    roas = 0.0
    for r in (row.get("purchase_roas") or []):
        roas = max(roas, float(r.get("value", 0)))
    rows.append({
        "ad_id": row.get("ad_id"),
        "ad_name": row.get("ad_name"),
        "spend": float(row.get("spend", 0)),
        "purchases": purchases,
        "roas": roas,
    })

rows.sort(key=lambda r: (-r["purchases"], -r["roas"]))
print(f"{'AD_ID':20} {'SPEND':>10} {'PURCH':>6} {'ROAS':>5}  NAME")
for r in rows[:15]:
    print(f"{r['ad_id'] or '-':20} {r['spend']:>10.2f} {r['purchases']:>6} {r['roas']:>5.2f}  {r['ad_name']}")

# Dump the top ad's full copy
print("\n═══ Top ad copy ═══")
if rows:
    top_ad_id = rows[0]["ad_id"]
    block = next((b for b in ad_copy_blocks if b["ad_id"] == top_ad_id), None)
    if block:
        print(f"Ad: {block['ad_name']}  ({top_ad_id})")
        print("\nBODIES:")
        for b in block["bodies"]: print(f"  --- \n{b}\n")
        print("\nTITLES:")
        for t in block["titles"]: print(f"  - {t}")
        print("\nDESCRIPTIONS:")
        for d in block["descs"]: print(f"  - {d}")
    else:
        # Fallback: fetch this specific ad's creative directly
        print(f"Top ad {top_ad_id} is not in the ACTIVE set — fetching copy directly")
        adurl = f"{BASE_URL}/{top_ad_id}"
        ad = _meta_request("GET", adurl, access_token=token, params={
            "access_token": token,
            "fields": "id,name,creative{id,body,title,object_story_spec,asset_feed_spec}",
        })
        print(json.dumps(ad, indent=2))

# Also list live adset IDs for the launch script
print("\n═══ LIVE AD SET IDs (copy into launch script) ═══")
for a in live_adsets:
    print(f'  "{a["id"]}",  # {a["name"]}')
