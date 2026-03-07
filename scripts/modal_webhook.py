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

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("requests", "python-dotenv", "fastapi")
    .add_local_dir(
        "/Users/luisfersang/Documents/Antigravity/agents/fb-ads-launcher/scripts",
        remote_path="/app/scripts",
    )
    .add_local_dir(
        "/Users/luisfersang/Documents/Antigravity/clients",
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

    print(f"Webhook received: record_id={record_id}, client_slug={client_slug}")

    if not record_id:
        return {"status": "error", "reason": "no record_id in payload"}

    if not client_slug:
        return {"status": "error", "reason": "no client_slug in payload"}

    # Set up paths for the scripts
    sys.path.insert(0, "/app/scripts")

    # Patch config_loader to look at /app/clients instead of local workspace
    os.environ.setdefault("FB_ADS_CLIENTS_DIR", "/app/clients")

    try:
        from main import run_launcher
        summary = run_launcher(client_slug, record_id, dry_run=False)

        return {
            "status": "success",
            "client": client_slug,
            "campaign_id": summary.get("campaign_id"),
            "ads_created": len(summary.get("ad_results", [])),
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR: {e}")
        return {"status": "error", "reason": str(e)}


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
