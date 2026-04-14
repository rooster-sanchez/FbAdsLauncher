#!/usr/bin/env python3
"""Follow-up: add the 2 missing multi-format static ads using PAC.

Attaches to the already-created ad sets. Uses create_pac_creative so the
existing 2 video ads per ad set remain (non-dynamic ad set).
"""
import sys
from pathlib import Path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all
from meta_api import upload_image, create_pac_creative, create_ad, delete_object

DRY_RUN = "--dry-run" in sys.argv

CLIENT_SLUG = "ts_twelve_south"
CTA = "SHOP_NOW"
DOWNLOADS = Path.home() / "Downloads"

PRODUCTS = {
    "hirise": {
        "adset_id": "6909530076275",
        "ad_name": "04-14-26_HIRISE 3 DELUXE_STATIC_FLEX_UGC",
        "destination_url": "https://www.twelvesouth.com/products/hirise-3-deluxe",
        "headline": "The Perfect Charging Setup",
        "primary_text": (
            "Get the fastest possible wireless charging from one single outlet "
            "in a sleek, minimal footprint thanks to HiRise 3 Deluxe.\nSHOP NOW"
        ),
        # PAC order: [FEED (1x1), VERTICAL (9x16)]
        "statics": [
            "HiRise%203%20Deluxe%20UGC_1x1.jpg",
            "HiRise%203%20Deluxe%20UGC_9x16.jpg",
        ],
    },
    "powerbug": {
        "adset_id": "6909530372475",
        "ad_name": "04-14-26_POWERBUG_STATIC_FLEX_UGC",
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
        "statics": [
            "UGC%20Static_1x1.jpg",
            "UGC%20Static_9x16.jpg",
        ],
    },
}

config = load_all(CLIENT_SLUG)
utm_defaults = config.get("utm_defaults", {})
url_tags = "&".join(f"{k}={v}" for k, v in utm_defaults.items()) if utm_defaults else ""

print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")

created = []

try:
    for slug, p in PRODUCTS.items():
        print(f"\n═══ {slug.upper()} ═══")
        # Upload both images
        hashes = []
        for fname in p["statics"]:
            fp = DOWNLOADS / fname
            if not fp.exists():
                raise FileNotFoundError(f"Missing: {fp}")
            if DRY_RUN:
                print(f"  [DRY] upload {fname}")
                hashes.append("DRY_" + fname)
            else:
                hashes.append(upload_image(config, str(fp)))

        media_refs = [{"type": "image", "ref": h} for h in hashes]

        if DRY_RUN:
            print(f"  [DRY] create PAC creative + ad '{p['ad_name']}' in {p['adset_id']}")
            continue

        creative_id = create_pac_creative(
            config=config,
            name=f"{p['ad_name']}_creative",
            media_refs=media_refs,
            headline=p["headline"],
            primary_text=p["primary_text"],
            description="",
            destination_url=p["destination_url"],
            cta=CTA,
            url_tags=url_tags,
        )
        created.append(("creative", creative_id))

        ad_id = create_ad(config, p["ad_name"], p["adset_id"], creative_id, status="PAUSED")
        created.append(("ad", ad_id))
        print(f"  ✓ Ad {ad_id}  {p['ad_name']}  →  ad set {p['adset_id']}")

    print("\nAll missing static ads created.")

except Exception as e:
    print(f"\n✗ Failed: {e}")
    if not DRY_RUN and created:
        print("Rolling back newly created objects...")
        for kind, oid in reversed(created):
            try:
                delete_object(config, oid)
                print(f"  Deleted {kind} {oid}")
            except Exception as de:
                print(f"  ! Could not delete {kind} {oid}: {de}")
    raise
