#!/usr/bin/env python3
"""Launch 4 RD static PAC ads into a NEW ad set on the active RD campaign.

Campaign: 09/15 | RD | MMS | ABO | SALES OBJECTIVE  (120230007635780227)
Audience: LAL stack (29 lookalikes from launch_preferences.yml)
Budget:   $50/day
Exclusions: 4 standard RD audiences from launch_preferences.yml
Page/IG:  101621458315124 / 17841439232370747 (matches the live ad in the campaign)
Pixel:    877075395001496 (RD pixel)
Attribution: 7d click

Copy is taken from the top L30D performer in the campaign
(03-31-26_RD_THEPRIMALPATH_FLEX_RDCOURSE_TOP_PERFORMERS_30D ...).

4 ads x (1:1 + 9:16 via PAC), all PAUSED.
"""
import sys
import yaml
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all
from meta_api import (
    upload_image, create_pac_creative, create_ad,
    create_adset, delete_object,
)

DRY_RUN = "--dry-run" in sys.argv

CLIENT_SLUG = "rd_resilient_daughters"
CAMPAIGN_ID = "120230007635780227"
DOWNLOADS = Path.home() / "Downloads"
DATE = "04-14-26"

# Page + IG: standard RD setup — Jefferson Bethke page + @fatherscollective IG
# (matches fb_ads_config.json defaults; the token has full identity perms here).
# The active ad in this campaign uses Primal Path's IG (17841439232370747) but
# that IG is not authorised for creative creation with this token.
ADSET_PAGE_ID = "339101236109342"
ADSET_IG_ID = "17841411587000289"

ADSET_NAME = "04/14 | RD | MMS | ABO | STATIC | LAL STACK"
DAILY_BUDGET_CENTS = 5000  # $50/day
ATTRIBUTION = "7d_click"

CTA = "LEARN_MORE"
DESTINATION_URL = "https://my.formingmen.com/daughters"
HEADLINE = "Save Your Daughter's Future Today"
DESCRIPTION = ""
PRIMARY_TEXT = (
    "95% of ALL of the in-person time you'll get with your daughter will happen "
    "before she turns 18. Let that sink in.\n"
    "I remember the day I dropped her off at her dorm. I looked her in the eyes "
    "and said to her with all the confidence I could muster,\n"
    "\u201cDarling, listen to me. You\u2019ve got what it takes. You\u2019re gonna make it, "
    "here\u2019s the world, beautiful and terrible things will happen, don\u2019t be afraid.\u201d\n"
    "I'm telling you this because you've got something I don't have anymore, and "
    "you know what that is?\n"
    "You've got time.\n"
    "Time to build this relationship with your daughter, time to work on yourself "
    "as a man, time to build a plan and a path to love and raise her into the "
    "woman that God has called her to be in the world.\n"
    "And that's why I created this course, Resilient Daughters. It's the fruit of "
    "my journey with Haley, my years of research and insight of pastoring Church "
    "of the City in New York and is, I hope, a massively empowering resource for "
    "dads and serves the next generation of godly young women well. \n"
    "It's a 26-module, self-paced video course designed to be robust yet accessible.\n"
    "At the heart of this course is a 4-part framework that will focus your "
    "efforts where it counts: in building the kind of relationship your daughter "
    "needs to thrive.   \n"
    "You'll learn how to cultivate each of these 4 in your relationship with your "
    "daughter, no matter her age, stage or struggle.\n"
    "Connection: Creating emotional closeness and trust that withstands rebellion.\n"
    "Confidence: Helping her develop a secure sense of self and godly identity.\n"
    "Comfort: Being a safe place for her to turn to when she\u2019s facing fear or anxiety.\n"
    "Challenge: Guiding her to grow in resilience, competence, and strength.\n"
    "This framework equips you with practical, actionable strategies you can "
    "start putting into practice today.  \n"
    "95% of the time you'll get with your daughter will happen before she turns 18.\n"
    "Make the most of it.\n"
    "Get the course and start building resilience in your daughter today!"
)

# 4 creatives: each is a PAC pair [1x1, 9x16]
CREATIVES = [
    {
        "label": "MATT",
        "ad_name": f"{DATE}_RD_THEPRIMALPATH_STATIC_RDCOURSE_MATT_TESTIMONIAL_PLAYBOOK_HOMEPAGE_LEARN MORE_20%",
        "statics": ["%231.jpg", "%231-9x16.jpg"],
    },
    {
        "label": "JD",
        "ad_name": f"{DATE}_RD_THEPRIMALPATH_STATIC_RDCOURSE_JD_TESTIMONIAL_CONNECT_HOMEPAGE_LEARN MORE_20%",
        "statics": ["%232-1.jpg", "%232-9x16.jpg"],
    },
    {
        "label": "KEVIN",
        "ad_name": f"{DATE}_RD_THEPRIMALPATH_STATIC_RDCOURSE_KEVIN_TESTIMONIAL_TRANSFORMED_HOMEPAGE_LEARN MORE_20%",
        "statics": ["%233.jpg", "%233-9x16.jpg"],
    },
    {
        "label": "DANIEL",
        "ad_name": f"{DATE}_RD_THEPRIMALPATH_STATIC_RDCOURSE_DANIEL_TESTIMONIAL_HALFWAY_HOMEPAGE_LEARN MORE_20%",
        "statics": ["%234.jpg", "%234-9x16.jpg"],
    },
]


def load_prefs():
    p = Path(__file__).resolve().parent.parent / "clients" / CLIENT_SLUG / "launch_preferences.yml"
    with open(p) as f:
        return yaml.safe_load(f)


def main():
    prefs = load_prefs()
    lal_ids = [a["id"] for a in prefs["default_lookalike_audiences"]]
    excl_ids = [a["id"] for a in prefs["standard_exclusions"]]

    config = load_all(CLIENT_SLUG)
    # Pixel from prefs (RD's pixel; config already matches but be explicit)
    config["default_pixel_id"] = prefs.get("resilient_daughters_pixel_id", config["default_pixel_id"])
    # Override page/IG to match the page that owns this campaign's active ad
    adset_config = dict(config)
    adset_config["fb_page_id"] = ADSET_PAGE_ID
    adset_config["instagram_user_id"] = ADSET_IG_ID

    utm_defaults = config.get("utm_defaults", {})
    url_tags = "&".join(f"{k}={v}" for k, v in utm_defaults.items()) if utm_defaults else ""

    print(f"Mode:       {'DRY RUN' if DRY_RUN else 'LIVE'}")
    print(f"Campaign:   {CAMPAIGN_ID}  (09/15 | RD | MMS | ABO | SALES OBJECTIVE)")
    print(f"Ad set:     {ADSET_NAME}  ${DAILY_BUDGET_CENTS/100:.0f}/day")
    print(f"Page / IG:  {ADSET_PAGE_ID} / {ADSET_IG_ID}")
    print(f"Pixel:      {adset_config['default_pixel_id']}")
    print(f"LAL stack:  {len(lal_ids)} audiences")
    print(f"Exclusions: {len(excl_ids)} audiences")
    print(f"Ads:        {len(CREATIVES)} (each PAC: 1:1 + 9:16)\n")

    # Verify all files exist first
    for c in CREATIVES:
        for fname in c["statics"]:
            fp = DOWNLOADS / fname
            if not fp.exists():
                raise FileNotFoundError(f"Missing: {fp}")
    print("\u2713 All 8 image files found in ~/Downloads\n")

    targeting = {
        "geo_locations": {"countries": ["US"], "location_types": ["home", "recent"]},
        "age_min": 18,
        "age_max": 65,
        "custom_audiences": [{"id": aid} for aid in lal_ids],
    }

    created = []  # (kind, id) for rollback

    try:
        # 1. Create the ad set
        if DRY_RUN:
            print(f"[DRY] create ad set '{ADSET_NAME}' on {CAMPAIGN_ID}")
            adset_id = "DRY_ADSET"
        else:
            adset_id = create_adset(
                config=adset_config,
                campaign_id=CAMPAIGN_ID,
                name=ADSET_NAME,
                targeting=targeting,
                daily_budget_cents=DAILY_BUDGET_CENTS,
                optimization_goal="OFFSITE_CONVERSIONS",
                billing_event="IMPRESSIONS",
                status="PAUSED",
                attribution_window=ATTRIBUTION,
                exclusion_audience_ids=excl_ids,
            )
            created.append(("adset", adset_id))

        print()
        # 2. Upload images + create PAC creative + ad for each
        for c in CREATIVES:
            print(f"=== {c['label']} ===")
            hashes = []
            for fname in c["statics"]:
                fp = DOWNLOADS / fname
                if DRY_RUN:
                    print(f"  [DRY] upload {fname}")
                    hashes.append(f"DRY_{fname}")
                else:
                    hashes.append(upload_image(adset_config, str(fp)))

            media_refs = [{"type": "image", "ref": h} for h in hashes]

            if DRY_RUN:
                print(f"  [DRY] PAC creative + ad '{c['ad_name']}' \u2192 {adset_id}")
                continue

            creative_id = create_pac_creative(
                config=adset_config,
                name=f"{c['ad_name']}_creative",
                media_refs=media_refs,
                headline=HEADLINE,
                primary_text=PRIMARY_TEXT,
                description=DESCRIPTION,
                destination_url=DESTINATION_URL,
                cta=CTA,
                url_tags=url_tags,
            )
            created.append(("creative", creative_id))

            ad_id = create_ad(adset_config, c["ad_name"], adset_id, creative_id, status="PAUSED")
            created.append(("ad", ad_id))
            print(f"  \u2713 Ad {ad_id}  {c['label']}  \u2192  ad set {adset_id}")

        print(f"\n\u2713 {'Would create' if DRY_RUN else 'Created'} 1 ad set + {len(CREATIVES)} PAUSED ads.")

    except Exception as e:
        print(f"\n\u2717 Failed: {e}")
        if not DRY_RUN and created:
            print("Rolling back newly created objects...")
            for kind, oid in reversed(created):
                try:
                    delete_object(adset_config, oid)
                    print(f"  Deleted {kind} {oid}")
                except Exception as de:
                    print(f"  ! Could not delete {kind} {oid}: {de}")
        raise


if __name__ == "__main__":
    main()
