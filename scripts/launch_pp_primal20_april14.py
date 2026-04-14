#!/usr/bin/env python3
"""Launch PRIMAL20 promo static ads for Primal Path — 04-14-26.

Targets 04-22_ABO_PP_SALES campaign:
  (1) Existing LAL_STACK ad set → 4 ads
  (2) New Broad (w/ exclusions) ad set → 4 ads  [created here, $100/day, PAUSED]

All ads use Jefferson Bethke page + @fatherscollective IG (per user direction).
Top-performing copy pulled from last-30d data. All ads PAUSED.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all
from meta_api import (
    upload_image, create_pac_creative, create_ad,
    create_adset, delete_object,
)

DRY_RUN = "--dry-run" in sys.argv
CLIENT_SLUG = "pp_primal_path"
CTA = "LEARN_MORE"
DOWNLOADS = Path.home() / "Downloads"
DATE = "04_14_26"

CAMPAIGN_ID = "120221445770860227"  # 04-22_ABO_PP_SALES
EXISTING_LAL_ADSET_ID = "120238521835520227"

# New broad ad set (matching LAL_STACK's settings)
NEW_BROAD_ADSET = {
    "name": "04-14-26 | Broad W/Exclusions | Primal Path | Best Performers",
    "daily_budget_cents": 10000,  # $100/day
    "optimization_goal": "OFFSITE_CONVERSIONS",
    "billing_event": "IMPRESSIONS",
    "attribution_window": "7d_click",
    "exclusion_audience_ids": [
        "120228275154410227",  # PP Customers - Updated August 7th 2025
        "120236483701190227",  # PRIMAL PATH - CUSTOMER LIST - UPDATED FEB 2026
    ],
    # Broad US, 18-65. Pixel is added automatically by create_adset (from config).
    "targeting": {
        "geo_locations": {"countries": ["US"], "location_types": ["home", "recent"]},
        "age_min": 18,
        "age_max": 65,
    },
}

# Top-performing copy (top purchase ad in campaign L30D)
HEADLINE = "Join Now and SAVE 20%"
DESCRIPTION = "A DISCIPLESHIP PROGRAM FOR FATHERS & SONS"
PRIMARY_TEXT = (
    "\u201cIf you don\u2019t disciple your son, somebody else will.\n"
    "Secular culture, his friends, the internet \u2014 don\u2019t hand the God-given influence "
    "you have in your son\u2019s life to someone else.\u201d\n"
    "\u201cWe want you to become one of the top 2 percent of dads in the world \u2014 a focused, "
    "passionate, intentional father with a vision to shape his sons.\u201d\n"
    "-Jon Tyson\n"
    "That's why we created the Primal Path. To give fathers the map, the model, and the "
    "milestones to disciple their sons with confidence.\n"
    "Your role as a father may be the greatest legacy of your life.\n"
    "Don\u2019t leave it to chance.\n"
    "Join The Primal Path today \u2014 and send your son into the world with your head held high.\n"
    "\u26a1 20% OFF LIMITED TIME OFFER\n"
    "\ud83d\udc49 Join the Journey at primalpath.co"
)
DESTINATION_URL = "https://primalpath.co/"

BASE_SUFFIX = "THEPRIMALPATH_STATIC_PPCOURSE_EMPOWERMENT_UNIQUE_BENEFIT_TESTIMONIAL_QUOTE_AI_HOME_PAGELP_LEARN_MORE_20%"

# 4 creatives: [1x1 first, 9x16 second] per PAC convention (FEED, VERTICAL)
CREATIVES = [
    {"label": "base",  "ad_name": f"{DATE}_PPATH_{BASE_SUFFIX}",       "statics": ["%231.jpg",   "%231-9x16.jpg"]},
    {"label": "ITE_1", "ad_name": f"{DATE}_PPATH_ITE_1_{BASE_SUFFIX}", "statics": ["%232-1.jpg", "%232-9x16.jpg"]},
    {"label": "ITE_2", "ad_name": f"{DATE}_PPATH_ITE_2_{BASE_SUFFIX}", "statics": ["%233.jpg",   "%233-9x16.jpg"]},
    {"label": "ITE_3", "ad_name": f"{DATE}_PPATH_ITE_3_{BASE_SUFFIX}", "statics": ["%234.jpg",   "%234-9x16.jpg"]},
]

config = load_all(CLIENT_SLUG)
# 100% Jefferson Bethke per user direction (config defaults: page 339101236109342, IG @fatherscollective 17841411587000289)
# No config override needed — defaults are correct.

utm_defaults = config.get("utm_defaults", {})
url_tags = "&".join(f"{k}={v}" for k, v in utm_defaults.items()) if utm_defaults else ""

print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
print(f"Campaign: 04-22_ABO_PP_SALES ({CAMPAIGN_ID})")
print(f"Identity: page={config['fb_page_id']}  ig={config['instagram_user_id']}  (Jefferson Bethke / @fatherscollective)")
print(f"Creatives: {len(CREATIVES)}")

# Verify files exist
for c in CREATIVES:
    for fname in c["statics"]:
        fp = DOWNLOADS / fname
        if not fp.exists():
            raise FileNotFoundError(f"Missing: {fp}")
print("\u2713 All 8 image files found in ~/Downloads\n")

created = []

try:
    # 1. Upload images once, reuse across both ad sets
    image_hashes_per_creative = {}
    for c in CREATIVES:
        print(f"═══ Upload {c['label']} ═══")
        hashes = []
        for fname in c["statics"]:
            fp = DOWNLOADS / fname
            if DRY_RUN:
                print(f"  [DRY] upload {fname}")
                hashes.append(f"DRY_{fname}")
            else:
                hashes.append(upload_image(config, str(fp)))
        image_hashes_per_creative[c["label"]] = hashes

    # 2. Create the new broad ad set
    print(f"\n═══ Create NEW broad ad set ═══")
    if DRY_RUN:
        print(f"  [DRY] create adset '{NEW_BROAD_ADSET['name']}' ${NEW_BROAD_ADSET['daily_budget_cents']/100:.0f}/day")
        new_adset_id = "DRY_NEW_BROAD"
    else:
        new_adset_id = create_adset(
            config=config,
            campaign_id=CAMPAIGN_ID,
            name=NEW_BROAD_ADSET["name"],
            targeting=dict(NEW_BROAD_ADSET["targeting"]),  # copy (function mutates)
            daily_budget_cents=NEW_BROAD_ADSET["daily_budget_cents"],
            optimization_goal=NEW_BROAD_ADSET["optimization_goal"],
            billing_event=NEW_BROAD_ADSET["billing_event"],
            attribution_window=NEW_BROAD_ADSET["attribution_window"],
            exclusion_audience_ids=NEW_BROAD_ADSET["exclusion_audience_ids"],
            destination_url=DESTINATION_URL,
            status="PAUSED",
        )
        created.append(("adset", new_adset_id))

    # 3. Attach 4 ads to each of the 2 ad sets (existing LAL + new Broad)
    targets = [
        (EXISTING_LAL_ADSET_ID, "LAL_STACK"),
        (new_adset_id,          "BROAD_EXCL"),
    ]
    for adset_id, adset_label in targets:
        print(f"\n═══ Ad set: {adset_label} ({adset_id}) ═══")
        for c in CREATIVES:
            hashes = image_hashes_per_creative[c["label"]]
            media_refs = [{"type": "image", "ref": h} for h in hashes]

            if DRY_RUN:
                print(f"  [DRY] PAC creative + ad '{c['ad_name']}' → {adset_id}")
                continue

            creative_id = create_pac_creative(
                config=config,
                name=f"{c['ad_name']}_{adset_label}_creative",
                media_refs=media_refs,
                headline=HEADLINE,
                primary_text=PRIMARY_TEXT,
                description=DESCRIPTION,
                destination_url=DESTINATION_URL,
                cta=CTA,
                url_tags=url_tags,
            )
            created.append(("creative", creative_id))

            ad_id = create_ad(config, c["ad_name"], adset_id, creative_id, status="PAUSED")
            created.append(("ad", ad_id))
            print(f"  \u2713 Ad {ad_id}  {c['label']}  \u2192  {adset_label}")

    total_ads = len(targets) * len(CREATIVES)
    print(f"\n\u2713 {'Would create' if DRY_RUN else 'Created'} 1 new ad set + {total_ads} PAUSED ads.")

except Exception as e:
    print(f"\n\u2717 Failed: {e}")
    if not DRY_RUN and created:
        print("Rolling back newly created objects...")
        for kind, oid in reversed(created):
            try:
                delete_object(config, oid)
                print(f"  Deleted {kind} {oid}")
            except Exception as de:
                print(f"  ! Could not delete {kind} {oid}: {de}")
    raise
