#!/usr/bin/env python3
from __future__ import annotations
"""
Slack Notifier for FB Ads Launcher.
Sends success/failure notifications via Slack webhook.

Usage:
    from notifier import notify_success, notify_failure
"""

import requests


def notify_success(webhook_url: str, client_slug: str, campaign_name: str,
                   campaign_id: str, adset_id: str, num_ads: int,
                   daily_budget: float, ads_manager_url: str) -> bool:
    """Send a success notification to Slack."""
    if not webhook_url:
        return False

    text = (
        f":white_check_mark: *Ads Created — {client_slug}*\n"
        f"Campaign: `{campaign_name}` (ID: {campaign_id})\n"
        f"Ad Set ID: {adset_id}\n"
        f"Ads: {num_ads} created (PAUSED)\n"
        f"Budget: ${daily_budget}/day\n"
        f"<{ads_manager_url}|View in Ads Manager>\n\n"
        f"To activate:\n"
        f"```python3 scripts/activate_ads.py {client_slug} {campaign_id}```"
    )

    return _send(webhook_url, text)


def notify_failure(webhook_url: str, client_slug: str, error: str,
                   created_objects: list[tuple], task_url: str = "") -> bool:
    """Send a failure notification to Slack."""
    if not webhook_url:
        return False

    objects_str = ""
    if created_objects:
        objects_str = "\nObjects created before failure:\n"
        for obj_type, obj_id in created_objects:
            objects_str += f"  • {obj_type}: {obj_id}\n"

    task_link = f"\n<{task_url}|ClickUp Task>" if task_url else ""

    text = (
        f":x: *Ad Upload Failed — {client_slug}*\n"
        f"Error: {error}\n"
        f"{objects_str}"
        f"{task_link}"
    )

    return _send(webhook_url, text)


def notify_launch_error(webhook_url: str, client_slug: str, error: str,
                        record_id: str = "") -> bool:
    """Send an actionable error notification to Slack.

    Classifies the error and provides clear next-step guidance so
    the user knows exactly what to fix.
    """
    if not webhook_url:
        return False

    error_lower = error.lower()

    # Classify error and build guidance
    if "invalid_permissions" in error_lower or "403" in error_lower:
        category = "Airtable Permissions"
        guidance = (
            "Your Airtable token doesn't have access to this base.\n"
            "*Fix:* Go to airtable.com/create/tokens → edit your token → add the base to its scopes."
        )
    elif "validation error" in error_lower or "brief validation" in error_lower:
        category = "Validation Error"
        # Extract the specific field issue from the error message
        guidance = (
            "*Fix:* Check the flagged fields in Airtable and re-trigger.\n"
            "Common issues: missing creatives, wrong ad format, empty required fields."
        )
    elif "configuration error" in error_lower:
        category = "Configuration Error"
        guidance = (
            "*Fix:* Check the client's `fb_ads_config.json` and Modal secrets.\n"
            "Verify: ad account ID, page ID, pixel ID, API keys."
        )
    elif "metaapierror" in error_lower or "facebook" in error_lower or "meta" in error_lower:
        category = "Meta API Error"
        guidance = (
            "*Fix:* Check your Meta access token (may be expired) or ad account permissions.\n"
            "If token expired: update in Modal secrets and redeploy."
        )
    elif "airtable" in error_lower and ("404" in error_lower or "not_found" in error_lower):
        category = "Airtable Not Found"
        guidance = (
            "*Fix:* The Airtable record or table wasn't found. Check that:\n"
            "• The base ID and table IDs in `fb_ads_config.json` are correct\n"
            "• The record hasn't been deleted"
        )
    else:
        category = "Launch Error"
        guidance = "*Fix:* Check Modal logs for details (`modal app logs fb-ads-launcher`)."

    airtable_link = ""
    if record_id:
        airtable_link = f"\nRecord ID: `{record_id}`"

    text = (
        f":rotating_light: *Ad Launch Failed — {client_slug}*\n"
        f"*Type:* {category}\n"
        f"*Error:* {error}\n"
        f"{airtable_link}\n\n"
        f"{guidance}"
    )

    return _send(webhook_url, text)


def _send(webhook_url: str, text: str) -> bool:
    """Send a message to a Slack webhook."""
    try:
        resp = requests.post(
            webhook_url,
            json={"text": text},
            timeout=10,
        )
        return resp.ok
    except Exception as e:
        print(f"  Slack notification error: {e}")
        return False
