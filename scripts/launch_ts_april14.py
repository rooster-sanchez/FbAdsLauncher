#!/usr/bin/env python3
"""One-off launch: 12 South — April 14 HiRise + PowerBug testing batch.

Creates 2 ad sets in the existing Testing campaign (04-28_ABO_ALL_7DC_US_TESTING),
each $100/day, broad US, 7-day-click, with 5 standard exclusions applied.

Per ad set (3 ads each = 6 ads total):
  - 2 video ads (single-video, SHOP_NOW)
  - 1 multi-format static ad (1x1 + 9x16 via asset_feed_spec)
"""
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all
from meta_api import (
    create_adset, upload_image, upload_video,
    create_ad_creative, create_ad, delete_object, MetaApiError,
)
from targeting import build_targeting_spec

DRY_RUN = "--dry-run" in sys.argv

# ─── Brief ─────────────────────────────────────────────────────────────────
CLIENT_SLUG = "ts_twelve_south"
CAMPAIGN_ID = "6691799568075"   # 04-28_ABO_ALL_7DC_US_TESTING
DAILY_BUDGET_CENTS = 10000       # $100/day
ATTRIBUTION = "7d_click"
CTA = "SHOP_NOW"

EXCLUSION_AUDIENCE_IDS = [
    "6606781459475",  # Klaviyo - MMS - All clients all time
    "6301185183875",  # 12S - Purchases 180 Days
    "6802575466475",  # TS - Existing Customers Shopify Export (Aug 2025)
    "6576843032475",  # Shopify Export | Lapsed Customers 12M
    "6576842535475",  # Shopify Export | HV Lapsed Customers 12M
]

DOWNLOADS = Path.home() / "Downloads"

PRODUCTS = {
    "hirise": {
        "adset_name": "04-14-26_ABO_HIRISE3DELUXE_TSHANDLE_BROAD_VIDEOS+STATICS_7DC",
        "destination_url": "https://www.twelvesouth.com/products/hirise-3-deluxe",
        "headline": "The Perfect Charging Setup",
        "primary_text": (
            "Get the fastest possible wireless charging from one single outlet "
            "in a sleek, minimal footprint thanks to HiRise 3 Deluxe.\nSHOP NOW"
        ),
        "videos": [
            ("Copy%20of%20TS_HiRise%203%20Deluxe_VO_1.mp4",
             "04-14-26_HIRISE 3 DELUXE_VIDEO_TS_HIRISE 3 DELUXE_VO_1"),
            ("TS_HiRise%203%20Deluxe.mp4",
             "04-14-26_HIRISE 3 DELUXE_VIDEO_TS_HIRISE 3 DELUXE"),
        ],
        "statics": [
            "HiRise%203%20Deluxe%20UGC_1x1.jpg",
            "HiRise%203%20Deluxe%20UGC_9x16.jpg",
        ],
        "static_ad_name": "04-14-26_HIRISE 3 DELUXE_STATIC_FLEX_UGC",
    },
    "powerbug": {
        "adset_name": "04-14-26_ABO_POWERBUG_TSHANDLE_BROAD_VIDEOS+STATICS_7DC",
        "destination_url": "https://www.twelvesouth.com/products/powerbug",
        "headline": "RESTOCKED: PowerBug Wireless Charger",
        "primary_text": (
            '"I love that this keeps my phone off the counter - no cords! '
            'I love using it in the kitchen. I bought 9 more as stocking stuffers '
            'for my entire family!"\n\n'
            "Hands-free StandBy Mode, dual-device fast charging, and minimalist design"
            "\u2014all in one.  PowerBug is back in stock!\n\n"
            "Get yours before they sell out!"
        ),
        "videos": [
            ("TS_PowerBug.mp4", "04-14-26_POWERBUG_VIDEO_TS_POWERBUG"),
            ("TS_PowerBug_VO_2.mp4", "04-14-26_POWERBUG_VIDEO_TS_POWERBUG_VO_2"),
        ],
        "statics": [
            "UGC%20Static_1x1.jpg",
            "UGC%20Static_9x16.jpg",
        ],
        "static_ad_name": "04-14-26_POWERBUG_STATIC_FLEX_UGC",
    },
}

# ─── Load config ───────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"12 South — April 14 HiRise + PowerBug testing launch")
print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
print(f"{'='*60}")

print("\n1. Loading config...")
config = load_all(CLIENT_SLUG)
print(f"  Ad account: {config['fb_ad_account_id']}")
print(f"  Page: {config['fb_page_id']}")
print(f"  IG:   {config.get('instagram_user_id','N/A')}")
print(f"  Pixel: {config['default_pixel_id']}")

# Verify all creative files exist
print("\n2. Verifying creative files in ~/Downloads ...")
missing = []
for slug, p in PRODUCTS.items():
    for fname, _ in p["videos"]:
        fp = DOWNLOADS / fname
        if not fp.exists():
            missing.append(str(fp))
        else:
            print(f"  ✓ {fname}  ({fp.stat().st_size/1024/1024:.1f} MB)")
    for fname in p["statics"]:
        fp = DOWNLOADS / fname
        if not fp.exists():
            missing.append(str(fp))
        else:
            print(f"  ✓ {fname}  ({fp.stat().st_size/1024:.0f} KB)")
if missing:
    raise FileNotFoundError("Missing creative files:\n  " + "\n  ".join(missing))

# UTM url tags
utm_defaults = config.get("utm_defaults", {})
url_tags = "&".join(f"{k}={v}" for k, v in utm_defaults.items()) if utm_defaults else ""

# Rollback bookkeeping
created_objects = []  # list of (type, id) — deleted in reverse on failure

def rollback():
    print("\n⚠ Rollback: deleting created objects in reverse order")
    for kind, oid in reversed(created_objects):
        try:
            print(f"  Deleting {kind} {oid}...")
            delete_object(config, oid)
        except Exception as e:
            print(f"  ✗ Failed to delete {kind} {oid}: {e}")

try:
    # ─── Targeting (broad, US) ────────────────────────────────────────────
    print("\n3. Building targeting spec (broad, US)...")
    targeting = build_targeting_spec(config, {
        "targeting": "broad",
        "gender": "all",
        "age_range": "",
        "custom_audience_ids": "",
        "interest_keywords": "",
    })
    targeting.setdefault("targeting_automation", {"advantage_audience": 0})
    print(f"  Targeting: {json.dumps(targeting)}")

    # ─── Per-product processing ───────────────────────────────────────────
    summary = {}

    for slug, p in PRODUCTS.items():
        print(f"\n{'═'*60}")
        print(f"Product: {slug.upper()}")
        print(f"{'═'*60}")

        # Create ad set
        print(f"\n  a) Ad set: {p['adset_name']}")
        if DRY_RUN:
            adset_id = f"DRY_RUN_ADSET_{slug}"
            print(f"     [DRY RUN] would create ad set ${DAILY_BUDGET_CENTS/100:.0f}/day")
        else:
            adset_id = create_adset(
                config=config,
                campaign_id=CAMPAIGN_ID,
                name=p["adset_name"],
                targeting=targeting,
                daily_budget_cents=DAILY_BUDGET_CENTS,
                optimization_goal="OFFSITE_CONVERSIONS",
                billing_event="IMPRESSIONS",
                destination_url=p["destination_url"],
                status="PAUSED",
                is_dynamic_creative=False,
                attribution_window=ATTRIBUTION,
                exclusion_audience_ids=EXCLUSION_AUDIENCE_IDS,
            )
            created_objects.append(("adset", adset_id))

        # Upload videos
        print(f"\n  b) Uploading {len(p['videos'])} videos...")
        video_refs = []
        for fname, adname in p["videos"]:
            fp = DOWNLOADS / fname
            if DRY_RUN:
                print(f"     [DRY RUN] would upload {fname}")
                video_refs.append(("DRY_VIDEO_" + fname, adname))
            else:
                vid = upload_video(config, str(fp))
                video_refs.append((vid, adname))

        # Upload statics
        print(f"\n  c) Uploading {len(p['statics'])} statics...")
        image_hashes = []
        for fname in p["statics"]:
            fp = DOWNLOADS / fname
            if DRY_RUN:
                print(f"     [DRY RUN] would upload {fname}")
                image_hashes.append("DRY_IMG_" + fname)
            else:
                h = upload_image(config, str(fp))
                image_hashes.append(h)

        # Create 2 video ads
        print(f"\n  d) Creating {len(video_refs)} video ads...")
        ad_ids = []
        for vid, adname in video_refs:
            if DRY_RUN:
                print(f"     [DRY RUN] would create video ad: {adname}")
                ad_ids.append(("DRY_AD_" + adname, adname))
                continue
            creative_id = create_ad_creative(
                config=config,
                name=f"{adname}_creative",
                media_type="video",
                media_ref=vid,
                headline=p["headline"],
                primary_text=p["primary_text"],
                description="",
                destination_url=p["destination_url"],
                cta=CTA,
                url_tags=url_tags,
            )
            created_objects.append(("creative", creative_id))
            ad_id = create_ad(config, adname, adset_id, creative_id, status="PAUSED")
            created_objects.append(("ad", ad_id))
            ad_ids.append((ad_id, adname))

        # Create 1 multi-format static ad (1x1 primary + 9x16 additional)
        print(f"\n  e) Creating multi-format static ad: {p['static_ad_name']}")
        if DRY_RUN:
            print(f"     [DRY RUN] would create static flex ad with 2 images")
            ad_ids.append(("DRY_AD_STATIC", p["static_ad_name"]))
        else:
            primary_hash = image_hashes[0]
            additional = [{"type": "image", "ref": h} for h in image_hashes[1:]]
            creative_id = create_ad_creative(
                config=config,
                name=f"{p['static_ad_name']}_creative",
                media_type="image",
                media_ref=primary_hash,
                headline=p["headline"],
                primary_text=p["primary_text"],
                description="",
                destination_url=p["destination_url"],
                cta=CTA,
                additional_media_refs=additional,
                url_tags=url_tags,
            )
            created_objects.append(("creative", creative_id))
            ad_id = create_ad(config, p["static_ad_name"], adset_id, creative_id, status="PAUSED")
            created_objects.append(("ad", ad_id))
            ad_ids.append((ad_id, p["static_ad_name"]))

        summary[slug] = {"adset_id": adset_id, "ads": ad_ids}

    # ─── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Campaign: {CAMPAIGN_ID}  (04-28_ABO_ALL_7DC_US_TESTING)")
    for slug, s in summary.items():
        print(f"\n{slug.upper()}")
        print(f"  Ad set: {s['adset_id']}  (${DAILY_BUDGET_CENTS/100:.0f}/day, PAUSED)")
        for ad_id, adname in s["ads"]:
            print(f"    Ad: {ad_id}  {adname}")

    if not DRY_RUN:
        print(f"\nAll objects PAUSED. View in Ads Manager:")
        print(f"  https://adsmanager.facebook.com/adsmanager/manage/campaigns"
              f"?act={config['fb_ad_account_id']}&selected_campaign_ids={CAMPAIGN_ID}")
    print("\nDone.")

except Exception as e:
    print(f"\n✗ Launch failed: {e}")
    if not DRY_RUN and created_objects:
        rollback()
    raise
