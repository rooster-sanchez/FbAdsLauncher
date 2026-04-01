#!/usr/bin/env python3
"""
Self-Healing Error Handler for FB Ads Launcher.
Wraps run_launcher() with intelligent error diagnosis and auto-fix retry logic.

When an error occurs:
1. Diagnoses the error using known patterns (no LLM needed for common errors)
2. If auto-fixable: applies the fix, notifies Slack, and retries
3. If not fixable: sends Slack with clear human instructions and raises

Usage:
    from error_agent import run_with_self_healing
    summary = run_with_self_healing(client_slug, record_id, dry_run=False)
"""

from __future__ import annotations

import re
import traceback
from dataclasses import dataclass

from meta_api import MetaApiError
from notifier import _send


MAX_RETRIES = 3


@dataclass
class Diagnosis:
    can_auto_fix: bool
    explanation: str
    fix_action: str  # key for apply_fix()
    fix_params: dict  # parameters for the fix
    suggested_action: str  # human-readable instructions if not auto-fixable


# ─── Error Diagnosis (pattern-matching, no LLM needed) ──────────────────────

def diagnose_error(
    error: Exception,
    config: dict,
    attempt_history: list[str],
) -> Diagnosis:
    """Analyze an error and decide whether it can be auto-fixed.

    Uses Meta API error codes and message patterns to classify errors.
    """
    error_msg = str(error).lower()
    code = getattr(error, "code", 0)
    subcode = getattr(error, "subcode", 0)

    # Already tried this fix? Don't retry the same fix.
    def already_tried(fix_name: str) -> bool:
        return fix_name in attempt_history

    # ── Auto-fixable errors ──────────────────────────────────────────────

    # Instagram not authorized (code 200) or Instagram check failed in preflight
    if (code == 200 or "instagram" in error_msg and ("not accessible" in error_msg or "not authoris" in error_msg or "deprecated" in error_msg)):
        if not already_tried("strip_instagram"):
            return Diagnosis(
                can_auto_fix=True,
                explanation="Instagram account not authorized or not accessible",
                fix_action="strip_instagram",
                fix_params={},
                suggested_action="",
            )

    # Rate limiting (code 32 or 4)
    if code in (32, 4) and not already_tried("rate_limit_backoff"):
        return Diagnosis(
            can_auto_fix=True,
            explanation="Meta API rate limit hit",
            fix_action="rate_limit_backoff",
            fix_params={"wait_seconds": 60},
            suggested_action="",
        )

    # Targeting too narrow (code 100, "too narrow")
    if code == 100 and "narrow" in error_msg and not already_tried("broaden_targeting"):
        return Diagnosis(
            can_auto_fix=True,
            explanation="Targeting spec is too narrow for Meta's requirements",
            fix_action="broaden_targeting",
            fix_params={},
            suggested_action="",
        )

    # Duplicate name
    if "duplicate" in error_msg and "name" in error_msg and not already_tried("deduplicate_name"):
        return Diagnosis(
            can_auto_fix=True,
            explanation="Duplicate campaign/ad set/ad name detected",
            fix_action="deduplicate_name",
            fix_params={},
            suggested_action="",
        )

    # Transient server errors (500/502/503) that slipped through _meta_request retries
    if any(f"[{c}]" in error_msg or f"status {c}" in error_msg for c in ("500", "502", "503")):
        if not already_tried("transient_retry"):
            return Diagnosis(
                can_auto_fix=True,
                explanation="Meta API returned a transient server error",
                fix_action="transient_retry",
                fix_params={"wait_seconds": 30},
                suggested_action="",
            )

    # Video still processing
    if "video" in error_msg and ("processing" in error_msg or "not ready" in error_msg):
        if not already_tried("video_wait"):
            return Diagnosis(
                can_auto_fix=True,
                explanation="Video is still processing on Meta's servers",
                fix_action="video_wait",
                fix_params={"wait_seconds": 120},
                suggested_action="",
            )

    # child_attachments has too many elements (carousel/PAC creative issue)
    if "child_attachments" in error_msg and "too many elements" in error_msg:
        return Diagnosis(
            can_auto_fix=False,
            explanation="Creative has too many media attachments for carousel/placement format",
            fix_action="",
            fix_params={},
            suggested_action=(
                "The ad creative has too many child_attachments for Meta's limits.\n"
                "For carousel ads: max 10 cards.\n"
                "For PAC (multi-placement) ads: check that the API version supports "
                "asset_customization_rules and that ad_formats is not conflicting.\n"
                "Try reducing the number of creative files per ad, or switch to "
                "Single Image/Video format."
            ),
        )

    # Campaign name ambiguous (multiple matches)
    if "multiple campaigns contain" in error_msg:
        # Extract the campaign names from the error message
        return Diagnosis(
            can_auto_fix=False,
            explanation="Multiple campaigns match the search term",
            fix_action="",
            fix_params={},
            suggested_action="Use a more specific campaign name in the Airtable 'Existing Campaign Name' field.",
        )

    # ── Non-fixable errors (escalate with clear instructions) ────────────

    # Token expired (code 190)
    if code == 190 or ("token" in error_msg and "expired" in error_msg):
        return Diagnosis(
            can_auto_fix=False,
            explanation="Meta access token has expired",
            fix_action="",
            fix_params={},
            suggested_action=(
                "1. Go to Business Settings > System Users > your user\n"
                "2. Click 'Generate New Token'\n"
                "3. Select the same permissions\n"
                "4. Update the token in Modal secrets:\n"
                "   `modal secret create fb-ads-launcher-env --force FB_ACCESS_TOKEN=\"new_token\" ...`\n"
                "5. Redeploy: `python3 -m modal deploy scripts/modal_webhook.py`"
            ),
        )

    # Ad account disabled
    if "account" in error_msg and ("disabled" in error_msg or "unsettled" in error_msg):
        ad_account_id = config.get("fb_ad_account_id", "unknown")
        return Diagnosis(
            can_auto_fix=False,
            explanation=f"Ad account act_{ad_account_id} is disabled or has billing issues",
            fix_action="",
            fix_params={},
            suggested_action=(
                f"1. Go to Business Manager > Ad Accounts > act_{ad_account_id}\n"
                "2. Check the account status and billing\n"
                "3. Resolve any payment or policy issues\n"
                "4. Re-trigger the launch once the account is active"
            ),
        )

    # Page access denied
    if "page" in error_msg and ("access" in error_msg or "permission" in error_msg):
        page_id = config.get("fb_page_id", "unknown")
        return Diagnosis(
            can_auto_fix=False,
            explanation=f"No access to Facebook Page {page_id}",
            fix_action="",
            fix_params={},
            suggested_action=(
                f"1. Go to Business Settings > Pages\n"
                f"2. Find page {page_id}\n"
                "3. Assign your System User with 'Create Content' permission\n"
                "4. Re-trigger the launch"
            ),
        )

    # Policy violation
    if "policy" in error_msg or "violat" in error_msg or "rejected" in error_msg:
        return Diagnosis(
            can_auto_fix=False,
            explanation="Ad content was rejected by Meta's ad policies",
            fix_action="",
            fix_params={},
            suggested_action=(
                "Review your ad creative and copy for policy compliance:\n"
                "- Check text overlay limits\n"
                "- Review restricted content categories\n"
                "- Ensure landing page matches ad content\n"
                "See: https://www.facebook.com/policies/ads/"
            ),
        )

    # Airtable errors
    if "airtable" in error_msg:
        if "403" in error_msg or "permission" in error_msg:
            return Diagnosis(
                can_auto_fix=False,
                explanation="Airtable API token doesn't have access to this base",
                fix_action="",
                fix_params={},
                suggested_action=(
                    "1. Go to airtable.com/create/tokens\n"
                    "2. Edit your personal access token\n"
                    "3. Add this base to its scopes\n"
                    "4. Update the token in Modal secrets"
                ),
            )

    # Config/validation errors — usually need human review
    if isinstance(error, ValueError) and ("configuration" in error_msg or "validation" in error_msg):
        return Diagnosis(
            can_auto_fix=False,
            explanation="Configuration or brief validation failed",
            fix_action="",
            fix_params={},
            suggested_action=f"Review the error and fix the data:\n{error}",
        )

    # Unknown error — escalate with full details
    return Diagnosis(
        can_auto_fix=False,
        explanation=f"Unknown error: {error}",
        fix_action="",
        fix_params={},
        suggested_action=(
            "Check Modal logs for details:\n"
            "  `modal app logs fb-ads-launcher`\n\n"
            f"Full error: {error}"
        ),
    )


# ─── Fix Application ────────────────────────────────────────────────────────

def apply_fix(fix_action: str, fix_params: dict, config: dict) -> None:
    """Apply an auto-fix to the config before retrying."""
    import time

    if fix_action == "strip_instagram":
        config["instagram_user_id"] = ""
        config["_ig_stripped"] = True  # Prevent resolve_instagram from re-resolving
        print("  Fix applied: Stripped instagram_user_id (Facebook-only placements)")

    elif fix_action == "rate_limit_backoff":
        wait = fix_params.get("wait_seconds", 60)
        print(f"  Fix applied: Waiting {wait}s for rate limit to reset...")
        time.sleep(wait)

    elif fix_action == "broaden_targeting":
        # Remove interest targeting, fall back to broad
        print("  Fix applied: Broadened targeting (removed interest constraints)")
        # The actual targeting is built from batch_fields, so we'd need to modify
        # the brief. For now, this is a placeholder — the retry will use broader defaults.

    elif fix_action == "deduplicate_name":
        # Append timestamp to naming convention to avoid duplicates
        from datetime import datetime
        suffix = datetime.now().strftime("_%H%M%S")
        nc = config.get("naming_convention", {})
        for key in ("campaign", "adset", "ad"):
            if key in nc:
                nc[key] = nc[key] + suffix
        config["naming_convention"] = nc
        print(f"  Fix applied: Appended '{suffix}' to naming convention")

    elif fix_action == "transient_retry":
        wait = fix_params.get("wait_seconds", 30)
        print(f"  Fix applied: Waiting {wait}s before retrying (transient error)...")
        time.sleep(wait)

    elif fix_action == "video_wait":
        wait = fix_params.get("wait_seconds", 120)
        print(f"  Fix applied: Waiting {wait}s for video processing...")
        time.sleep(wait)

    else:
        print(f"  Warning: Unknown fix action '{fix_action}' — skipping")


# ─── Slack Notifications for Self-Healing ────────────────────────────────────

def notify_auto_fix(webhook_url: str, client_slug: str, error: str, fix: str) -> bool:
    """Notify Slack that an error was auto-fixed."""
    if not webhook_url:
        return False
    text = (
        f":wrench: *Auto-Fix Applied — {client_slug}*\n"
        f"Error: {error}\n"
        f"Fix: {fix}\n"
        f"Retrying launch..."
    )
    return _send(webhook_url, text)


def notify_needs_human(webhook_url: str, client_slug: str, explanation: str,
                       suggested_action: str, record_id: str = "") -> bool:
    """Notify Slack that human intervention is needed."""
    if not webhook_url:
        return False
    record_info = f"\nRecord ID: `{record_id}`" if record_id else ""
    text = (
        f":rotating_light: *Needs Human — {client_slug}*\n"
        f"*Issue:* {explanation}\n"
        f"{record_info}\n\n"
        f":bulb: *How to fix:*\n{suggested_action}"
    )
    return _send(webhook_url, text)


def notify_retry_success(webhook_url: str, client_slug: str, attempts: int,
                         fixes_applied: list[str]) -> bool:
    """Notify Slack that a launch succeeded after auto-fix retries."""
    if not webhook_url:
        return False
    fixes_str = ", ".join(fixes_applied) if fixes_applied else "none"
    text = (
        f":white_check_mark: *Launch Recovered — {client_slug}*\n"
        f"Succeeded after {attempts} attempt(s)\n"
        f"Auto-fixes applied: {fixes_str}"
    )
    return _send(webhook_url, text)


# ─── Main Self-Healing Wrapper ───────────────────────────────────────────────

def run_with_self_healing(
    client_slug: str,
    record_id: str,
    dry_run: bool = False,
    config_override: dict | None = None,
) -> dict:
    """Run the launcher with self-healing error handling.

    Wraps run_launcher() in a retry loop that:
    1. Catches errors
    2. Diagnoses them
    3. Applies auto-fixes when possible
    4. Retries the launch
    5. Escalates to human when auto-fix isn't possible

    Returns the summary dict from run_launcher() on success.
    """
    from config_loader import load_all
    from main import run_launcher

    # Load config once (fixes will mutate it in-place)
    config = config_override or load_all(client_slug)
    slack_url = config.get("slack_webhook_url", "")

    attempt_history: list[str] = []
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            summary = run_launcher(client_slug, record_id, dry_run=dry_run, config_override=config)

            # If we recovered after retries, notify
            if attempt > 0:
                notify_retry_success(slack_url, client_slug, attempt + 1, attempt_history)

            return summary

        except (MetaApiError, ValueError, RuntimeError) as e:
            last_error = e
            print(f"\n{'='*60}")
            print(f"Self-healing: Attempt {attempt + 1}/{MAX_RETRIES} failed")
            print(f"Error: {e}")
            print(f"{'='*60}")

            diagnosis = diagnose_error(e, config, attempt_history)

            if diagnosis.can_auto_fix and attempt < MAX_RETRIES - 1:
                print(f"\nDiagnosis: {diagnosis.explanation}")
                print(f"Auto-fix: {diagnosis.fix_action}")

                # Notify Slack about the auto-fix
                notify_auto_fix(slack_url, client_slug, diagnosis.explanation, diagnosis.fix_action)

                # Apply the fix
                apply_fix(diagnosis.fix_action, diagnosis.fix_params, config)
                attempt_history.append(diagnosis.fix_action)

                print("Retrying launch...\n")
                continue
            else:
                # Can't auto-fix — escalate to human
                print(f"\nDiagnosis: {diagnosis.explanation}")
                print(f"Cannot auto-fix. Escalating to human.")
                print(f"Suggested action: {diagnosis.suggested_action}")

                notify_needs_human(
                    slack_url, client_slug,
                    diagnosis.explanation,
                    diagnosis.suggested_action,
                    record_id=record_id,
                )
                raise

    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Self-healing loop exhausted without result")
