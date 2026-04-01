#!/usr/bin/env python3
"""One-off launch: Forming Men Churches — Pastors Challenge flex ad.

Creates a new dynamic ad set in the existing Churches campaign,
uploads all creatives from Airtable record recktZszNVoDPA2Zr,
and creates a single flex ad combining all images + text variants.

Campaign: 120237071689720227 (CBO, OUTCOME_LEADS)
"""

import json
import os
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all
from airtable_reader import download_attachment, write_ad_meta_id, _get_record, _patch_record
from meta_api import (
    _meta_request, BASE_URL, create_ad, create_ad_creative,
    upload_image, detect_media_type, MetaApiError,
)
from targeting import build_targeting_spec

DRY_RUN = "--dry-run" in sys.argv

# ─── Config ──────────────────────────────────────────────────────────────────

CLIENT_SLUG = "fm_forming_men"
CAMPAIGN_ID = "120237071689720227"
AD_RECORD_ID = "recktZszNVoDPA2Zr"
DESTINATION_URL = "https://manyear.mykajabi.com/challenge-based-discipleship-playbook"
CTA = "LEARN_MORE"
ATTRIBUTION_WINDOW = "7d_click"
ADSET_NAME = "03-31-26 | Broad | CHALLENGE BASED DISCIPLESHIP | Churches"

# ─── Load config ─────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"FM Churches — Pastors Challenge Flex Ad Launch")
print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
print(f"{'='*60}")

print("\n1. Loading config...")
config = load_all(CLIENT_SLUG)
print(f"  Ad account: {config['fb_ad_account_id']}")
print(f"  Page: {config['fb_page_id']}")
print(f"  IG: {config.get('instagram_user_id', 'N/A')}")
print(f"  Pixel: {config['default_pixel_id']}")

# ─── Read Airtable record ───────────────────────────────────────────────────

print("\n2. Reading Airtable ad record...")
record = _get_record(
    config["airtable_base_id"],
    config["airtable_ads_table_id"],
    AD_RECORD_ID,
    config["airtable_api_key"],
)
fields = record.get("fields", {})

ad_name = fields.get("1. Ad Name", "FM Churches Flex")
headline = fields.get("4. Headline 1", "")
primary_text_1 = fields.get("7. Primary Text 1", "")
primary_text_2 = fields.get("8. Primary Text 2", "")
attachments_raw = fields.get("3. Ad Creative", [])

headlines = [h for h in [headline] if h]
primary_texts = [pt for pt in [primary_text_1, primary_text_2] if pt]

print(f"  Ad: {ad_name}")
print(f"  Headlines: {len(headlines)}")
print(f"  Primary texts: {len(primary_texts)}")
print(f"  Creatives: {len(attachments_raw)} files")
for att in attachments_raw:
    print(f"    - {att['filename']} ({att['width']}x{att['height']})")

# ─── Build targeting ─────────────────────────────────────────────────────────

print("\n3. Building targeting spec...")
targeting = build_targeting_spec(config, {
    "targeting": "broad",
    "gender": "all",
    "age_range": "",
    "custom_audience_ids": "",
    "interest_keywords": "",
})
targeting.setdefault("targeting_automation", {"advantage_audience": 0})
print(f"  Targeting: {json.dumps(targeting, indent=2)}")

# ─── Create ad set ───────────────────────────────────────────────────────────

print("\n4. Creating ad set...")
print(f"  Campaign: {CAMPAIGN_ID}")
print(f"  Name: {ADSET_NAME}")
print(f"  Optimization: OFFSITE_CONVERSIONS (LEAD)")
print(f"  Attribution: {ATTRIBUTION_WINDOW}")
print(f"  Dynamic creative: true")

if DRY_RUN:
    print(f"  [DRY RUN] Would create ad set")
    adset_id = "DRY_RUN_ADSET"
else:
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/adsets"

    payload = {
        "name": ADSET_NAME,
        "campaign_id": CAMPAIGN_ID,
        "optimization_goal": "OFFSITE_CONVERSIONS",
        "billing_event": "IMPRESSIONS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "targeting": json.dumps(targeting),
        "status": "PAUSED",
        "is_dynamic_creative": "true",
        "access_token": config["fb_access_token"],
        "promoted_object": json.dumps({
            "pixel_id": config["default_pixel_id"],
            "custom_event_type": "LEAD",
        }),
        "attribution_spec": json.dumps([
            {"event_type": "CLICK_THROUGH", "window_days": 7},
        ]),
    }
    # CBO campaign — do NOT set daily_budget (Meta rejects it)

    data = _meta_request("POST", url, access_token=config["fb_access_token"], data=payload)
    adset_id = data.get("id")
    if not adset_id:
        raise MetaApiError(f"No ad set ID returned: {data}")
    print(f"  Created ad set: {adset_id}")

# ─── Download + upload creatives ─────────────────────────────────────────────

print("\n5. Uploading creatives...")
download_dir = tempfile.mkdtemp(prefix="fm-churches-flex-")
media_refs = []

for att in attachments_raw:
    filename = att["filename"]
    media_type = detect_media_type(filename)
    print(f"  Downloading: {filename}")

    if DRY_RUN:
        print(f"    [DRY RUN] Would upload {media_type}")
        media_refs.append({"type": media_type, "ref": f"DRY_RUN_{filename}"})
        continue

    local_path = download_attachment(
        att["url"], download_dir, filename, config["airtable_api_key"]
    )
    ref = upload_image(config, local_path)
    media_refs.append({"type": "image", "ref": ref})
    print(f"    Uploaded: hash={ref}")

# ─── Create flex creative ────────────────────────────────────────────────────

print("\n6. Creating flex creative...")
print(f"  Images: {len(media_refs)}")
print(f"  Headlines: {headlines}")
print(f"  Primary texts: {len(primary_texts)} variations")
print(f"  URL: {DESTINATION_URL}")
print(f"  CTA: {CTA}")

# Build UTM tags
utm_defaults = config.get("utm_defaults", {})
url_tags = "&".join(f"{k}={v}" for k, v in utm_defaults.items()) if utm_defaults else ""

if DRY_RUN:
    print(f"  [DRY RUN] Would create flex creative + ad")
    creative_id = "DRY_RUN_CREATIVE"
    ad_id = "DRY_RUN_AD"
else:
    creative_name = f"{ADSET_NAME}_flex_creative"
    creative_id = create_ad_creative(
        config,
        name=creative_name,
        media_type="image",
        media_ref=media_refs[0]["ref"],
        headline=headlines,
        primary_text=primary_texts,
        description="",
        destination_url=DESTINATION_URL,
        cta=CTA,
        additional_media_refs=media_refs[1:],
        url_tags=url_tags,
    )
    print(f"  Creative ID: {creative_id}")

    # Create the ad
    full_ad_name = f"{ADSET_NAME}_flex"
    ad_id = create_ad(config, full_ad_name, adset_id, creative_id)
    print(f"  Ad ID: {ad_id}")

    # Write Meta Ad ID back to Airtable
    write_ad_meta_id(AD_RECORD_ID, ad_id, config)

# ─── Summary ─────────────────────────────────────────────────────────────────

ads_manager_url = (
    f"https://adsmanager.facebook.com/adsmanager/manage/campaigns"
    f"?act={config['fb_ad_account_id']}"
)

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
print(f"Campaign: {CAMPAIGN_ID}")
print(f"Ad Set: {adset_id}")
print(f"Ad: {ad_id}")
print(f"Creative: {creative_id}")
print(f"Images: {len(media_refs)}")
print(f"Headlines: {len(headlines)}")
print(f"Primary texts: {len(primary_texts)}")
print(f"Status: PAUSED")
print(f"URL: {DESTINATION_URL}")
if not DRY_RUN:
    print(f"\nView in Ads Manager: {ads_manager_url}")
print("\nDone.")
