#!/usr/bin/env python3
"""
Register a ClickUp webhook for the FB Ads Launcher.

Usage:
    # Register a new webhook
    python3 skills/fb-ads-launcher/scripts/setup_webhook.py <modal_webhook_url>

    # List existing webhooks
    python3 skills/fb-ads-launcher/scripts/setup_webhook.py --list

    # Delete a webhook
    python3 skills/fb-ads-launcher/scripts/setup_webhook.py --delete <webhook_id>
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(WORKSPACE_ROOT / ".env")

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY", "")
CLICKUP_TEAM_ID = os.getenv("CLICKUP_TEAM_ID", "")
CLICKUP_BASE = "https://api.clickup.com/api/v2"


def _headers():
    return {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}


def list_webhooks():
    """List all webhooks for the team."""
    resp = requests.get(
        f"{CLICKUP_BASE}/team/{CLICKUP_TEAM_ID}/webhook",
        headers=_headers(),
        timeout=30,
    )
    if not resp.ok:
        print(f"Error listing webhooks: {resp.status_code} {resp.text[:200]}")
        return

    webhooks = resp.json().get("webhooks", [])
    if not webhooks:
        print("No webhooks registered.")
        return

    print(f"Found {len(webhooks)} webhook(s):\n")
    for wh in webhooks:
        print(f"  ID: {wh['id']}")
        print(f"  Endpoint: {wh['endpoint']}")
        print(f"  Events: {', '.join(wh.get('events', []))}")
        print(f"  Status: {'active' if wh.get('health', {}).get('status') == 'active' else 'unknown'}")
        print()


def register_webhook(endpoint_url: str):
    """Register a new ClickUp webhook for taskStatusUpdated events."""
    payload = {
        "endpoint": endpoint_url,
        "events": ["taskStatusUpdated"],
    }

    resp = requests.post(
        f"{CLICKUP_BASE}/team/{CLICKUP_TEAM_ID}/webhook",
        headers=_headers(),
        json=payload,
        timeout=30,
    )

    if not resp.ok:
        print(f"Error registering webhook: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)

    data = resp.json()
    webhook_id = data.get("id", data.get("webhook", {}).get("id", "unknown"))
    print(f"Webhook registered successfully!")
    print(f"  ID: {webhook_id}")
    print(f"  Endpoint: {endpoint_url}")
    print(f"  Events: taskStatusUpdated")
    print(f"\nNow when any task status changes to 'Ready to Launch',")
    print(f"the FB Ads Launcher will run automatically.")


def delete_webhook(webhook_id: str):
    """Delete a webhook by ID."""
    resp = requests.delete(
        f"{CLICKUP_BASE}/webhook/{webhook_id}",
        headers=_headers(),
        timeout=30,
    )

    if resp.ok:
        print(f"Webhook {webhook_id} deleted.")
    else:
        print(f"Error deleting webhook: {resp.status_code} {resp.text[:200]}")


def main():
    parser = argparse.ArgumentParser(description="Manage ClickUp webhooks for FB Ads Launcher")
    parser.add_argument("endpoint_url", nargs="?", help="Modal webhook URL to register")
    parser.add_argument("--list", action="store_true", help="List existing webhooks")
    parser.add_argument("--delete", metavar="WEBHOOK_ID", help="Delete a webhook by ID")
    args = parser.parse_args()

    if not CLICKUP_API_KEY or not CLICKUP_TEAM_ID:
        print("ERROR: CLICKUP_API_KEY and CLICKUP_TEAM_ID must be set in .env")
        sys.exit(1)

    if args.list:
        list_webhooks()
    elif args.delete:
        delete_webhook(args.delete)
    elif args.endpoint_url:
        register_webhook(args.endpoint_url)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
