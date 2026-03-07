#!/usr/bin/env python3
"""
List Custom Audiences — Shows all custom/lookalike audiences in an ad account.
Use this to find audience IDs for the ClickUp brief's lookalike targeting.

Usage:
    python3 skills/fb-ads-launcher/scripts/list_custom_audiences.py <client_slug>
    python3 skills/fb-ads-launcher/scripts/list_custom_audiences.py <client_slug> --filter lookalike
"""

import argparse
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all
from meta_api import get_custom_audiences


def main():
    parser = argparse.ArgumentParser(
        description="List custom/lookalike audiences in a client's ad account"
    )
    parser.add_argument("client_slug", help="Client slug (e.g., bc_bella_coterie)")
    parser.add_argument("--filter", help="Filter by subtype (e.g., 'lookalike', 'custom')",
                        default="")
    args = parser.parse_args()

    config = load_all(args.client_slug)
    print(f"\nCustom audiences for: {args.client_slug}")
    print(f"Ad account: {config['fb_ad_account_id']}\n")

    audiences = get_custom_audiences(config)

    if args.filter:
        audiences = [
            a for a in audiences
            if args.filter.lower() in (a.get("subtype", "") or "").lower()
        ]

    if not audiences:
        print("No audiences found.")
        return

    print(f"{'ID':<25} {'Subtype':<15} {'Size':<12} Name")
    print("-" * 80)
    for aud in audiences:
        size = aud.get("approximate_count", 0)
        size_str = f"{size:,}" if size else "N/A"
        print(f"{aud['id']:<25} {aud.get('subtype', 'N/A'):<15} {size_str:<12} {aud['name']}")

    print(f"\nTotal: {len(audiences)} audience(s)")
    print("\nTo use in ClickUp brief, copy the ID(s) into the 'custom_audience_ids' field.")


if __name__ == "__main__":
    main()
