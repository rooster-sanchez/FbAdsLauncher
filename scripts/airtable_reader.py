#!/usr/bin/env python3
from __future__ import annotations
"""
Airtable Reader for FB Ads Launcher
Reads Ad Set record (batch config) and linked Ad records from Airtable.

Replaces clickup_reader.py — same brief dict format so main.py's downstream
code (meta_api, targeting) stays untouched.

Usage:
    from airtable_reader import get_batch_brief
    brief = get_batch_brief("recXXXXXX", config)
"""

import os
import re
import time
from datetime import datetime

import requests

AIRTABLE_BASE_URL = "https://api.airtable.com/v0"


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _get_record(base_id: str, table_id: str, record_id: str, api_key: str) -> dict:
    """Fetch a single Airtable record by ID."""
    resp = requests.get(
        f"{AIRTABLE_BASE_URL}/{base_id}/{table_id}/{record_id}",
        headers=_headers(api_key),
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(
            f"Airtable GET record {record_id} failed [{resp.status_code}]: {resp.text[:300]}"
        )
    return resp.json()


def _patch_record(base_id: str, table_id: str, record_id: str,
                  fields: dict, api_key: str) -> dict:
    """Update fields on a single Airtable record."""
    resp = requests.patch(
        f"{AIRTABLE_BASE_URL}/{base_id}/{table_id}/{record_id}",
        headers={**_headers(api_key), "Content-Type": "application/json"},
        json={"fields": fields},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(
            f"Airtable PATCH {record_id} failed [{resp.status_code}]: {resp.text[:300]}"
        )
    return resp.json()


def _parse_exclusion_audiences(selections: list) -> list[str]:
    """Parse audience IDs from multipleSelects values like 'Audience Name (123456789)'.

    Returns a list of Meta audience ID strings.
    """
    ids = []
    for selection in selections:
        match = re.search(r'\((\d+)\)$', str(selection).strip())
        if match:
            ids.append(match.group(1))
    return ids


def _clean_text(text: str) -> str:
    """Clean up text from Airtable — strip whitespace, keep as single string."""
    return text.strip() if text else ""


def get_batch_brief(record_id: str, config: dict) -> dict:
    """Read a complete batch brief from an Airtable Ad Set record + linked Ads.

    Returns the same dict shape as clickup_reader.get_batch_brief:
        {
            "task_id": str,
            "task_name": str,
            "task_url": str,
            "batch_fields": {field_name: value, ...},
            "ads": [
                {
                    "task_id": str,
                    "ad_name": str,
                    "fields": {headline, primary_text, description},
                    "attachments": [{name, url, type}, ...],
                },
            ]
        }
    """
    api_key = config["airtable_api_key"]
    base_id = config["airtable_base_id"]
    adsets_table = config["airtable_ad_sets_table_id"]
    ads_table = config["airtable_ads_table_id"]

    # 1. Read the Ad Set record
    adset_record = _get_record(base_id, adsets_table, record_id, api_key)
    f = adset_record.get("fields", {})

    # 2. Build batch_fields dict (same keys main.py expects)
    # Field names use numbered prefixes from the template (e.g., "1. Campaign")
    # Falls back to old names for backwards compatibility with un-synced bases
    batch_fields = {
        "campaign": f.get("1. Campaign") or f.get("Campaign", "New") or "New",
        "existing_campaign_name": f.get("2. Campaign Name") or f.get("Existing Campaign Name", "") or "",
        "ad_set": f.get("3. Ad Set New?") or "New",
        "daily_budget": float(f.get("6. Daily Budget") or f.get("5. Daily Budget") or f.get("Daily Budget") or 0),
        "targeting": (f.get("7. Targeting Type") or f.get("6. Targeting Type") or f.get("Targeting Type") or "Broad").lower(),
        "age_range": f.get("8. Age Range") or f.get("7. Age Range") or f.get("Age Range", "") or "",
        "gender": (f.get("9. Gender") or f.get("8. Gender") or f.get("Gender") or "All").lower(),
        "custom_audience_ids": _parse_exclusion_audiences(
            f.get("10. Custom Audiences") or f.get("Custom Audiences") or []
        ) or f.get("10. Custom Audience IDs") or f.get("9. Custom Audience IDs") or f.get("Custom Audience IDs", "") or "",
        "interest_keywords": f.get("11. Interest Keywords") or f.get("10. Interest Keywords") or f.get("Interest Keywords", "") or "",
        "destination_url": f.get("12. Destination URL") or f.get("11. Destination URL") or f.get("Destination URL", "") or "",
        "cta": f.get("13. CTA") or f.get("12. CTA") or f.get("CTA", "LEARN_MORE") or "LEARN_MORE",
        "attribution_window": f.get("14. Attribution Window") or f.get("Attribution Window", "") or "",
        "existing_ad_set_name": f.get("5. Existing Ad Set Name") or f.get("Existing Ad Set Name") or "",
        "adset_name": f.get("4. Ad Set Name") or f.get("Ad Set Name") or "",
        "launch_date": f.get("16. Launch Date") or f.get("Launch Date", "") or "",
        "exclusion_audiences": _parse_exclusion_audiences(
            f.get("17. Exclusion Audiences") or f.get("Exclusion Audiences") or []
        ),
        # Idempotency fields — used to detect already-launched records
        "_status": f.get("15. Status") or f.get("Status", ""),
        "_meta_campaign_id": f.get("Meta Campaign ID", ""),
    }

    # 3. Read each linked Ad record
    ad_record_ids = f.get("17. Ads") or f.get("15. Ads") or f.get("Ads", [])  # list of record IDs
    ads = []

    for i, ad_rec_id in enumerate(ad_record_ids):
        # Rate limit: Airtable allows 5 req/sec per base
        if i > 0:
            time.sleep(0.25)

        ad_record = _get_record(base_id, ads_table, ad_rec_id, api_key)
        ad_f = ad_record.get("fields", {})

        # Collect headline variants (non-empty only)
        # New numbered names: "4. Headline 1", "5. Headline 2", "6. Headline 3"
        # Fallback to old names: "Headline 1", "Headline 2", "Headline 3"
        headlines = []
        headline_num_map = {1: "4", 2: "5", 3: "6"}
        for hi in range(1, 4):
            prefix = headline_num_map[hi]
            h = ad_f.get(f"{prefix}. Headline {hi}", "") or ad_f.get(f"Headline {hi}", "") or ""
            h = _clean_text(h)
            if h:
                headlines.append(h)
        # Backward compat: also check old "Headline" field name
        if not headlines:
            old_h = _clean_text(ad_f.get("Headline", "") or "")
            if old_h:
                headlines.append(old_h)

        # Collect primary text variants (non-empty only)
        # New numbered names: "7. Primary Text 1", "8. Primary Text 2", "9. Primary Text 3"
        # Fallback to old names: "Primary Text 1", "Primary Text 2", "Primary Text 3"
        primary_texts = []
        primary_num_map = {1: "7", 2: "8", 3: "9"}
        for pi in range(1, 4):
            prefix = primary_num_map[pi]
            pt = ad_f.get(f"{prefix}. Primary Text {pi}", "") or ad_f.get(f"Primary Text {pi}", "") or ""
            pt = _clean_text(pt)
            if pt:
                primary_texts.append(pt)
        # Backward compat: also check old "Primary Text" field name
        if not primary_texts:
            old_pt = _clean_text(ad_f.get("Primary Text", "") or "")
            if old_pt:
                primary_texts.append(old_pt)

        description = _clean_text(ad_f.get("Description", "") or "")

        # Return string if single variant, list if multiple (triggers flex ads downstream)
        headline = headlines[0] if len(headlines) == 1 else (headlines if headlines else "")
        primary_text = primary_texts[0] if len(primary_texts) == 1 else (primary_texts if primary_texts else "")

        ad_format = ad_f.get("2. Ad Format") or ad_f.get("Ad Format", "Single Image/Video") or "Single Image/Video"
        # Backward compat: rename old "Multi-Format" to "Multi-Placement"
        if ad_format == "Multi-Format":
            ad_format = "Multi-Placement"

        # Airtable attachments: list of dicts with url, filename, type, id
        attachments_raw = ad_f.get("3. Ad Creative") or ad_f.get("Ad Creative") or ad_f.get("Creative", []) or []
        attachments = [
            {
                "name": att.get("filename", "creative"),
                "url": att.get("url", ""),
                "type": att.get("type", ""),
            }
            for att in attachments_raw
        ]

        ads.append({
            "task_id": ad_rec_id,
            "ad_name": ad_f.get("1. Ad Name") or ad_f.get("Ad Name", "") or "",
            "fields": {
                "headline": headline,
                "primary_text": primary_text,
                "description": description,
                "ad_format": ad_format,
            },
            "attachments": attachments,
        })

    return {
        "task_id": record_id,
        "task_name": f.get("4. Ad Set Name") or f.get("Ad Set Name", "") or "",
        "task_url": f"https://airtable.com/{base_id}/{adsets_table}/{record_id}",
        "batch_fields": batch_fields,
        "ads": ads,
    }


def download_attachment(url: str, save_dir: str, filename: str, api_key: str) -> str:
    """Download a file from an Airtable attachment URL.

    Airtable attachment URLs are pre-signed S3 URLs — no auth header needed.
    Returns the local file path.
    """
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)

    resp = requests.get(url, timeout=120, stream=True)
    if not resp.ok:
        raise RuntimeError(
            f"Failed to download Airtable attachment [{resp.status_code}]: {url[:100]}"
        )

    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    return save_path


def update_task_status(record_id: str, status: str, config: dict) -> bool:
    """Update an Ad Set record's Status field. Returns True on success."""
    try:
        _patch_record(
            config["airtable_base_id"],
            config["airtable_ad_sets_table_id"],
            record_id,
            {"15. Status": status},
            config["airtable_api_key"],
        )
        return True
    except RuntimeError as e:
        print(f"Warning: Failed to update Airtable status: {e}")
        return False


def add_task_comment(record_id: str, comment_text: str, config: dict) -> bool:
    """Write a note to the Ad Set record's Notes field.

    Airtable has no comments API for personal access tokens,
    so we write to the Notes long text field instead.
    """
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        _patch_record(
            config["airtable_base_id"],
            config["airtable_ad_sets_table_id"],
            record_id,
            {"Notes": f"[{ts}] {comment_text}"},
            config["airtable_api_key"],
        )
        return True
    except RuntimeError as e:
        print(f"Note: Could not write comment to Airtable: {e}")
        return False


def write_meta_ids(record_id: str, campaign_id: str, adset_ids: list[str],
                   ad_ids: list[str], config: dict, launch_date: str = "") -> bool:
    """Write Meta campaign/ad set IDs back to the Ad Set record and set status to Launched."""
    try:
        fields = {
            "Meta Campaign ID": campaign_id,
            "Meta Ad Set IDs": ", ".join(adset_ids),
            "16. Launch Date": launch_date or datetime.now().strftime("%Y-%m-%d"),
            "15. Status": "Launched",
        }
        _patch_record(
            config["airtable_base_id"],
            config["airtable_ad_sets_table_id"],
            record_id,
            fields,
            config["airtable_api_key"],
        )
        return True
    except RuntimeError as e:
        print(f"Warning: Failed to write Meta IDs to Airtable: {e}")
        return False


def write_ad_meta_id(ad_record_id: str, meta_ad_id: str, config: dict) -> bool:
    """Write a Meta Ad ID back to an individual Ad record."""
    try:
        _patch_record(
            config["airtable_base_id"],
            config["airtable_ads_table_id"],
            ad_record_id,
            {"Meta Ad ID": meta_ad_id},
            config["airtable_api_key"],
        )
        return True
    except RuntimeError as e:
        print(f"Warning: Failed to write Meta Ad ID to Airtable: {e}")
        return False


if __name__ == "__main__":
    """Quick test: read a batch brief and print it."""
    import json
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from config_loader import load_all

    if len(sys.argv) < 3:
        print("Usage: python3 airtable_reader.py <client_slug> <airtable_record_id>")
        sys.exit(1)

    client_slug = sys.argv[1]
    record_id = sys.argv[2]

    config = load_all(client_slug)
    brief = get_batch_brief(record_id, config)
    print(json.dumps(brief, indent=2, default=str))
