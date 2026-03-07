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
        f"```python3 skills/fb-ads-launcher/scripts/activate_ads.py {client_slug} {campaign_id}```"
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
