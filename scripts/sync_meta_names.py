#!/usr/bin/env python3
from __future__ import annotations
"""
Sync Meta Names to Airtable — Fetches active campaigns and ad sets from Meta,
then updates the singleSelect field choices in the Airtable Ad Sets table so
dropdowns stay current.

Updates these fields in the Ad Sets table:
  - "2. Campaign Name" — populated with active campaign names
  - "Existing Ad Set Name" — populated with active ad set names

Usage:
    # Single client
    python3 agents/fb-ads-launcher/scripts/sync_meta_names.py ts_twelve_south

    # Preview without making changes
    python3 agents/fb-ads-launcher/scripts/sync_meta_names.py ts_twelve_south --dry-run

    # Sync all clients that have airtable_base_id configured
    python3 agents/fb-ads-launcher/scripts/sync_meta_names.py --all

    # Dry-run all clients
    python3 agents/fb-ads-launcher/scripts/sync_meta_names.py --all --dry-run
"""

import argparse
import glob
import json
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import load_all
from meta_api import _meta_request, BASE_URL

import requests

AIRTABLE_META_URL = "https://api.airtable.com/v0/meta/bases"


# ─── Meta Fetchers ────────────────────────────────────────────────────────────

def fetch_active_campaigns(config: dict) -> list[str]:
    """Fetch all ACTIVE campaign names from Meta, handling pagination."""
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/campaigns"
    params = {
        "access_token": config["fb_access_token"],
        "fields": "name",
        "effective_status": json.dumps(["ACTIVE"]),
        "limit": 100,
    }

    names = []
    while url:
        data = _meta_request(
            "GET", url,
            access_token=config["fb_access_token"],
            params=params,
        )
        for item in data.get("data", []):
            names.append(item["name"])

        # Follow pagination
        paging = data.get("paging", {})
        url = paging.get("next")
        params = None  # params are embedded in the next URL

    return names


def fetch_active_adsets(config: dict) -> list[str]:
    """Fetch all ACTIVE ad set names from Meta, handling pagination."""
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/adsets"
    params = {
        "access_token": config["fb_access_token"],
        "fields": "name",
        "effective_status": json.dumps(["ACTIVE"]),
        "limit": 100,
    }

    names = []
    while url:
        data = _meta_request(
            "GET", url,
            access_token=config["fb_access_token"],
            params=params,
        )
        for item in data.get("data", []):
            names.append(item["name"])

        # Follow pagination
        paging = data.get("paging", {})
        url = paging.get("next")
        params = None

    return names


# ─── Airtable Helpers ─────────────────────────────────────────────────────────

def get_table_fields(airtable_api_key: str, base_id: str, table_id: str) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Fetch all field names/IDs and existing singleSelect choices for a table.

    Returns:
        (field_map, choices_map)
        field_map:   {field_name: field_id}
        choices_map: {field_name: {choice_name, ...}}  (only for singleSelect fields)
    """
    url = f"{AIRTABLE_META_URL}/{base_id}/tables"
    headers = {"Authorization": f"Bearer {airtable_api_key}"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    for table in data.get("tables", []):
        if table.get("id") == table_id:
            field_map = {f["name"]: f["id"] for f in table.get("fields", [])}
            choices_map = {}
            for f in table.get("fields", []):
                if f.get("type") == "singleSelect":
                    choices_map[f["name"]] = {
                        c["name"] for c in f.get("options", {}).get("choices", [])
                    }
            return field_map, choices_map
    return {}, {}



def update_field_choices(airtable_api_key: str, base_id: str, table_id: str,
                         field_name: str, names: list[str],
                         existing_choices: set[str],
                         dry_run: bool = False) -> bool:
    """Add missing singleSelect choices via the typecast workaround.

    The Airtable Meta API can't add choices to existing select fields via PATCH.
    Instead, we create a dummy record with typecast=true (which forces the option
    into existence), then immediately delete it.
    """
    new_names = [n for n in names if n not in existing_choices]

    if not new_names:
        print(f"    All {len(names)} choices already exist — nothing to add")
        return True

    if dry_run:
        print(f"    [DRY RUN] Would add {len(new_names)} new choice(s) "
              f"({len(existing_choices)} already exist)")
        for n in new_names:
            print(f"      + {n}")
        return True

    print(f"    Adding {len(new_names)} new choice(s) ({len(existing_choices)} already exist)")
    headers = {
        "Authorization": f"Bearer {airtable_api_key}",
        "Content-Type": "application/json",
    }
    record_url = f"https://api.airtable.com/v0/{base_id}/{table_id}"

    for name in new_names:
        # Create dummy record with typecast to force the option into existence
        resp = requests.post(
            record_url, headers=headers,
            json={"fields": {field_name: name}, "typecast": True},
            timeout=30,
        )
        if not resp.ok:
            print(f"      Failed to add '{name}': {resp.text[:200]}")
            continue

        rec_id = resp.json().get("id")
        if rec_id:
            requests.delete(f"{record_url}/{rec_id}", headers=headers, timeout=30)
        print(f"      + {name}")
        time.sleep(0.25)

    return True


# ─── Client Discovery ─────────────────────────────────────────────────────────

def find_all_clients() -> list[str]:
    """Find all client slugs that have airtable_base_id in fb_ads_config.json."""
    workspace_root = SCRIPTS_DIR.resolve().parents[2]
    clients_dir = workspace_root / "clients"
    pattern = str(clients_dir / "*" / "fb_ads_config.json")

    slugs = []
    for config_path in glob.glob(pattern):
        with open(config_path) as f:
            config = json.load(f)
        if config.get("airtable_base_id"):
            slug = Path(config_path).parent.name
            slugs.append(slug)

    return sorted(slugs)


# ─── Main ─────────────────────────────────────────────────────────────────────

def sync_client(client_slug: str, dry_run: bool = False):
    """Sync Meta campaign/ad set names to Airtable for a single client."""
    print(f"\n{'='*60}")
    print(f"Syncing: {client_slug}")
    print(f"{'='*60}")

    config = load_all(client_slug)

    if not config["airtable_base_id"] or not config["airtable_ad_sets_table_id"]:
        print(f"  Skipping — no airtable_base_id or airtable_ad_sets_table_id configured")
        return

    base_id = config["airtable_base_id"]
    table_id = config["airtable_ad_sets_table_id"]
    airtable_key = config["airtable_api_key"]

    if not airtable_key:
        print(f"  Error: AIRTABLE_API_KEY not set")
        return

    # Fetch active campaigns and ad sets from Meta
    print(f"\n  Fetching active campaigns...")
    campaigns = fetch_active_campaigns(config)
    print(f"  Found {len(campaigns)} active campaign(s)")
    for name in campaigns:
        print(f"    - {name}")

    print(f"\n  Fetching active ad sets...")
    adsets = fetch_active_adsets(config)
    print(f"  Found {len(adsets)} active ad set(s)")
    for name in adsets:
        print(f"    - {name}")

    if not campaigns and not adsets:
        print(f"\n  No active campaigns or ad sets found, nothing to sync.")
        return

    # Look up field IDs and existing choices (single API call)
    print(f"\n  Looking up Airtable field IDs...")
    fields_map, choices_map = get_table_fields(airtable_key, base_id, table_id)

    campaign_field_name = None
    for name in ("2. Campaign Name", "Existing Campaign Name"):
        if name in fields_map:
            campaign_field_name = name
            break

    adset_field_name = None
    for name in ("5. Existing Ad Set Name", "Existing Ad Set Name"):
        if name in fields_map:
            adset_field_name = name
            break

    if not campaign_field_name:
        print(f"  Warning: Could not find field '2. Campaign Name' in table {table_id}")
    if not adset_field_name:
        print(f"  Warning: Could not find field '5. Existing Ad Set Name' in table {table_id}")

    # Update field choices via typecast workaround
    if campaigns and campaign_field_name:
        print(f"\n  Updating '{campaign_field_name}' field choices...")
        update_field_choices(airtable_key, base_id, table_id,
                             campaign_field_name, campaigns,
                             choices_map.get(campaign_field_name, set()),
                             dry_run=dry_run)

    if adsets and adset_field_name:
        print(f"\n  Updating '{adset_field_name}' field choices...")
        update_field_choices(airtable_key, base_id, table_id,
                             adset_field_name, adsets,
                             choices_map.get(adset_field_name, set()),
                             dry_run=dry_run)

    # Summary
    print(f"\n  Summary for {client_slug}:")
    print(f"    Campaigns synced: {len(campaigns)}")
    print(f"    Ad sets synced:   {len(adsets)}")
    if dry_run:
        print(f"    Mode: DRY RUN (no changes made)")


def main():
    parser = argparse.ArgumentParser(
        description="Sync active Meta campaign/ad set names to Airtable singleSelect fields"
    )
    parser.add_argument("client_slug", nargs="?", default=None,
                        help="Client slug (e.g., ts_twelve_south)")
    parser.add_argument("--all", action="store_true",
                        help="Sync all clients with airtable_base_id configured")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without updating Airtable")
    args = parser.parse_args()

    if not args.all and not args.client_slug:
        parser.error("Provide a client_slug or use --all")

    if args.all:
        slugs = find_all_clients()
        if not slugs:
            print("No clients found with airtable_base_id configured.")
            return
        print(f"Found {len(slugs)} client(s) to sync: {', '.join(slugs)}")
        for slug in slugs:
            try:
                sync_client(slug, dry_run=args.dry_run)
            except Exception as e:
                print(f"\n  Error syncing {slug}: {e}")
    else:
        sync_client(args.client_slug, dry_run=args.dry_run)

    print(f"\nDone.")


if __name__ == "__main__":
    main()
