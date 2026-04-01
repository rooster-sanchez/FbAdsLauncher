"""
FB Ads Launcher — Modal Webhook Endpoint
=========================================
Receives Airtable automation webhooks when an Ad Set status changes to
"Ready to Launch" and automatically runs the FB Ads Launcher.

Each client's Airtable base has an automation that sends:
    {"record_id": "recXXX", "client_slug": "ts_twelve_south"}

Deploy:
    modal deploy agents/fb-ads-launcher/scripts/modal_webhook.py

Test (one-off):
    modal run agents/fb-ads-launcher/scripts/modal_webhook.py

Secrets to create first (see bottom of file for exact commands):
    modal secret create fb-ads-launcher-env \
        FB_ACCESS_TOKEN="..." \
        AIRTABLE_API_KEY="..." \
        SLACK_WEBHOOK_URL="..."
"""

from __future__ import annotations

import os
import sys

import modal

# ─── Modal App & Image ───────────────────────────────────────────────────────

app = modal.App("fb-ads-launcher")

LAUNCHER_VERSION = "2026-03-13-v8"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("requests", "python-dotenv", "fastapi")
    .env({"LAUNCHER_VERSION": LAUNCHER_VERSION})
    .add_local_dir(
        "/Users/luisfersang/Documents/Rooster's AI Projects/FbAdsLauncher/scripts",
        remote_path="/app/scripts",
    )
    .add_local_dir(
        "/Users/luisfersang/Documents/Rooster's AI Projects/FbAdsLauncher/clients",
        remote_path="/app/clients",
    )
)

secrets = [modal.Secret.from_name("fb-ads-launcher-env")]


# ─── Webhook Endpoint ────────────────────────────────────────────────────────

@app.function(image=image, secrets=secrets, timeout=600)
@modal.fastapi_endpoint(method="POST")
def webhook(body: dict):
    """Receive Airtable automation webhook when Ad Set status = 'Ready to Launch'.

    Expected payload from Airtable automation:
        {"record_id": "recXXXXXX", "client_slug": "ts_twelve_south"}
    """

    record_id = body.get("record_id", "")
    client_slug = body.get("client_slug", "")

    print(f"Webhook received: record_id={record_id}, client_slug={client_slug} [version={LAUNCHER_VERSION}]")

    if not record_id:
        return {"status": "error", "reason": "no record_id in payload"}

    if not client_slug:
        return {"status": "error", "reason": "no client_slug in payload"}

    # Set up paths for the scripts
    sys.path.insert(0, "/app/scripts")

    # Patch config_loader to look at /app/clients instead of local workspace
    os.environ.setdefault("FB_ADS_CLIENTS_DIR", "/app/clients")

    try:
        from error_agent import run_with_self_healing
        summary = run_with_self_healing(client_slug, record_id, dry_run=False)

        return {
            "status": "success",
            "client": client_slug,
            "campaign_id": summary.get("campaign_id"),
            "ads_created": len(summary.get("ad_results", [])),
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR (after self-healing attempts): {e}")

        # error_agent already sends detailed Slack notifications,
        # but send a final fallback notification just in case
        slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")
        if slack_url:
            try:
                from notifier import notify_launch_error
                notify_launch_error(
                    slack_url,
                    client_slug=client_slug,
                    error=f"[v{LAUNCHER_VERSION}] {e}",
                    record_id=record_id,
                )
            except Exception:
                print("Warning: Slack error notification failed")

        return {"status": "error", "reason": str(e)}


# ─── Health Check Endpoint ───────────────────────────────────────────────────

@app.function(image=image, secrets=secrets, timeout=120)
@modal.fastapi_endpoint(method="GET")
def health(client_slug: str = ""):
    """Run pre-flight checks for one or all clients.

    GET /health              → check all clients
    GET /health?client_slug=ts_twelve_south → check one client
    """
    sys.path.insert(0, "/app/scripts")
    os.environ.setdefault("FB_ADS_CLIENTS_DIR", "/app/clients")

    from config_loader import load_all, validate_config
    from preflight import resolve_instagram, run_preflight

    from pathlib import Path
    clients_dir = Path(os.environ.get("FB_ADS_CLIENTS_DIR", "/app/clients"))

    # Determine which clients to check
    if client_slug:
        slugs = [client_slug]
    else:
        slugs = sorted([
            d.name for d in clients_dir.iterdir()
            if d.is_dir() and not d.name.startswith("_") and (d / "fb_ads_config.json").exists()
        ])

    results = {}
    for slug in slugs:
        try:
            config = load_all(slug)
            config_errors = validate_config(config)
            if config_errors:
                results[slug] = {"status": "config_error", "errors": config_errors}
                continue

            resolve_instagram(config)
            preflight_errors = run_preflight(config)
            if preflight_errors:
                results[slug] = {"status": "unhealthy", "errors": preflight_errors}
            else:
                results[slug] = {"status": "healthy"}
        except Exception as e:
            results[slug] = {"status": "error", "errors": [str(e)]}

    healthy = sum(1 for r in results.values() if r["status"] == "healthy")
    total = len(results)

    return {
        "summary": f"{healthy}/{total} clients healthy",
        "version": LAUNCHER_VERSION,
        "clients": results,
    }


# ─── Local Entrypoint (for testing) ──────────────────────────────────────────

@app.local_entrypoint()
def main():
    """Test the webhook endpoint locally: modal run agents/fb-ads-launcher/scripts/modal_webhook.py"""
    print("Webhook endpoint deployed. URL will be shown in Modal dashboard.")
    print("To test, use: curl -X POST <url> -H 'Content-Type: application/json' -d '{...}'")


# ─── Secret setup (run these once before deploying) ──────────────────────────
#
# modal secret create fb-ads-launcher-env \
#     FB_ACCESS_TOKEN="EAAakoZAaaKCABQ..." \
#     AIRTABLE_API_KEY="patXXXXX..." \
#     SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
#
# If secrets already exist and need updating:
#     modal secret create fb-ads-launcher-env --force \
#         FB_ACCESS_TOKEN="..." AIRTABLE_API_KEY="..." SLACK_WEBHOOK_URL="..."
#
# Note: Airtable base/table IDs are per-client in fb_ads_config.json,
# not in Modal secrets. They're loaded from the /app/clients mount.
#
# ─── Deploy ──────────────────────────────────────────────────────────────────
#
#     modal deploy agents/fb-ads-launcher/scripts/modal_webhook.py
#
# After deploying, the webhook URL will be:
#     https://<your-modal-username>--fb-ads-launcher-webhook.modal.run
#
# Configure each client's Airtable base automation to POST to this URL with:
#     {"record_id": "{{record_id}}", "client_slug": "<client_slug>"}
#
