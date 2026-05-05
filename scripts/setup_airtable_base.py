#!/usr/bin/env python3
from __future__ import annotations
"""
Set up an Airtable base for a client with the Ad Launcher table structure.

Your token can't create bases, so create an empty base in the Airtable UI first,
then run this script to populate it with the right tables and fields.

Usage:
    python3 scripts/setup_airtable_base.py appXXXXXXXX

    # If you already have the base set up, just print the IDs:
    python3 scripts/setup_airtable_base.py appXXXXXXXX --info
"""

import argparse
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
# Load root .env from repo root (scripts/ is at scripts/, repo root is 3 up)
_root_env = os.path.join(SCRIPTS_DIR, "..", "..", "..", ".env")
if os.path.exists(_root_env):
    load_dotenv(_root_env)
else:
    load_dotenv()

AIRTABLE_API = "https://api.airtable.com/v0"


def _headers():
    api_key = os.getenv("AIRTABLE_API_KEY", "")
    if not api_key:
        print("ERROR: AIRTABLE_API_KEY not found in .env")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _post(endpoint: str, data: dict) -> dict:
    resp = requests.post(
        f"{AIRTABLE_API}{endpoint}",
        headers=_headers(),
        json=data,
        timeout=30,
    )
    if not resp.ok:
        print(f"API error [{resp.status_code}]: {resp.text[:500]}")
        sys.exit(1)
    return resp.json()


def _get(endpoint: str) -> dict:
    resp = requests.get(
        f"{AIRTABLE_API}{endpoint}",
        headers=_headers(),
        timeout=15,
    )
    if not resp.ok:
        print(f"API error [{resp.status_code}]: {resp.text[:300]}")
        sys.exit(1)
    return resp.json()


def get_existing_tables(base_id: str) -> list[dict]:
    """Get existing tables in a base."""
    data = _get(f"/meta/bases/{base_id}/tables")
    return data.get("tables", [])


def create_table(base_id: str, name: str, fields: list[dict]) -> dict:
    """Create a table in an existing base."""
    payload = {"name": name, "fields": fields}
    print(f"  Creating table: {name}...")
    return _post(f"/meta/bases/{base_id}/tables", payload)


def add_field(base_id: str, table_id: str, field: dict) -> dict:
    """Add a field to an existing table."""
    print(f"    Adding field: {field['name']}...")
    return _post(f"/meta/bases/{base_id}/tables/{table_id}/fields", field)


AD_SETS_FIELDS = [
    {"name": "4. Ad Set Name", "type": "singleLineText"},
    {
        "name": "1. Campaign",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "New", "color": "greenLight2"},
                {"name": "Existing", "color": "blueLight2"},
            ]
        },
    },
    {
        "name": "2. Campaign Name",
        "type": "singleSelect",
        "options": {"choices": []},
    },
    {
        "name": "5. Existing Ad Set Name",
        "type": "singleSelect",
        "options": {"choices": []},
    },
    {
        "name": "6. Daily Budget",
        "type": "currency",
        "options": {"precision": 0, "symbol": "$"},
    },
    {
        "name": "7. Targeting Type",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "Broad", "color": "greenLight2"},
                {"name": "Lookalikes", "color": "blueLight2"},
                {"name": "Interest", "color": "purpleLight2"},
            ]
        },
    },
    {"name": "8. Age Range", "type": "singleLineText"},
    {
        "name": "9. Gender",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "All", "color": "grayLight2"},
                {"name": "Women", "color": "pinkLight2"},
                {"name": "Men", "color": "blueLight2"},
            ]
        },
    },
    {"name": "10. Custom Audience IDs", "type": "multilineText"},
    {
        "name": "10. Custom Audiences",
        "type": "multipleSelects",
        "options": {"choices": []},
    },
    {"name": "11. Interest Keywords", "type": "multilineText"},
    {"name": "12. Destination URL", "type": "url"},
    {
        "name": "13. CTA",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "SHOP_NOW", "color": "greenLight2"},
                {"name": "LEARN_MORE", "color": "blueLight2"},
                {"name": "SIGN_UP", "color": "purpleLight2"},
                {"name": "SUBSCRIBE", "color": "tealLight2"},
                {"name": "GET_OFFER", "color": "yellowLight2"},
                {"name": "BOOK_NOW", "color": "orangeLight2"},
                {"name": "CONTACT_US", "color": "redLight2"},
                {"name": "DOWNLOAD", "color": "cyanLight2"},
                {"name": "APPLY_NOW", "color": "pinkLight2"},
                {"name": "ORDER_NOW", "color": "greenLight2"},
                {"name": "BUY_NOW", "color": "blueLight2"},
                {"name": "WATCH_MORE", "color": "grayLight2"},
                {"name": "NO_BUTTON", "color": "grayLight2"},
            ]
        },
    },
    {
        "name": "14. Attribution Window",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "7d_click_1d_view", "color": "blueLight2"},
                {"name": "7d_click", "color": "cyanLight2"},
                {"name": "1d_click_1d_view", "color": "tealLight2"},
                {"name": "1d_click", "color": "greenLight2"},
            ]
        },
    },
    {
        "name": "15. Status",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "Draft", "color": "grayLight2"},
                {"name": "Creative Review", "color": "yellowLight2"},
                {"name": "Client Review", "color": "orangeLight2"},
                {"name": "Approved", "color": "greenLight2"},
                {"name": "Ready to Launch", "color": "blueLight2"},
                {"name": "Launched", "color": "purpleLight2"},
            ]
        },
    },
    {"name": "Notes", "type": "multilineText"},
    {"name": "Meta Campaign ID", "type": "singleLineText"},
    {"name": "Meta Ad Set IDs", "type": "multilineText"},
    {"name": "16. Launch Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
    {
        "name": "17. Exclusion Audiences",
        "type": "multipleSelects",
        "options": {"choices": []},
    },
]

ADS_FIELDS = [
    {"name": "1. Ad Name", "type": "singleLineText"},
    {"name": "3. Ad Creative", "type": "multipleAttachments"},
    {"name": "4. Headline 1", "type": "multilineText"},
    {"name": "5. Headline 2", "type": "multilineText"},
    {"name": "6. Headline 3", "type": "multilineText"},
    {"name": "7. Primary Text 1", "type": "multilineText"},
    {"name": "8. Primary Text 2", "type": "multilineText"},
    {"name": "9. Primary Text 3", "type": "multilineText"},
    {"name": "Description", "type": "multilineText"},
    {
        "name": "2. Ad Format",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "Single Image/Video", "color": "blueLight2"},
                {"name": "Multi-Placement", "color": "purpleLight2"},
                {"name": "Carousel", "color": "tealLight2"},
                {"name": "Flexible", "color": "orangeLight2"},
            ]
        },
    },
    {
        "name": "10. Status",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "Draft", "color": "grayLight2"},
                {"name": "In Review", "color": "yellowLight2"},
                {"name": "Needs Changes", "color": "redLight2"},
                {"name": "Approved", "color": "greenLight2"},
            ]
        },
    },
    {"name": "Meta Ad ID", "type": "singleLineText"},
]


def print_config(base_id: str, adsets_table_id: str, ads_table_id: str):
    """Print the config snippet for fb_ads_config.json."""
    print(f"\n{'='*60}")
    print("Add these to your client's fb_ads_config.json:")
    print(f"{'='*60}")
    config_snippet = {
        "airtable_base_id": base_id,
        "airtable_ad_sets_table_id": adsets_table_id,
        "airtable_ads_table_id": ads_table_id,
    }
    print(json.dumps(config_snippet, indent=2))
    print(f"\nBase URL: https://airtable.com/{base_id}")


def setup_base(base_id: str):
    """Create Ad Sets and Ads tables in an existing base."""
    # Check existing tables
    existing = get_existing_tables(base_id)
    existing_names = {t["name"] for t in existing}

    print(f"\nBase {base_id} has {len(existing)} existing table(s): {', '.join(existing_names) or 'none'}")

    # Create Ad Sets table
    if "Ad Sets" in existing_names:
        print("\n  'Ad Sets' table already exists — skipping creation")
        adsets_table = next(t for t in existing if t["name"] == "Ad Sets")
        adsets_table_id = adsets_table["id"]
    else:
        print("\n  Creating 'Ad Sets' table...")
        result = create_table(base_id, "Ad Sets", AD_SETS_FIELDS)
        adsets_table_id = result["id"]
        print(f"  Created: {adsets_table_id}")

    time.sleep(0.3)

    # Create Ads table
    if "Ads" in existing_names:
        print("\n  'Ads' table already exists — skipping creation")
        ads_table = next(t for t in existing if t["name"] == "Ads")
        ads_table_id = ads_table["id"]
    else:
        print("\n  Creating 'Ads' table...")
        result = create_table(base_id, "Ads", ADS_FIELDS)
        ads_table_id = result["id"]
        print(f"  Created: {ads_table_id}")

    time.sleep(0.3)

    # Add linked record field (Ad Sets → Ads)
    # Check if it already exists
    adsets_table_data = next(
        (t for t in get_existing_tables(base_id) if t["id"] == adsets_table_id), {}
    )
    existing_field_names = {f["name"] for f in adsets_table_data.get("fields", [])}

    if "Ads" in existing_field_names:
        print("\n  'Ads' linked field already exists on Ad Sets — skipping")
    else:
        print("\n  Adding 'Ads' linked record field to Ad Sets table...")
        add_field(base_id, adsets_table_id, {
            "name": "Ads",
            "type": "multipleRecordLinks",
            "options": {"linkedTableId": ads_table_id},
        })

    print("\nSetup complete!")
    print_config(base_id, adsets_table_id, ads_table_id)

    print("\nNext steps:")
    print("  1. Open the base in Airtable and create a Gallery view on the Ads table")
    print("  2. Set up the automation: Ad Sets → Status = 'Ready to Launch' → webhook POST")
    print("  3. Add the config snippet above to your client's fb_ads_config.json")
    print("  4. Optionally delete the default 'Table 1' that Airtable creates with new bases")


def show_info(base_id: str):
    """Show table IDs for an existing base."""
    tables = get_existing_tables(base_id)

    adsets = next((t for t in tables if t["name"] == "Ad Sets"), None)
    ads = next((t for t in tables if t["name"] == "Ads"), None)

    if not adsets or not ads:
        print(f"Base {base_id} doesn't have the expected tables.")
        print(f"Found: {', '.join(t['name'] for t in tables)}")
        print("Run without --info to set up the tables.")
        return

    print_config(base_id, adsets["id"], ads["id"])


def migrate_add_field(base_id: str, table_name: str, field_def: dict):
    """Add a field to an existing table if it doesn't already exist."""
    tables = get_existing_tables(base_id)
    table = next((t for t in tables if t["name"] == table_name), None)
    if not table:
        print(f"  Table '{table_name}' not found in base {base_id} — skipping")
        return False

    existing_field_names = {f["name"] for f in table.get("fields", [])}
    if field_def["name"] in existing_field_names:
        print(f"  '{field_def['name']}' already exists in '{table_name}' — skipping")
        return False

    add_field(base_id, table["id"], field_def)
    return True


def migrate_all_clients():
    """Add the Attribution Window field to all client Airtable bases."""
    import glob as glob_mod

    # scripts/foo.py — repo root is parents[1]
    configs_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "clients")
    config_files = glob_mod.glob(os.path.join(configs_dir, "*/fb_ads_config.json"))

    if not config_files:
        print("No client configs found.")
        return

    migrate_fields = [
        next(f for f in AD_SETS_FIELDS if f["name"] == "17. Exclusion Audiences"),
        next(f for f in AD_SETS_FIELDS if f["name"] == "10. Custom Audiences"),
    ]

    print(f"Migrating {len(config_files)} client base(s)...\n")
    for config_path in sorted(config_files):
        client_slug = os.path.basename(os.path.dirname(config_path))
        with open(config_path) as f:
            cfg = json.load(f)

        base_id = cfg.get("airtable_base_id", "")
        if not base_id or base_id.startswith("appXXX"):
            print(f"  {client_slug}: no valid airtable_base_id — skipping")
            continue

        print(f"  {client_slug} ({base_id}):")
        try:
            for field_def in migrate_fields:
                migrate_add_field(base_id, "Ad Sets", field_def)
        except SystemExit:
            print(f"    Failed — skipping")
        time.sleep(0.3)

    print("\nMigration complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Set up Ad Launcher tables in an existing Airtable base"
    )
    parser.add_argument("base_id", nargs="?", help="Airtable base ID (appXXXXXXXX) — create the base in the UI first")
    parser.add_argument("--info", action="store_true", help="Just print table IDs, don't create anything")
    parser.add_argument("--migrate", action="store_true",
                        help="Add new fields to ALL existing client bases (no base_id needed)")
    args = parser.parse_args()

    if args.migrate:
        migrate_all_clients()
    elif not args.base_id:
        parser.error("base_id is required unless using --migrate")
    elif args.info:
        show_info(args.base_id)
    else:
        setup_base(args.base_id)


if __name__ == "__main__":
    main()
