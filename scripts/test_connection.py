#!/usr/bin/env python3
"""
Test API connections for fb-ads-launcher.
Verifies Meta API token, ad account access, page access, and Airtable API key.

Usage:
    python3 agents/fb-ads-launcher/scripts/test_connection.py <client_slug>
"""

import sys

import requests

from config_loader import load_all, validate_config

META_API_VERSION = "v21.0"
META_BASE = f"https://graph.facebook.com/{META_API_VERSION}"


def test_meta_token(access_token: str) -> bool:
    """Verify the Meta access token is valid."""
    resp = requests.get(
        f"{META_BASE}/me",
        params={"access_token": access_token},
        timeout=15,
    )
    if resp.ok:
        data = resp.json()
        print(f"  Meta token valid — user: {data.get('name', data.get('id', 'unknown'))}")
        return True
    print(f"  Meta token INVALID [{resp.status_code}]: {resp.text[:200]}")
    return False


def test_ad_account(access_token: str, ad_account_id: str) -> bool:
    """Verify the ad account is accessible."""
    resp = requests.get(
        f"{META_BASE}/act_{ad_account_id}",
        params={"access_token": access_token, "fields": "name,account_status"},
        timeout=15,
    )
    if resp.ok:
        data = resp.json()
        print(f"  Ad account OK — {data.get('name', 'unnamed')} (status: {data.get('account_status')})")
        return True
    print(f"  Ad account FAILED [{resp.status_code}]: {resp.text[:200]}")
    return False


def test_page(access_token: str, page_id: str) -> bool:
    """Verify the Facebook Page is accessible."""
    if not page_id:
        print("  Page ID not configured — skipping")
        return False
    resp = requests.get(
        f"{META_BASE}/{page_id}",
        params={"access_token": access_token, "fields": "name,id"},
        timeout=15,
    )
    if resp.ok:
        data = resp.json()
        print(f"  Page OK — {data.get('name', 'unnamed')} ({data.get('id')})")
        return True
    print(f"  Page FAILED [{resp.status_code}]: {resp.text[:200]}")
    return False


def test_airtable(api_key: str, base_id: str) -> bool:
    """Verify the Airtable API key and base access."""
    if not api_key:
        print("  Airtable API key not configured — skipping")
        return False
    if not base_id:
        print("  Airtable base ID not configured — skipping")
        return False
    resp = requests.get(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    if resp.ok:
        tables = resp.json().get("tables", [])
        table_names = [t.get("name", "?") for t in tables]
        print(f"  Airtable OK — base has {len(tables)} table(s): {', '.join(table_names)}")
        return True
    print(f"  Airtable FAILED [{resp.status_code}]: {resp.text[:200]}")
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 agents/fb-ads-launcher/scripts/test_connection.py <client_slug>")
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

    results = {}

    print("1. Meta Access Token")
    results["meta_token"] = test_meta_token(config["fb_access_token"])

    print("2. Ad Account")
    results["ad_account"] = test_ad_account(config["fb_access_token"], config["fb_ad_account_id"])

    print("3. Facebook Page")
    results["page"] = test_page(config["fb_access_token"], config["fb_page_id"])

    print("4. Airtable API")
    results["airtable"] = test_airtable(config["airtable_api_key"], config["airtable_base_id"])

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
