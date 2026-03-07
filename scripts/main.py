#!/usr/bin/env python3
from __future__ import annotations
"""
FB Ads Launcher — Main Orchestrator
Reads an Airtable Ad Set record (batch brief) and linked Ad records,
then creates campaigns, ad sets, and ads in Meta Ads Manager.

All objects are created PAUSED. Use activate_ads.py to go live.

Usage:
    python3 agents/fb-ads-launcher/scripts/main.py <client_slug> <record_id>
    python3 agents/fb-ads-launcher/scripts/main.py <client_slug> <record_id> --dry-run
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add scripts dir to path for local imports
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config_loader import build_name, load_all, validate_config
from airtable_reader import (
    add_task_comment,
    download_attachment,
    get_batch_brief,
    update_task_status,
    write_ad_meta_id,
    write_meta_ids,
)
from meta_api import (
    MetaApiError,
    create_ad,
    create_ad_creative,
    create_carousel_creative,
    create_pac_creative,
    create_adset,
    create_campaign,
    detect_media_type,
    search_adsets,
    search_campaigns,
    upload_image,
    upload_video,
)
from targeting import build_targeting_spec

# Will be available after notifier.py is built
try:
    from notifier import notify_failure, notify_success
except ImportError:
    notify_success = None
    notify_failure = None


def validate_brief(brief: dict, batch_fields: dict, dry_run: bool = False) -> list[str]:
    """Validate that the batch brief has all required data."""
    errors = []

    # Campaign: dropdown (New/Existing)
    campaign_mode = str(batch_fields.get("campaign", "") or "").strip()
    if not campaign_mode:
        errors.append("Missing 'Campaign' dropdown on parent task (New or Existing)")
    elif campaign_mode.lower() == "existing" and not str(batch_fields.get("existing_campaign_name", "") or "").strip():
        errors.append("Campaign set to 'Existing' but 'Existing Campaign Name' is empty")

    # Ad Set: dropdown (New/Existing)
    adset_mode = str(batch_fields.get("ad_set", "") or "").strip()
    if not adset_mode:
        errors.append("Missing 'Ad Set' dropdown on parent task (New or Existing)")
    elif adset_mode.lower() == "existing" and not str(batch_fields.get("existing_ad_set_name", "") or "").strip():
        errors.append("Ad Set set to 'Existing' but 'Existing Ad Set Name' is empty")

    if not batch_fields.get("destination_url"):
        errors.append("Missing 'destination_url' field on parent task")

    budget = batch_fields.get("daily_budget")
    if budget is None:
        errors.append("Missing 'daily_budget' field on parent task")
    elif isinstance(budget, (int, float)) and budget <= 0:
        errors.append(f"Daily budget must be positive, got: {budget}")

    if not brief.get("ads"):
        errors.append("No subtasks (ads) found on the parent task")

    for i, ad in enumerate(brief.get("ads", [])):
        ad_name = ad.get("ad_name", f"ad_{i+1}")
        if not ad.get("ad_name"):
            errors.append(f"Subtask {i+1} has no name (ad name)")

        fields = ad.get("fields", {})
        ad_format = fields.get("ad_format", "Single Image/Video")
        num_attachments = len(ad.get("attachments", []))

        if not ad.get("attachments") and not dry_run:
            errors.append(f"Ad '{ad_name}' has no file attachment (creative)")
        elif ad_format in ("Multi-Placement", "Carousel") and num_attachments < 2 and not dry_run:
            errors.append(f"Ad '{ad_name}' is {ad_format} but has only {num_attachments} attachment(s) — need at least 2")

        headline = fields.get("headline", "")
        primary_text = fields.get("primary_text", "")
        has_headline = headline if isinstance(headline, str) else bool(headline)
        has_primary = primary_text if isinstance(primary_text, str) else bool(primary_text)
        if not has_headline:
            errors.append(f"Ad '{ad_name}' missing 'Headline 1'")
        if not has_primary:
            errors.append(f"Ad '{ad_name}' missing 'Primary Text 1'")

    return errors


def find_or_create_campaign(config: dict, batch_fields: dict, dry_run: bool) -> tuple[str, str]:
    """Find an existing campaign or create a new one.

    Campaign field is a dropdown: 'New' or 'Existing'.
    When 'Existing', uses 'existing_campaign_name' text field to find it.
    When 'New', generates name from naming convention.

    Returns (campaign_id, campaign_name).
    """
    campaign_mode = str(batch_fields.get("campaign", "New")).strip()
    existing_name = str(batch_fields.get("existing_campaign_name", "") or "").strip()

    if campaign_mode.lower() == "existing":
        if not existing_name:
            raise ValueError("Campaign set to 'Existing' but 'Existing Campaign Name' field is empty")

        print(f"\n  Looking for existing campaign: '{existing_name}'")
        existing = search_campaigns(config, existing_name)

        # Try exact match first
        for camp in existing:
            if camp["name"].lower() == existing_name.lower():
                print(f"  Found (exact): {camp['name']} (ID: {camp['id']})")
                return camp["id"], camp["name"]

        # If only one partial match, use it
        if len(existing) == 1:
            camp = existing[0]
            print(f"  Found (partial match): {camp['name']} (ID: {camp['id']})")
            return camp["id"], camp["name"]

        if existing:
            names = [c["name"] for c in existing]
            raise ValueError(
                f"Multiple campaigns contain '{existing_name}': {names}. "
                f"Use a more specific name."
            )

        raise ValueError(f"Campaign '{existing_name}' not found in ad account. Check the name and try again.")

    # Mode is "New" — generate campaign name from naming convention
    naming = config.get("naming_convention", {})
    if naming.get("campaign"):
        today = datetime.now().strftime("%Y-%m-%d")
        campaign_name = build_name(
            naming["campaign"],
            date=today,
            phase="testing",
            campaign_type="testing",
            buying_type="abo",
            objective="sales",
            geo="us",
        )
    else:
        campaign_name = f"campaign_{datetime.now().strftime('%Y-%m-%d')}"

    if dry_run:
        print(f"  [DRY RUN] Would create campaign: {campaign_name}")
        return "DRY_RUN_CAMPAIGN_ID", campaign_name

    campaign_id = create_campaign(config, campaign_name)
    return campaign_id, campaign_name


def find_or_create_adset(config: dict, campaign_id: str, batch_fields: dict,
                         targeting_spec: dict, dry_run: bool,
                         is_dynamic_creative: bool = False) -> str:
    """Find an existing ad set or create a new one.

    Ad Set field is a dropdown: 'New' or 'Existing'.
    When 'Existing', uses 'existing_ad_set_name' text field to find it.
    When 'New', generates name from targeting + naming convention.
    """
    adset_mode = str(batch_fields.get("ad_set", "New")).strip()
    existing_name = str(batch_fields.get("existing_ad_set_name", "") or "").strip()

    if adset_mode.lower() == "existing":
        if not existing_name:
            raise ValueError("Ad Set set to 'Existing' but 'Existing Ad Set Name' field is empty")

        print(f"\n  Looking for existing ad set: '{existing_name}'")
        existing = search_adsets(config, campaign_id, existing_name)

        for adset in existing:
            if adset["name"].lower() == existing_name.lower():
                print(f"  Found (exact): {adset['name']} (ID: {adset['id']})")
                return adset["id"]

        if len(existing) == 1:
            adset = existing[0]
            print(f"  Found (partial match): {adset['name']} (ID: {adset['id']})")
            return adset["id"]

        if existing:
            names = [a["name"] for a in existing]
            raise ValueError(
                f"Multiple ad sets contain '{existing_name}': {names}. "
                f"Use a more specific name."
            )

        raise ValueError(f"Ad set '{existing_name}' not found in campaign. Check the name and try again.")

    # Mode is "New" — use ad set name from brief, otherwise generate from convention
    adset_name_from_brief = str(batch_fields.get("adset_name", "") or "").strip()
    if adset_name_from_brief:
        adset_name = adset_name_from_brief
    else:
        targeting_type = str(batch_fields.get("targeting", "broad")).strip().lower()
        age_range = str(batch_fields.get("age_range", "")).replace(" ", "")
        gender = str(batch_fields.get("gender", "all")).strip().lower()
        audience_label = f"{targeting_type}_{gender}_{age_range}" if age_range else f"{targeting_type}_{gender}"

        naming = config.get("naming_convention", {})
        resolved_campaign = batch_fields.get("_resolved_campaign_name", "campaign")
        if naming.get("adset"):
            adset_name = build_name(
                naming["adset"],
                campaign_name=resolved_campaign,
                targeting_type=targeting_type,
                audience_label=audience_label,
            )
        else:
            adset_name = audience_label

    # Convert budget from dollars to cents
    daily_budget = batch_fields.get("daily_budget", 0)
    if isinstance(daily_budget, str):
        daily_budget = float(daily_budget.replace("$", "").replace(",", ""))
    daily_budget_cents = int(float(daily_budget) * 100)

    attribution_window = str(batch_fields.get("attribution_window", "") or "").strip()
    launch_date = str(batch_fields.get("launch_date", "") or "").strip()

    # Convert Airtable date (YYYY-MM-DD) to Meta start_time (ISO 8601 with midnight)
    start_time = ""
    if launch_date:
        start_time = f"{launch_date}T00:00:00-0500"

    if dry_run:
        print(f"  [DRY RUN] Would create ad set: {adset_name} (${daily_budget}/day)")
        print(f"  [DRY RUN] Targeting: {json.dumps(targeting_spec, indent=2)}")
        if attribution_window:
            print(f"  [DRY RUN] Attribution window: {attribution_window}")
        if start_time:
            print(f"  [DRY RUN] Start time: {start_time}")
        return "DRY_RUN_ADSET_ID"

    return create_adset(
        config,
        campaign_id=campaign_id,
        name=adset_name,
        targeting=targeting_spec,
        daily_budget_cents=daily_budget_cents,
        is_dynamic_creative=is_dynamic_creative,
        attribution_window=attribution_window,
        start_time=start_time,
    )


def _download_and_upload(config: dict, attachment: dict, download_dir: str) -> dict:
    """Download a creative attachment and upload to Meta.

    Returns {"type": "image"|"video", "ref": image_hash or video_id}.
    """
    filename = attachment["name"]
    media_type = detect_media_type(filename)

    local_path = download_attachment(
        attachment["url"], download_dir, filename, config["airtable_api_key"]
    )

    if media_type == "image":
        ref = upload_image(config, local_path)
    else:
        ref = upload_video(config, local_path)

    print(f"    Uploaded: {filename} ({media_type})")
    return {"type": media_type, "ref": ref}


def _build_ad_name(config: dict, ad_name: str) -> str:
    """Build full ad name from naming convention."""
    naming = config.get("naming_convention", {})
    if naming.get("ad"):
        return build_name(naming["ad"], adset_name="", ad_name=ad_name)
    return ad_name


def _process_single_ad(config, adset_id, ad_name, attachments, headline,
                        primary_text, description, destination_url, cta,
                        download_dir, url_tags="") -> dict:
    """Single Image/Video: upload first attachment, create one standard creative + ad.

    Uses only the first headline and primary text (no text variations).
    """
    attachment = attachments[0]
    media = _download_and_upload(config, attachment, download_dir)

    # Standard ads: use only first headline/text
    h = headline[0] if isinstance(headline, list) else headline
    pt = primary_text[0] if isinstance(primary_text, list) else primary_text

    creative_name = f"{ad_name}_creative"
    creative_id = create_ad_creative(
        config, name=creative_name, media_type=media["type"], media_ref=media["ref"],
        headline=h, primary_text=pt, description=description,
        destination_url=destination_url, cta=cta, url_tags=url_tags,
    )

    full_ad_name = _build_ad_name(config, ad_name)
    ad_id = create_ad(config, full_ad_name, adset_id, creative_id)

    return {
        "ad_name": ad_name, "ad_id": ad_id, "creative_id": creative_id,
        "media_type": media["type"], "media_ref": media["ref"],
    }


def _process_multi_placement_ad(config, adset_id, ad_name, attachments, headline,
                                 primary_text, description, destination_url, cta,
                                 download_dir, url_tags="") -> dict:
    """Multi-Placement: upload ALL attachments as placement-specific variants.

    Uses Placement Asset Customization (PAC) via asset_feed_spec + asset_customization_rules.
    Works on standard (non-dynamic) ad sets — multiple ads per ad set OK.
    Attachment order: [0]=Feed (1:1/4:5), [1]=Stories/Reels (9:16), [2]=Other.
    """
    print(f"    Format: Multi-Placement ({len(attachments)} sizes)")

    media_refs = [_download_and_upload(config, att, download_dir) for att in attachments]

    creative_name = f"{ad_name}_creative"
    creative_id = create_pac_creative(
        config, name=creative_name, media_refs=media_refs,
        headline=headline, primary_text=primary_text, description=description,
        destination_url=destination_url, cta=cta, url_tags=url_tags,
    )

    full_ad_name = _build_ad_name(config, ad_name)
    ad_id = create_ad(config, full_ad_name, adset_id, creative_id)

    return {
        "ad_name": ad_name, "ad_id": ad_id, "creative_id": creative_id,
        "media_type": media_refs[0]["type"], "media_ref": media_refs[0]["ref"],
    }


def _process_carousel_ad(config, adset_id, ad_name, attachments, headline,
                           primary_text, description, destination_url, cta,
                           download_dir, url_tags="") -> dict:
    """Carousel: upload ALL attachments as carousel cards.

    Single headline for all cards. Primary text as message above carousel.
    """
    print(f"    Format: Carousel ({len(attachments)} cards)")

    # Upload all attachments
    media_refs = [_download_and_upload(config, att, download_dir) for att in attachments]

    # For carousel, use first headline/primary_text only (strings, not lists)
    carousel_headline = headline[0] if isinstance(headline, list) else headline
    carousel_text = primary_text[0] if isinstance(primary_text, list) else primary_text

    creative_name = f"{ad_name}_creative"
    creative_id = create_carousel_creative(
        config, name=creative_name, media_refs=media_refs,
        headline=carousel_headline, primary_text=carousel_text,
        description=description, destination_url=destination_url, cta=cta,
        url_tags=url_tags,
    )

    full_ad_name = _build_ad_name(config, ad_name)
    ad_id = create_ad(config, full_ad_name, adset_id, creative_id)

    return {
        "ad_name": ad_name, "ad_id": ad_id, "creative_id": creative_id,
        "media_type": "carousel", "media_ref": None,
    }


def _process_flex_ad(config: dict, adset_id: str, all_ads: list[dict],
                     batch_fields: dict, download_dir: str, dry_run: bool,
                     url_tags: str = "") -> dict:
    """Flexible Ad: combine ALL ad records into 1 flex creative + 1 ad.

    Collects all creatives (images/videos) and all unique text variations
    from every Ad record, bundles them into a single asset_feed_spec creative
    in a dynamic ad set.
    """
    destination_url = batch_fields.get("destination_url", "")
    cta = batch_fields.get("cta", "LEARN_MORE")

    # Collect all unique headlines, primary texts, descriptions
    all_headlines = []
    all_primary_texts = []
    all_descriptions = []
    all_attachments = []

    for ad_data in all_ads:
        fields = ad_data.get("fields", {})
        h = fields.get("headline", "")
        pt = fields.get("primary_text", "")
        desc = fields.get("description", "")

        # Flatten lists/strings into unique headline/text pools
        for val in (h if isinstance(h, list) else [h] if h else []):
            if val and val not in all_headlines:
                all_headlines.append(val)
        for val in (pt if isinstance(pt, list) else [pt] if pt else []):
            if val and val not in all_primary_texts:
                all_primary_texts.append(val)
        if desc and desc not in all_descriptions:
            all_descriptions.append(desc)

        for att in ad_data.get("attachments", []):
            all_attachments.append(att)

    print(f"    Flex totals: {len(all_attachments)} creatives, "
          f"{len(all_headlines)} headlines, {len(all_primary_texts)} primary texts")

    if dry_run:
        for att in all_attachments:
            print(f"    Creative: {att['name']} ({detect_media_type(att['name'])})")
        print(f"    Headlines: {all_headlines}")
        print(f"    [DRY RUN] Would create flex creative + ad")
        return {"ad_name": "Flex Ad", "ad_id": "DRY_RUN", "creative_id": "DRY_RUN"}

    if not all_attachments:
        raise ValueError("Flexible ad has no creative files attached")

    # Upload all attachments
    media_refs = [_download_and_upload(config, att, download_dir) for att in all_attachments]

    # Build asset_feed_spec with all creatives + all text variants
    adset_name = str(batch_fields.get("adset_name", "") or "").strip() or "Flex"
    creative_name = f"{adset_name}_flex_creative"
    creative_id = create_ad_creative(
        config, name=creative_name,
        media_type=media_refs[0]["type"], media_ref=media_refs[0]["ref"],
        headline=all_headlines, primary_text=all_primary_texts,
        description=all_descriptions[0] if all_descriptions else "",
        destination_url=destination_url, cta=cta,
        additional_media_refs=media_refs[1:] if len(media_refs) > 1 else None,
        url_tags=url_tags,
    )

    full_ad_name = _build_ad_name(config, f"{adset_name}_flex")
    ad_id = create_ad(config, full_ad_name, adset_id, creative_id)

    return {
        "ad_name": f"{adset_name}_flex",
        "ad_id": ad_id,
        "creative_id": creative_id,
        "media_type": "flex",
        "media_ref": None,
    }


def process_ad(config: dict, adset_id: str, ad_data: dict, batch_fields: dict,
               download_dir: str, dry_run: bool, url_tags: str = "") -> dict:
    """Process a single ad: download creative, upload to Meta, create ad.

    Routes to format-specific handler based on Ad Format field.
    Returns dict with created object IDs.
    """
    ad_name = ad_data["ad_name"]
    fields = ad_data.get("fields", {})
    attachments = ad_data.get("attachments", [])
    ad_format = fields.get("ad_format", "Single Image/Video")

    headline = fields.get("headline", "")
    primary_text = fields.get("primary_text", "")
    description = fields.get("description", "")
    destination_url = batch_fields.get("destination_url", "")
    cta = batch_fields.get("cta", "LEARN_MORE")

    print(f"\n  Processing ad: {ad_name} [{ad_format}]")
    if isinstance(headline, list):
        print(f"    Headlines ({len(headline)} options): {headline}")
    else:
        print(f"    Headline: {headline}")
    pt_preview = primary_text if isinstance(primary_text, str) else primary_text[0] if primary_text else ""
    print(f"    Primary text: {pt_preview[:80]}...")
    print(f"    CTA: {cta}")
    print(f"    URL: {destination_url}")
    print(f"    Attachments: {len(attachments)}")

    if dry_run:
        for att in attachments:
            print(f"    Creative: {att['name']} ({detect_media_type(att['name'])})")
        if not attachments:
            print(f"    Creative: [no file attached yet]")
        print(f"    [DRY RUN] Would upload creative(s), create ad creative, create ad")
        return {"ad_name": ad_name, "ad_id": "DRY_RUN", "creative_id": "DRY_RUN"}

    if not attachments:
        raise ValueError(f"Ad '{ad_name}' has no creative file attached")

    if ad_format == "Carousel":
        return _process_carousel_ad(
            config, adset_id, ad_name, attachments,
            headline, primary_text, description, destination_url, cta, download_dir,
            url_tags=url_tags,
        )
    elif ad_format == "Multi-Placement":
        return _process_multi_placement_ad(
            config, adset_id, ad_name, attachments,
            headline, primary_text, description, destination_url, cta, download_dir,
            url_tags=url_tags,
        )
    else:
        # Single Image/Video (standard) — or Flexible handled separately
        return _process_single_ad(
            config, adset_id, ad_name, attachments,
            headline, primary_text, description, destination_url, cta, download_dir,
            url_tags=url_tags,
        )


def run_launcher(client_slug: str, record_id: str, dry_run: bool = False) -> dict:
    """Run the FB Ads Launcher programmatically.

    Returns a summary dict on success, raises on failure.
    Can be called from CLI (main()) or from the Modal webhook.
    """
    print(f"\n{'='*60}")
    print(f"FB Ads Launcher — {client_slug}")
    print(f"Record ID: {record_id}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*60}")

    # 1. Load config
    print("\n1. Loading configuration...")
    config = load_all(client_slug)

    config_errors = validate_config(config)
    if config_errors:
        raise ValueError(f"Configuration errors: {'; '.join(config_errors)}")
    print("  Config loaded successfully")

    # 2. Read Airtable brief
    print("\n2. Reading Airtable brief...")
    brief = get_batch_brief(record_id, config)

    batch_fields = brief["batch_fields"]
    print(f"  Task: {brief['task_name']}")
    print(f"  Ads: {len(brief['ads'])} subtask(s)")
    print(f"  Fields: {json.dumps(batch_fields, indent=4, default=str)}")

    # 3. Validate brief
    print("\n3. Validating brief...")
    brief_errors = validate_brief(brief, batch_fields, dry_run=dry_run)
    if brief_errors:
        raise ValueError(f"Brief validation errors: {'; '.join(brief_errors)}")
    print("  Brief is valid")

    # 4. Build targeting spec
    print("\n4. Building targeting spec...")
    targeting_spec = build_targeting_spec(config, batch_fields)
    print(f"  Targeting: {json.dumps(targeting_spec, indent=2)}")

    # Track created objects for error reporting
    created_objects = []
    campaign_id = None
    campaign_name = None

    try:
        # 5. Find or create campaign
        print("\n5. Campaign...")
        campaign_id, campaign_name = find_or_create_campaign(config, batch_fields, dry_run)
        created_objects.append(("campaign", campaign_id))

        # Inject resolved campaign name into batch_fields for ad set naming
        batch_fields["_resolved_campaign_name"] = campaign_name

        # Build url_tags for ad-level UTM parameters
        utm_defaults = config.get("utm_defaults", {})
        url_tags = "&".join(f"{k}={v}" for k, v in utm_defaults.items()) if utm_defaults else ""
        if url_tags:
            print(f"  URL tags: {url_tags}")

        # 6. Create ad set(s) + ads
        #
        # Format routing:
        #   - Standard / Multi-Placement / Carousel: 1 ad set, N ads (non-dynamic)
        #   - Flexible: 1 dynamic ad set, 1 flex ad with ALL creatives + text variants
        print("\n6. Ad Set(s)...")
        download_dir = tempfile.mkdtemp(prefix="fb-ads-launcher-")
        ad_results = []

        # Check if any ad is Flexible format
        is_flex = any(
            ad.get("fields", {}).get("ad_format") == "Flexible"
            for ad in brief["ads"]
        )

        if is_flex:
            # ── Flexible Ad: combine ALL creatives + text variants into 1 ad ──
            print("  Mode: Flexible Ad (1 dynamic ad set, 1 ad with all creatives)")

            adset_id = find_or_create_adset(
                config, campaign_id, batch_fields, targeting_spec, dry_run,
                is_dynamic_creative=True,
            )
            created_objects.append(("adset", adset_id))

            print("\n7. Building flex creative...")
            result = _process_flex_ad(
                config, adset_id, brief["ads"], batch_fields, download_dir, dry_run,
                url_tags=url_tags,
            )
            ad_results.append(result)
            created_objects.append(("ad", result.get("ad_id", "unknown")))
        else:
            # ── Standard / Multi-Placement / Carousel: 1 ad set, multiple ads ──
            adset_id = find_or_create_adset(
                config, campaign_id, batch_fields, targeting_spec, dry_run,
                is_dynamic_creative=False,
            )
            created_objects.append(("adset", adset_id))

            print("\n7. Creating ads...")
            for ad_data in brief["ads"]:
                result = process_ad(
                    config, adset_id, ad_data, batch_fields, download_dir, dry_run,
                    url_tags=url_tags,
                )
                ad_results.append(result)
                created_objects.append(("ad", result.get("ad_id", "unknown")))

    except (MetaApiError, ValueError, RuntimeError) as e:
        print(f"\nERROR: {e}")
        print(f"Objects created before failure:")
        for obj_type, obj_id in created_objects:
            print(f"  {obj_type}: {obj_id}")

        # Send failure notification
        if notify_failure and config.get("slack_webhook_url"):
            try:
                notify_failure(
                    config["slack_webhook_url"],
                    client_slug=client_slug,
                    error=str(e),
                    created_objects=created_objects,
                    task_url=brief.get("task_url", ""),
                )
            except Exception:
                pass
        raise

    # 8. Summary
    adset_ids = [obj_id for obj_type, obj_id in created_objects if obj_type == "adset"]
    ads_manager_url = (
        f"https://adsmanager.facebook.com/adsmanager/manage/campaigns"
        f"?act={config['fb_ad_account_id']}"
    )

    summary = {
        "client_slug": client_slug,
        "record_id": record_id,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "adset_ids": adset_ids,
        "ad_results": ad_results,
        "ads_manager_url": ads_manager_url,
        "dry_run": dry_run,
    }

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Client: {client_slug}")
    print(f"Campaign ID: {campaign_id}")
    print(f"Ad Set(s): {', '.join(adset_ids)}")
    print(f"Ads created: {len(ad_results)}")
    for r in ad_results:
        print(f"  - {r['ad_name']} (ID: {r.get('ad_id', 'N/A')})")
    print(f"Status: ALL PAUSED")

    if not dry_run:
        print(f"\nView in Ads Manager: {ads_manager_url}")
        print(f"\nTo activate:")
        print(f"  python3 skills/fb-ads-launcher/scripts/activate_ads.py {client_slug} {campaign_id}")

        # 9. Write results back to Airtable
        print("\n8. Updating Airtable...")
        write_meta_ids(
            record_id,
            campaign_id=campaign_id,
            adset_ids=adset_ids,
            ad_ids=[r.get("ad_id", "") for r in ad_results],
            config=config,
            launch_date=batch_fields.get("launch_date", ""),
        )

        # Write individual Meta Ad IDs back to each Ad record
        for i, result in enumerate(ad_results):
            ad_record_id = brief["ads"][i].get("task_id", "")
            meta_ad_id = result.get("ad_id", "")
            if ad_record_id and meta_ad_id and meta_ad_id != "DRY_RUN":
                write_ad_meta_id(ad_record_id, meta_ad_id, config)

        # Write a launch summary note
        note = (
            f"Ads Created (PAUSED)\n\n"
            f"Campaign ID: {campaign_id}\n"
            f"Ad Set(s): {', '.join(adset_ids)}\n"
            f"Ads: {len(ad_results)}\n\n"
            f"View: {ads_manager_url}\n\n"
            f"To activate:\n"
            f"python3 agents/fb-ads-launcher/scripts/activate_ads.py {client_slug} {campaign_id}"
        )
        add_task_comment(record_id, note, config)

        # 10. Send Slack notification
        if notify_success and config.get("slack_webhook_url"):
            try:
                notify_success(
                    config["slack_webhook_url"],
                    client_slug=client_slug,
                    campaign_name=campaign_name,
                    campaign_id=campaign_id,
                    adset_id=", ".join(adset_ids),
                    num_ads=len(ad_results),
                    daily_budget=batch_fields.get("daily_budget", 0),
                    ads_manager_url=ads_manager_url,
                )
            except Exception as e:
                print(f"  Warning: Slack notification failed: {e}")

    print("\nDone.")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Read an Airtable Ad Set brief and launch Facebook/Meta ads"
    )
    parser.add_argument("client_slug", help="Client slug (e.g., bc_bella_coterie)")
    parser.add_argument("record_id", help="Airtable Ad Set record ID (recXXXXXX)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be created without calling Meta API")
    args = parser.parse_args()

    try:
        run_launcher(args.client_slug, args.record_id, dry_run=args.dry_run)
    except Exception as e:
        print(f"\nFATAL: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
