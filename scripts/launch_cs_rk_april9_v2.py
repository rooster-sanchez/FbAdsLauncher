#!/usr/bin/env python3
"""
One-off launch script: Christian Sexuality — Raising Kids (Batch 2)
Campaign: 04-01-26_MMS_ABO_TESTING
Date: 2026-04-09

1 ad set with 3 static PAC ads + 1 video ad
Same copy/headline/targeting as batch 1.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_all
from meta_api import (
    create_ad, create_ad_creative, create_adset, upload_image, upload_video,
    create_pac_creative, delete_object,
)

# ─── Config ──────────────────────────────────────────────────────────────────

CLIENT = "cs_christian_sexuality"
CAMPAIGN_ID = "120244383809380584"
LANDING_PAGE = "https://christian-sexuality.com/raising-kids/"
CTA = "LEARN_MORE"
DAILY_BUDGET_CENTS = 20000  # $200/day
ATTRIBUTION = "7d_click"

INCLUDE_AUDIENCES = [
    "120243181148690584",  # MMS_CS_IGCS_FOLLOWERS
    "120243181166930584",  # MMS_FBPAGE_FOLLOWERS
]
EXCLUDE_AUDIENCE = "120242687345410584"  # Raising Kids Past Purchasers

ADSET_NAME = "04-09-26_MMS_ABO_TESTING_CUSTOM_IGCS+FBPAGE_FOLLOWERS"

# ─── Files ───────────────────────────────────────────────────────────────────

DL = Path.home() / "Downloads"

STATIC_ADS = [
    ("RK_92Percent_PAC",          DL / "1.png",  DL / "9.png"),
    ("RK_75Percent_PAC",          DL / "2.png",  DL / "11.png"),
    ("RK_JackieHillPerry_PAC",    DL / "3.png",  DL / "13.png"),
]

VIDEO_FILE = DL / "video-JVv03jNWSCLWoG20O1At.mp4"

# ─── Ad Copy (same as batch 1) ──────────────────────────────────────────────

PRIMARY_TEXT = (
    "If your stomach knots up when your kids ask about bodies, sex, or the \u201cPride\u201d "
    "flags in your neighborhood, you aren\u2019t alone. Most of us are parenting from a "
    "place of silence\u2014only 8% of us had a helpful talk with our own parents."
    "\n\n"
    "You don\u2019t need to be a perfect expert; you just need to be their first teacher "
    "before the internet fills the void."
    "\n\n"
    "Raising Kids is the only video course that prepares YOU first. We help you "
    "process your own story so you can show up with a calm, gospel-confident tone "
    "that says, \u201cWe are not afraid of your questions\u201d."
    "\n\n"
    "Process Your Background: Heal from \u201cpurity culture\u201d wounds so you don\u2019t transmit them."
    "\n\n"
    "Own Your Posture: Learn why being \u201cinformal and receptive\u201d matters more than perfect words."
    "\n\n"
    "Get the Scripts: Learn how to answer your kids questions with truth and love."
    "\n\n"
    "This course is designed to give you real, practical, biblical wisdom from "
    "voices you trust. Including Preston and Jackie Hill Perry, Jon Tyson, John Mark "
    "Comer, Preston Sprinkle, Dan Allender, Julia Sadusky, and more."
    "\n\n"
    "Lead your kids through today\u2019s confusing world with clarity and confidence."
    "\n\n"
    "\U0001f3af 8 episodes of teaching + real-life stories to help you have the "
    "conversations that matter most."
    "\n\n"
    "Move from paralyzed to prepared today.\n"
    "GET ACCESS TO RAISING KIDS"
)

HEADLINE = "Be their first teacher"

UTM_TAGS = "utm_source=facebook_ads&utm_medium=paid&utm_campaign={{campaign.name}}&utm_content={{ad.name}}&utm_term={{adset.name}}"


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("CS Raising Kids — Launch Script (Batch 2)")
    print("=" * 60)

    config = load_all(CLIENT)
    print(f"Loaded config for {CLIENT}")
    print(f"Ad Account: act_{config['fb_ad_account_id']}")
    print(f"Page: {config['fb_page_id']}, IG: {config.get('instagram_user_id', 'NONE')}")

    created_objects = []

    try:
        # ── Step 1: Upload images ────────────────────────────────────────
        print("\n--- Uploading images ---")
        static_hashes = []
        for ad_name, f1x1, f9x16 in STATIC_ADS:
            print(f"  Uploading {ad_name} (1x1 + 9x16)")
            h1 = upload_image(config, str(f1x1))
            h2 = upload_image(config, str(f9x16))
            static_hashes.append((ad_name, h1, h2))

        # ── Step 2: Upload video ─────────────────────────────────────────
        print("\n--- Uploading video ---")
        video_id = upload_video(config, str(VIDEO_FILE))
        print(f"  Video ready: {video_id}")

        # ── Step 3: Create ad set ────────────────────────────────────────
        print("\n--- Creating ad set ---")
        targeting = {
            "geo_locations": {"countries": ["US"]},
            "age_min": 25,
            "age_max": 65,
            "custom_audiences": [{"id": aid} for aid in INCLUDE_AUDIENCES],
            "targeting_automation": {"advantage_audience": 0},
        }

        adset_id = create_adset(
            config,
            campaign_id=CAMPAIGN_ID,
            name=ADSET_NAME,
            targeting=targeting,
            daily_budget_cents=DAILY_BUDGET_CENTS,
            optimization_goal="OFFSITE_CONVERSIONS",
            billing_event="IMPRESSIONS",
            destination_url=LANDING_PAGE,
            status="PAUSED",
            attribution_window=ATTRIBUTION,
            exclusion_audience_ids=[EXCLUDE_AUDIENCE],
        )
        created_objects.append(("adset", adset_id, True))

        # ── Step 4: Create 3 static PAC ads ─────────────────────────────
        print("\n--- Creating static PAC ads ---")
        for ad_name, feed_hash, vertical_hash in static_hashes:
            media_refs = [
                {"type": "image", "ref": feed_hash},
                {"type": "image", "ref": vertical_hash},
            ]
            creative_id = create_pac_creative(
                config, ad_name, media_refs,
                headline=HEADLINE,
                primary_text=PRIMARY_TEXT,
                description="",
                destination_url=LANDING_PAGE,
                cta=CTA,
                url_tags=UTM_TAGS,
            )
            created_objects.append(("creative", creative_id, True))

            ad_id = create_ad(config, ad_name, adset_id, creative_id, status="PAUSED")
            created_objects.append(("ad", ad_id, True))
            print(f"  Ad created: {ad_name} ({ad_id})")

        # ── Step 5: Create video ad ─────────────────────────────────────
        print("\n--- Creating video ad ---")
        video_creative_id = create_ad_creative(
            config,
            name="RK_Video_Ad",
            media_type="video",
            media_ref=video_id,
            headline=HEADLINE,
            primary_text=PRIMARY_TEXT,
            description="",
            destination_url=LANDING_PAGE,
            cta=CTA,
            url_tags=UTM_TAGS,
        )
        created_objects.append(("creative", video_creative_id, True))

        video_ad_id = create_ad(
            config, "RK_Video_Ad", adset_id,
            video_creative_id, status="PAUSED",
        )
        created_objects.append(("ad", video_ad_id, True))
        print(f"  Video ad created: {video_ad_id}")

        # ── Summary ─────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("LAUNCH COMPLETE — ALL PAUSED")
        print("=" * 60)
        print(f"Campaign: 04-01-26_MMS_ABO_TESTING ({CAMPAIGN_ID})")
        print(f"Ad Set:   {ADSET_NAME} ({adset_id})")
        print(f"Budget:   $200/day")
        print(f"Targeting: US, 25-65, IGCS+FBPAGE followers, excl Raising Kids purchasers")
        print(f"Ads: 3 static PAC + 1 video = 4 ads total")
        print(f"Primary text: Copy 1 (long form)")
        print(f"Headline: {HEADLINE}")
        print(f"\nAll objects are PAUSED. Use activate_ads.py to go live.")

    except Exception as e:
        print(f"\nERROR: {e}")
        print(f"Created objects before failure: {created_objects}")
        if created_objects:
            print("Rolling back newly created objects...")
            for obj_type, obj_id, is_new in reversed(created_objects):
                if is_new:
                    try:
                        delete_object(config, obj_id)
                        print(f"  Deleted {obj_type} {obj_id}")
                    except Exception as re:
                        print(f"  Failed to delete {obj_type} {obj_id}: {re}")
        raise


if __name__ == "__main__":
    main()
