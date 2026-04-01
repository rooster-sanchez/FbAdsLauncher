#!/usr/bin/env python3
"""
Test API connections for fb-ads-launcher.
Verifies Meta API token, ad account access, page access, Instagram, pixel,
and Airtable API key.

Usage:
    python3 scripts/test_connection.py <client_slug>
"""

import sys
from pathlib import Path

# Add scripts dir to path for local imports
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all, validate_config
from preflight import (
    check_ad_account,
    check_airtable,
    check_instagram,
    check_meta_token,
    check_page,
    check_pixel,
    resolve_instagram,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/test_connection.py <client_slug>")
        sys.exit(1)

    client_slug = sys.argv[1]
    print(f"\nTesting connections for client: {client_slug}\n")

    try:
        config = load_all(client_slug)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Validate config completeness
    errors = validate_config(config)
    if errors:
        print("Config validation errors:")
        for err in errors:
            print(f"  - {err}")
        print()

    token = config["fb_access_token"]
    results = {}

    print("1. Meta Access Token")
    ok, msg = check_meta_token(token)
    print(f"  {msg}")
    results["meta_token"] = ok

    print("2. Ad Account")
    ok, msg = check_ad_account(token, config["fb_ad_account_id"])
    print(f"  {msg}")
    results["ad_account"] = ok

    print("3. Facebook Page")
    ok, msg = check_page(token, config["fb_page_id"])
    print(f"  {msg}")
    results["page"] = ok

    print("4. Instagram Account")
    # Try to resolve Instagram if not configured
    resolve_instagram(config)
    ok, msg = check_instagram(token, config["fb_page_id"], config.get("instagram_user_id", ""))
    print(f"  {msg}")
    results["instagram"] = ok

    print("5. Pixel")
    ok, msg = check_pixel(token, config.get("default_pixel_id", ""))
    print(f"  {msg}")
    results["pixel"] = ok

    print("6. Airtable API")
    ok, msg = check_airtable(config["airtable_api_key"], config["airtable_base_id"])
    print(f"  {msg}")
    results["airtable"] = ok

    print("\n--- Summary ---")
    all_ok = all(results.values())
    for name, ok in results.items():
        status = "OK" if ok else "FAIL"
        print(f"  {name}: {status}")

    if all_ok:
        print("\nAll connections verified. Ready to launch ads.")
    else:
        print("\nSome connections failed. Fix before running the launcher.")
        sys.exit(1)


if __name__ == "__main__":
    main()
