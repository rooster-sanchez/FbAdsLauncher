#!/usr/bin/env python3
"""
Activate Ads — Move PAUSED campaign/ad set/ads to ACTIVE.
Run this AFTER reviewing the created objects in Ads Manager.

Usage:
    python3 skills/fb-ads-launcher/scripts/activate_ads.py <client_slug> <campaign_id>
    python3 skills/fb-ads-launcher/scripts/activate_ads.py <client_slug> <campaign_id> --dry-run
"""

import argparse
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all, validate_config
from meta_api import get_ads_in_campaign, search_adsets, update_status


def main():
    parser = argparse.ArgumentParser(
        description="Activate PAUSED campaign, ad sets, and ads"
    )
    parser.add_argument("client_slug", help="Client slug (e.g., bc_bella_coterie)")
    parser.add_argument("campaign_id", help="Meta campaign ID to activate")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be activated without making changes")
    args = parser.parse_args()

    print(f"\nActivating campaign: {args.campaign_id}")
    print(f"Client: {args.client_slug}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}\n")

    config = load_all(args.client_slug)
    errors = validate_config(config)
    if errors:
        for err in errors:
            print(f"  ERROR: {err}")
        sys.exit(1)

    # Get all ad sets in campaign
    adsets = search_adsets(config, args.campaign_id)
    paused_adsets = [a for a in adsets if a.get("status") == "PAUSED"]

    # Get all ads in campaign
    ads = get_ads_in_campaign(config, args.campaign_id)
    paused_ads = [a for a in ads if a.get("status") == "PAUSED"]

    print(f"Found {len(paused_adsets)} paused ad set(s) and {len(paused_ads)} paused ad(s)\n")

    if not paused_adsets and not paused_ads:
        print("Nothing to activate.")
        return

    # Activate ads first, then ad sets, then campaign
    for ad in paused_ads:
        if args.dry_run:
            print(f"  [DRY RUN] Would activate ad: {ad['name']} ({ad['id']})")
        else:
            update_status(config, ad["id"], "ACTIVE")
            print(f"  Activated ad: {ad['name']} ({ad['id']})")

    for adset in paused_adsets:
        if args.dry_run:
            print(f"  [DRY RUN] Would activate ad set: {adset['name']} ({adset['id']})")
        else:
            update_status(config, adset["id"], "ACTIVE")
            print(f"  Activated ad set: {adset['name']} ({adset['id']})")

    # Activate campaign
    if args.dry_run:
        print(f"  [DRY RUN] Would activate campaign: {args.campaign_id}")
    else:
        update_status(config, args.campaign_id, "ACTIVE")
        print(f"  Activated campaign: {args.campaign_id}")

    print(f"\nDone. {len(paused_ads)} ad(s) and {len(paused_adsets)} ad set(s) are now ACTIVE.")


if __name__ == "__main__":
    main()
