#!/usr/bin/env python3
"""
Pre-flight validation for FB Ads Launcher.
Checks API connectivity, account access, and config completeness
before any Meta objects are created.

Used by:
  - main.py (automated launches via webhook)
  - test_connection.py (manual CLI checks)
  - modal_webhook.py (health endpoint)
"""

from __future__ import annotations

import requests

META_API_VERSION = "v21.0"
META_BASE = f"https://graph.facebook.com/{META_API_VERSION}"


# ─── Individual Check Functions ──────────────────────────────────────────────
# Each returns (ok: bool, message: str)
# message is descriptive on success, error detail on failure.


def check_meta_token(access_token: str) -> tuple[bool, str]:
    """Verify the Meta access token is valid."""
    if not access_token:
        return False, "FB_ACCESS_TOKEN is empty"
    try:
        resp = requests.get(
            f"{META_BASE}/me",
            params={"access_token": access_token},
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"Network error checking Meta token: {e}"
    if resp.ok:
        data = resp.json()
        name = data.get("name", data.get("id", "unknown"))
        return True, f"Token valid — user: {name}"
    return False, f"Token INVALID [{resp.status_code}]: {resp.text[:200]}"


def check_ad_account(access_token: str, ad_account_id: str) -> tuple[bool, str]:
    """Verify the ad account is accessible."""
    if not ad_account_id:
        return False, "fb_ad_account_id is empty"
    try:
        resp = requests.get(
            f"{META_BASE}/act_{ad_account_id}",
            params={"access_token": access_token, "fields": "name,account_status"},
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"Network error checking ad account: {e}"
    if resp.ok:
        data = resp.json()
        name = data.get("name", "unnamed")
        status = data.get("account_status")
        return True, f"Ad account OK — {name} (status: {status})"
    return False, f"Ad account FAILED [{resp.status_code}]: {resp.text[:200]}"


def check_page(access_token: str, page_id: str) -> tuple[bool, str]:
    """Verify the Facebook Page is accessible."""
    if not page_id:
        return False, "fb_page_id is empty"
    try:
        resp = requests.get(
            f"{META_BASE}/{page_id}",
            params={"access_token": access_token, "fields": "name,id"},
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"Network error checking page: {e}"
    if resp.ok:
        data = resp.json()
        return True, f"Page OK — {data.get('name', 'unnamed')} ({data.get('id')})"
    # Permission errors (#10) mean the page exists but we can't read its metadata.
    # This is OK — we can still use the page for ad creatives.
    error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    error_code = error_data.get("error", {}).get("code", 0)
    if error_code == 10:
        return True, f"Page OK (no read permission, but usable for ads) ({page_id})"
    return False, f"Page FAILED [{resp.status_code}]: {resp.text[:200]}"


def check_instagram(access_token: str, page_id: str, ig_user_id: str) -> tuple[bool, str]:
    """Verify the Instagram account is accessible and authorized for the page.

    If ig_user_id is empty, tries to auto-resolve from the page.
    Returns the resolved ig_user_id in the message on success.
    """
    if not page_id:
        return False, "Cannot check Instagram without fb_page_id"

    # If we have an explicit IG user ID, verify it's valid
    if ig_user_id:
        try:
            resp = requests.get(
                f"{META_BASE}/{ig_user_id}",
                params={"access_token": access_token, "fields": "id,username"},
                timeout=15,
            )
        except requests.RequestException as e:
            return False, f"Network error checking Instagram account: {e}"
        if resp.ok:
            data = resp.json()
            username = data.get("username", "")
            return True, f"Instagram OK — @{username} ({ig_user_id})"
        return False, f"Instagram user {ig_user_id} not accessible [{resp.status_code}]: {resp.text[:200]}"

    # No IG user ID configured — not an error, just a warning
    return True, "No Instagram account configured (Facebook-only placements)"


def check_pixel(access_token: str, pixel_id: str) -> tuple[bool, str]:
    """Verify the Meta pixel is accessible."""
    if not pixel_id:
        return True, "No pixel configured (tracking disabled)"
    try:
        resp = requests.get(
            f"{META_BASE}/{pixel_id}",
            params={"access_token": access_token, "fields": "id,name"},
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"Network error checking pixel: {e}"
    if resp.ok:
        data = resp.json()
        return True, f"Pixel OK — {data.get('name', 'unnamed')} ({pixel_id})"
    return False, f"Pixel FAILED [{resp.status_code}]: {resp.text[:200]}"


def check_airtable(api_key: str, base_id: str) -> tuple[bool, str]:
    """Verify the Airtable API key and base access."""
    if not api_key:
        return False, "AIRTABLE_API_KEY is empty"
    if not base_id:
        return False, "airtable_base_id is empty"
    try:
        resp = requests.get(
            f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"Network error checking Airtable: {e}"
    if resp.ok:
        tables = resp.json().get("tables", [])
        table_names = [t.get("name", "?") for t in tables]
        return True, f"Airtable OK — {len(tables)} table(s): {', '.join(table_names)}"
    return False, f"Airtable FAILED [{resp.status_code}]: {resp.text[:200]}"


# ─── Instagram Resolution ────────────────────────────────────────────────────


def resolve_instagram(config: dict) -> str:
    """Resolve Instagram user ID from the page, updating config in-place.

    Tries:
    1. Config value (already set)
    2. Page's instagram_business_account / connected_instagram_account fields
    3. Page's /instagram_accounts edge

    Returns the resolved ig_user_id (empty string if none found).
    """
    # If IG was explicitly stripped by self-healing, don't re-resolve
    if config.get("_ig_stripped"):
        print("  Instagram stripped by self-healing — skipping resolution")
        return ""

    ig_id = config.get("instagram_user_id", "")
    if ig_id:
        return ig_id

    page_id = config.get("fb_page_id", "")
    if not page_id:
        return ""

    access_token = config["fb_access_token"]

    # Method 1: Page fields
    try:
        resp = requests.get(
            f"{META_BASE}/{page_id}",
            params={
                "access_token": access_token,
                "fields": "instagram_business_account,connected_instagram_account",
            },
            timeout=15,
        )
        if resp.ok:
            data = resp.json()
            for field in ("instagram_business_account", "connected_instagram_account"):
                ig_account = data.get(field, {})
                ig_id = ig_account.get("id", "") if isinstance(ig_account, dict) else ""
                if ig_id:
                    print(f"  Auto-resolved Instagram user ID from page ({field}): {ig_id}")
                    config["instagram_user_id"] = ig_id
                    return ig_id
    except Exception as e:
        print(f"  Warning: Could not fetch Instagram account from page fields: {e}")

    # Method 2: /instagram_accounts edge
    try:
        resp = requests.get(
            f"{META_BASE}/{page_id}/instagram_accounts",
            params={"access_token": access_token, "fields": "id,username"},
            timeout=15,
        )
        if resp.ok:
            accounts = resp.json().get("data", [])
            if accounts:
                ig_id = accounts[0].get("id", "")
                if ig_id:
                    username = accounts[0].get("username", "")
                    print(f"  Auto-resolved Instagram user ID from page edge: {ig_id} ({username})")
                    config["instagram_user_id"] = ig_id
                    return ig_id
    except Exception as e:
        print(f"  Warning: Could not fetch Instagram accounts from page edge: {e}")

    print(f"  No Instagram account found for page {page_id}")
    return ""


# ─── Full Pre-flight ─────────────────────────────────────────────────────────


def run_preflight(config: dict) -> list[str]:
    """Run all pre-flight checks against a loaded config.

    Returns a list of error messages. Empty list means all checks passed.
    Also prints status for each check (useful for logging).
    """
    errors = []
    warnings = []

    token = config.get("fb_access_token", "")
    ad_account_id = config.get("fb_ad_account_id", "")
    page_id = config.get("fb_page_id", "")
    ig_user_id = config.get("instagram_user_id", "")
    pixel_id = config.get("default_pixel_id", "")
    airtable_key = config.get("airtable_api_key", "")
    base_id = config.get("airtable_base_id", "")

    checks = [
        ("Meta Token", check_meta_token(token)),
        ("Ad Account", check_ad_account(token, ad_account_id)),
        ("Facebook Page", check_page(token, page_id)),
        ("Instagram", check_instagram(token, page_id, ig_user_id)),
        ("Pixel", check_pixel(token, pixel_id)),
        ("Airtable", check_airtable(airtable_key, base_id)),
    ]

    for name, (ok, msg) in checks:
        if ok:
            print(f"  [OK] {name}: {msg}")
            # Treat "no Instagram configured" as a warning, not error
            if "No Instagram" in msg or "No pixel" in msg:
                warnings.append(f"{name}: {msg}")
        else:
            print(f"  [FAIL] {name}: {msg}")
            errors.append(f"{name}: {msg}")

    if warnings:
        for w in warnings:
            print(f"  [WARN] {w}")

    return errors
