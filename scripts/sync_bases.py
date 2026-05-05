#!/usr/bin/env python3
from __future__ import annotations
"""
Sync Airtable base structures from the template to all client bases.

Reads the template base (applXM4Udl33lKIst) and applies field-level changes
to every client base that has an airtable_base_id in fb_ads_config.json.

Handles:
  - Renaming fields (detected via explicit rename map)
  - Adding new fields
  - Adding new options to single-select fields
  - Flagging fields for manual deletion

Does NOT handle (Airtable API limitation):
  - Views (must be created/modified manually in the UI)
  - Field reordering
  - Changing field types
  - Field deletion (API doesn't support it)

Usage:
    # Dry run — show what would change
    python3 scripts/sync_bases.py

    # Apply changes
    python3 scripts/sync_bases.py --apply
"""

import argparse
import glob as glob_mod
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_API = "https://api.airtable.com/v0"
TEMPLATE_BASE_ID = "applXM4Udl33lKIst"

# ─── Rename Maps ─────────────────────────────────────────────────────────────
# When you rename a field in the template, add it here so the sync script
# renames it in client bases instead of creating a duplicate.
#
# Format: "Old Name (in client bases)" → "New Name (in template)"
# After a successful sync, you can remove entries from this map.

AD_SETS_RENAMES = {
    # All client bases are now duplicates of the template (as of 2026-03-06).
    # Add entries here only when you rename a field in the template going forward.
}

ADS_RENAMES = {
    # All client bases are now duplicates of the template (as of 2026-03-06).
    # Add entries here only when you rename a field in the template going forward.
}

# Table name → rename map
RENAME_MAPS = {
    "Ad Sets": AD_SETS_RENAMES,
    "Ads": ADS_RENAMES,
}

# Fields to skip during sync (auto-created by Airtable, or cross-base references)
SKIP_FIELD_TYPES = {"multipleRecordLinks"}

# Field types that can't be created via Airtable API
UNCREATABLE_FIELD_TYPES = {"createdTime", "lastModifiedTime", "autoNumber", "createdBy", "lastModifiedBy"}


def _headers():
    api_key = os.getenv("AIRTABLE_API_KEY", "")
    if not api_key:
        print("ERROR: AIRTABLE_API_KEY not found in .env")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _get(endpoint: str) -> dict:
    resp = requests.get(f"{AIRTABLE_API}{endpoint}", headers=_headers(), timeout=15)
    if not resp.ok:
        print(f"  API error [{resp.status_code}]: {resp.text[:300]}")
        return {}
    return resp.json()


def _post(endpoint: str, data: dict) -> dict:
    resp = requests.post(
        f"{AIRTABLE_API}{endpoint}", headers=_headers(), json=data, timeout=30,
    )
    if not resp.ok:
        print(f"  API error [{resp.status_code}]: {resp.text[:300]}")
        return {}
    return resp.json()


def _patch(endpoint: str, data: dict) -> dict:
    resp = requests.patch(
        f"{AIRTABLE_API}{endpoint}", headers=_headers(), json=data, timeout=30,
    )
    if not resp.ok:
        print(f"  API error [{resp.status_code}]: {resp.text[:300]}")
        return {}
    return resp.json()


def _add_select_option_via_typecast(base_id: str, table_id: str,
                                     field_name: str, option_value: str):
    """Add a new option to a single-select field by creating+deleting a dummy record.

    The Airtable meta API doesn't support adding choices to existing select fields,
    but creating a record with typecast=true forces the option into existence.
    """
    # Create dummy record with the new value
    resp = requests.post(
        f"{AIRTABLE_API}/{base_id}/{table_id}",
        headers=_headers(),
        json={"fields": {field_name: option_value}, "typecast": True},
        timeout=30,
    )
    if not resp.ok:
        print(f"      Failed to add option '{option_value}': {resp.text[:200]}")
        return
    rec_id = resp.json().get("id")
    if rec_id:
        # Delete the dummy record
        requests.delete(
            f"{AIRTABLE_API}/{base_id}/{table_id}/{rec_id}",
            headers=_headers(),
            timeout=30,
        )


def get_tables(base_id: str) -> list[dict]:
    data = _get(f"/meta/bases/{base_id}/tables")
    return data.get("tables", [])


def get_client_bases() -> list[dict]:
    # scripts/foo.py — repo root is parents[1]
    configs_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "clients")
    config_files = glob_mod.glob(os.path.join(configs_dir, "*/fb_ads_config.json"))

    clients = []
    seen_bases = set()
    for path in sorted(config_files):
        slug = os.path.basename(os.path.dirname(path))
        with open(path) as f:
            cfg = json.load(f)
        base_id = cfg.get("airtable_base_id", "")
        if not base_id or base_id == TEMPLATE_BASE_ID:
            continue
        if base_id in seen_bases:
            continue
        seen_bases.add(base_id)
        clients.append({"slug": slug, "base_id": base_id})

    return clients


def build_field_spec(field: dict) -> dict:
    """Build a clean field spec for creation (strip IDs and metadata)."""
    spec = {"name": field["name"], "type": field["type"]}
    if field.get("options"):
        opts = {}
        if field["type"] == "singleSelect" and "choices" in field["options"]:
            opts["choices"] = [
                {"name": c["name"], "color": c.get("color", "blueLight2")}
                for c in field["options"]["choices"]
            ]
        elif field["type"] == "currency":
            opts["precision"] = field["options"].get("precision", 0)
            opts["symbol"] = field["options"].get("symbol", "$")
        elif field["type"] == "date" and "dateFormat" in field["options"]:
            opts["dateFormat"] = field["options"]["dateFormat"]
        if opts:
            spec["options"] = opts
    return spec


def diff_table(template_table: dict, client_table: dict, table_name: str) -> dict:
    """Compare template vs client table. Returns changes needed."""
    rename_map = RENAME_MAPS.get(table_name, {})
    # Reverse map: new_name → old_name
    reverse_renames = {v: k for k, v in rename_map.items()}

    template_fields = {f["name"]: f for f in template_table.get("fields", [])
                       if f["type"] not in SKIP_FIELD_TYPES}
    client_fields = {f["name"]: f for f in client_table.get("fields", [])
                     if f["type"] not in SKIP_FIELD_TYPES}

    changes = {
        "rename": [],    # Fields to rename (old_name → new_name)
        "add": [],       # New fields to create
        "update": [],    # Select fields needing new options
        "delete": [],    # Fields to flag for manual deletion
        "manual": [],    # Fields that can't be created via API
    }

    # Track which client fields are accounted for
    matched_client_fields = set()

    for template_name, t_field in template_fields.items():
        # Case 1: Field exists with same name in client
        if template_name in client_fields:
            matched_client_fields.add(template_name)
            c_field = client_fields[template_name]

            # Check for missing select options
            if t_field["type"] == "singleSelect" and c_field["type"] == "singleSelect":
                t_choices = {c["name"] for c in t_field.get("options", {}).get("choices", [])}
                c_choices_list = c_field.get("options", {}).get("choices", [])
                c_choices = {c["name"] for c in c_choices_list}
                missing = t_choices - c_choices
                if missing:
                    # Merge: keep existing choices (with their IDs) + add new ones
                    merged = list(c_choices_list)  # existing choices keep their IDs
                    for tc in t_field["options"]["choices"]:
                        if tc["name"] not in c_choices:
                            merged.append({"name": tc["name"], "color": tc.get("color", "blueLight2")})
                    changes["update"].append({
                        "field_id": c_field["id"],
                        "name": template_name,
                        "missing_choices": missing,
                        "merged_choices": merged,
                    })
            continue

        # Case 2: Field was renamed — old name exists in client
        old_name = reverse_renames.get(template_name)
        if old_name and old_name in client_fields:
            matched_client_fields.add(old_name)
            c_field = client_fields[old_name]
            rename_entry = {
                "field_id": c_field["id"],
                "old_name": old_name,
                "new_name": template_name,
            }

            # Also update select options if needed
            if t_field["type"] == "singleSelect" and c_field["type"] == "singleSelect":
                t_choices = {c["name"] for c in t_field.get("options", {}).get("choices", [])}
                c_choices = {c["name"] for c in c_field.get("options", {}).get("choices", [])}
                missing = t_choices - c_choices
                if missing:
                    rename_entry["new_options"] = {
                        "choices": [
                            {"name": c["name"], "color": c.get("color", "blueLight2")}
                            for c in t_field["options"]["choices"]
                        ]
                    }
                    rename_entry["missing_choices"] = missing

            changes["rename"].append(rename_entry)
            continue

        # Case 3: Truly new field — doesn't exist in any form
        if t_field["type"] in UNCREATABLE_FIELD_TYPES:
            changes["manual"].append({"name": template_name, "type": t_field["type"]})
        else:
            changes["add"].append(build_field_spec(t_field))

    # Fields in client that aren't in template and aren't being renamed
    for client_name, c_field in client_fields.items():
        if client_name not in matched_client_fields:
            # Check if this field is being renamed TO something
            if client_name in rename_map:
                continue  # Already handled above
            changes["delete"].append({"name": client_name, "field_id": c_field["id"]})

    return changes


def apply_changes(base_id: str, table_id: str, changes: dict, apply: bool) -> int:
    """Apply field changes to a client table. Returns number of changes made."""
    count = 0

    # 1. Renames first (so subsequent operations use the new names)
    for r in changes["rename"]:
        patch_data = {"name": r["new_name"]}
        if r.get("new_options"):
            patch_data["options"] = r["new_options"]
        extra = ""
        if r.get("missing_choices"):
            extra = f" + adding options: {', '.join(r['missing_choices'])}"
        if apply:
            print(f"    ~ Renaming: {r['old_name']} → {r['new_name']}{extra}")
            _patch(f"/meta/bases/{base_id}/tables/{table_id}/fields/{r['field_id']}", patch_data)
            time.sleep(0.25)
        else:
            print(f"    ~ Would rename: {r['old_name']} → {r['new_name']}{extra}")
        count += 1

    # 2. Add new fields
    for field_spec in changes["add"]:
        if apply:
            print(f"    + Adding: {field_spec['name']} ({field_spec['type']})")
            _post(f"/meta/bases/{base_id}/tables/{table_id}/fields", field_spec)
            time.sleep(0.25)
        else:
            print(f"    + Would add: {field_spec['name']} ({field_spec['type']})")
        count += 1

    # 3. Update select options (via typecast workaround — meta API can't add choices)
    for u in changes["update"]:
        missing_list = list(u["missing_choices"])
        missing_str = ", ".join(missing_list)
        if apply:
            print(f"    ~ Adding options to {u['name']}: {missing_str}")
            for choice_name in missing_list:
                _add_select_option_via_typecast(base_id, table_id, u["name"], choice_name)
                time.sleep(0.25)
        else:
            print(f"    ~ Would add options to {u['name']}: {missing_str}")
        count += 1

    # 4. Fields that need manual creation (API limitation)
    for m in changes.get("manual", []):
        print(f"    ! Manual add needed: {m['name']} ({m['type']}) — API can't create this type")
        count += 1

    # 5. Flag deletions (API can't delete fields)
    for d in changes["delete"]:
        print(f"    - Manual delete needed: {d['name']}")
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser(
        description="Sync Airtable field structure from template to all client bases"
    )
    parser.add_argument("--apply", action="store_true",
                        help="Actually apply changes (default is dry run)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"\n{'='*60}")
    print(f"Airtable Base Sync — {mode}")
    print(f"Template: {TEMPLATE_BASE_ID}")
    print(f"{'='*60}")

    # 1. Read template
    print("\nReading template base...")
    template_tables = get_tables(TEMPLATE_BASE_ID)
    if not template_tables:
        print("ERROR: Could not read template base")
        sys.exit(1)

    template_by_name = {t["name"]: t for t in template_tables}
    for t in template_tables:
        fields = [f["name"] for f in t.get("fields", []) if f["type"] not in SKIP_FIELD_TYPES]
        print(f"  {t['name']}: {', '.join(fields)}")

    # 2. Get client bases
    clients = get_client_bases()
    print(f"\n{len(clients)} unique client base(s)\n")

    # 3. Diff and sync
    total_changes = 0
    for client in clients:
        slug = client["slug"]
        base_id = client["base_id"]
        print(f"--- {slug} ({base_id}) ---")

        client_tables = get_tables(base_id)
        if not client_tables:
            print("  ERROR: Could not read base")
            continue

        client_by_name = {t["name"]: t for t in client_tables}

        for table_name, template_table in template_by_name.items():
            if table_name not in client_by_name:
                print(f"  {table_name}: MISSING (create manually)")
                continue

            client_table = client_by_name[table_name]
            changes = diff_table(template_table, client_table, table_name)

            has_changes = any(changes[k] for k in changes)
            if not has_changes:
                print(f"  {table_name}: up to date")
                continue

            print(f"  {table_name}:")
            n = apply_changes(base_id, client_table["id"], changes, args.apply)
            total_changes += n

        time.sleep(0.3)
        print()

    print(f"{'='*60}")
    if args.apply:
        print(f"Done. {total_changes} change(s) applied.")
    else:
        print(f"Dry run complete. {total_changes} change(s) found.")
        print(f"Run with --apply to execute.")
    print(f"{'='*60}")

    if total_changes > 0:
        print("\nREMINDER: Views must be replicated manually in Airtable UI.")
        print("Template views:")
        for t in template_tables:
            views = [v["name"] for v in t.get("views", [])]
            print(f"  {t['name']}: {', '.join(views)}")
        print()


if __name__ == "__main__":
    main()
