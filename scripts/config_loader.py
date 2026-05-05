#!/usr/bin/env python3
from __future__ import annotations
"""
Config Loader for FB Ads Launcher
Loads client credentials, fb_ads_config.json, and Airtable table routing.

Usage:
    from config_loader import load_all
    config = load_all("bc_bella_coterie")
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# scripts/foo.py — repo root is parents[1]
# Modal: scripts are mounted at /app/scripts/ (parents[1] = /app)
try:
    WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
except IndexError:
    WORKSPACE_ROOT = Path("/app")
# In Modal, client configs are mounted at /app/clients
_CLIENTS_DIR_OVERRIDE = os.getenv("FB_ADS_CLIENTS_DIR", "")


def load_all(client_slug: str) -> dict:
    """Load credentials and config for a client.

    Returns a dict with all credentials and settings needed
    for Meta API and ClickUp operations.
    """
    # Load root .env first, then client-specific overrides
    root_env = WORKSPACE_ROOT / ".env"
    if root_env.exists():
        load_dotenv(root_env)

    # Determine clients directory (local workspace or Modal mount)
    clients_dir = Path(_CLIENTS_DIR_OVERRIDE) if _CLIENTS_DIR_OVERRIDE else WORKSPACE_ROOT / "clients"

    client_env = clients_dir / client_slug / "credentials" / "secrets.env"
    if client_env.exists():
        load_dotenv(client_env, override=True)

    # Load fb_ads_config.json
    config_path = clients_dir / client_slug / "fb_ads_config.json"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Missing fb_ads_config.json at {config_path}\n"
            f"Create it with fb_page_id, naming_convention, utm_defaults, etc."
        )

    with open(config_path) as f:
        ads_config = json.load(f)

    return {
        # Credentials
        "fb_access_token": os.getenv("FB_ACCESS_TOKEN", ""),
        "fb_ad_account_id": os.getenv("FB_AD_ACCOUNT_ID", "") or ads_config.get("fb_ad_account_id", ""),
        "airtable_api_key": os.getenv("AIRTABLE_API_KEY", ""),
        "slack_webhook_url": os.getenv("SLACK_WEBHOOK_URL", ""),
        # Airtable table routing (per-client base)
        "airtable_base_id": ads_config.get("airtable_base_id", ""),
        "airtable_ad_sets_table_id": ads_config.get("airtable_ad_sets_table_id", ""),
        "airtable_ads_table_id": ads_config.get("airtable_ads_table_id", ""),
        # From fb_ads_config.json
        "fb_page_id": ads_config.get("fb_page_id", ""),
        "instagram_user_id": ads_config.get("instagram_user_id", ""),
        "default_optimization_goal": ads_config.get("default_optimization_goal", "OFFSITE_CONVERSIONS"),
        "default_billing_event": ads_config.get("default_billing_event", "IMPRESSIONS"),
        "default_pixel_id": ads_config.get("default_pixel_id", ""),
        "default_geo_locations": ads_config.get("default_geo_locations", {"countries": ["US"]}),
        "naming_convention": ads_config.get("naming_convention", {}),
        "utm_defaults": ads_config.get("utm_defaults", {}),
        # Meta
        "client_slug": client_slug,
    }


def validate_config(config: dict) -> list[str]:
    """Return a list of error messages. Empty list means valid.

    Checks required fields and warns about optional-but-recommended fields.
    Warnings are printed but not included in the returned error list.
    """
    errors = []
    if not config["fb_access_token"]:
        errors.append("FB_ACCESS_TOKEN is missing from .env")
    if not config["fb_ad_account_id"]:
        errors.append("FB_AD_ACCOUNT_ID is missing from client secrets.env")
    if not config["airtable_api_key"]:
        errors.append("AIRTABLE_API_KEY is missing from .env")
    if not config["airtable_base_id"]:
        errors.append("airtable_base_id is missing from fb_ads_config.json")
    if not config.get("airtable_ad_sets_table_id"):
        errors.append("airtable_ad_sets_table_id is missing from fb_ads_config.json")
    if not config.get("airtable_ads_table_id"):
        errors.append("airtable_ads_table_id is missing from fb_ads_config.json")
    if not config["fb_page_id"]:
        errors.append("fb_page_id is missing from fb_ads_config.json")

    # Warnings (not blocking, but printed)
    if not config.get("instagram_user_id"):
        print("  [WARN] instagram_user_id is empty — ads will be Facebook-only (can be auto-resolved)")
    opt_goal = config.get("default_optimization_goal", "")
    if "CONVERSION" in opt_goal.upper() and not config.get("default_pixel_id"):
        print("  [WARN] default_pixel_id is empty but optimization goal is CONVERSIONS — tracking may not work")

    return errors


def build_name(template: str, **kwargs) -> str:
    """Render a naming convention template with provided values.

    Example:
        build_name("{date}_{phase}_{geo}", date="2026-02-25", phase="testing", geo="us")
        → "2026-02-25_testing_us"
    """
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Naming template requires {e} but it was not provided")


def build_destination_url(base_url: str, utm_defaults: dict, **overrides) -> str:
    """Append UTM parameters to a destination URL.

    utm_defaults may contain template variables like {campaign_name}.
    overrides provides the values for those templates (e.g. campaign_name="...").
    Only utm_* keys are included in the final URL.
    """
    # Resolve template variables in UTM default values
    # Skip Meta dynamic parameters like {{campaign.name}} (double curly braces)
    resolved = {}
    for key, value in utm_defaults.items():
        if isinstance(value, str) and "{" in value and "{{" not in value:
            try:
                resolved[key] = value.format(**overrides)
            except KeyError:
                resolved[key] = value
        else:
            resolved[key] = value

    if not resolved:
        return base_url

    separator = "&" if "?" in base_url else "?"
    params = "&".join(f"{k}={v}" for k, v in resolved.items())
    return f"{base_url}{separator}{params}"
