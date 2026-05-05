"""
FB Ads Launcher — Modal Webhook Endpoint
========================================
Receives Airtable automation webhooks when an Ad Set status changes to
"Ready to Launch" and runs the launcher.

Each client's Airtable base has an automation that sends:
    {"record_id": "recXXX", "client_slug": "ts_twelve_south"}

Deploy (from repo root):
    modal deploy scripts/modal_webhook.py

Secret (create once):
    modal secret create fb-ads-launcher-env \\
        FB_ACCESS_TOKEN="..." \\
        AIRTABLE_API_KEY="..." \\
        SLACK_WEBHOOK_URL="..."

This file is a thin deploy wrapper: it builds the Modal image, mounts
scripts/ + clients/, wires the secret, and exposes POST /webhook (plus a
GET /health helper). Launcher logic lives in the rest of scripts/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import modal

# ─── Paths ────────────────────────────────────────────────────────────────────

# scripts/modal_webhook.py → repo root is parents[1]
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
CLIENTS_DIR = REPO_ROOT / "clients"


def _build_clients_mount() -> Path:
    """Stage only launcher-relevant client files under /tmp and return the path.

    Only ships clients that have a launcher config (fb_ads_config.json).
    Skips _example and any client without launcher setup.

    Runs only during local `modal deploy`. On the Modal runtime container,
    CLIENTS_DIR does not exist and we return a placeholder.
    """
    import shutil

    stage = Path("/tmp/fb_ads_launcher_mount/clients")

    # Skip during remote execution — the container has no local source tree
    if not CLIENTS_DIR.exists():
        return stage

    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    for client_dir in sorted(CLIENTS_DIR.iterdir()):
        if not client_dir.is_dir() or client_dir.name.startswith("_"):
            continue

        # Only stage clients that have a launcher config
        cfg_src = client_dir / "fb_ads_config.json"
        if not cfg_src.exists():
            continue

        prefs_src = client_dir / "launch_preferences.yml"
        creds_src = client_dir / "credentials"

        dst = stage / client_dir.name
        dst.mkdir(parents=True)
        shutil.copy2(cfg_src, dst / "fb_ads_config.json")
        if prefs_src.exists():
            shutil.copy2(prefs_src, dst / "launch_preferences.yml")
        if creds_src.exists():
            shutil.copytree(creds_src, dst / "credentials", dirs_exist_ok=True)

    return stage


CLIENTS_MOUNT = _build_clients_mount()


# ─── Modal App & Image ────────────────────────────────────────────────────────

app = modal.App("fb-ads-launcher")

LAUNCHER_VERSION = "2026-05-05-fbal"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("requests", "python-dotenv", "fastapi", "pyyaml")
    .env({"LAUNCHER_VERSION": LAUNCHER_VERSION})
    .add_local_dir(str(SCRIPTS_DIR), remote_path="/app/scripts")
    .add_local_dir(str(CLIENTS_MOUNT), remote_path="/app/clients")
)

secrets = [modal.Secret.from_name("fb-ads-launcher-env")]


def _init_runtime() -> None:
    """Wire the Modal mount into the launcher scripts."""
    if "/app/scripts" not in sys.path:
        sys.path.insert(0, "/app/scripts")
    # config_loader honours FB_ADS_CLIENTS_DIR — point it at the mount
    os.environ.setdefault("FB_ADS_CLIENTS_DIR", "/app/clients")


# ─── Webhook Endpoint ─────────────────────────────────────────────────────────

@app.function(image=image, secrets=secrets, timeout=600)
@modal.fastapi_endpoint(method="POST")
def webhook(body: dict):
    """POST /webhook — Airtable automation entrypoint.

    Expected payload:
        {"record_id": "recXXXXXX", "client_slug": "ts_twelve_south"}
    """

    record_id = body.get("record_id", "")
    client_slug = body.get("client_slug", "")

    print(
        f"Webhook received: record_id={record_id}, client_slug={client_slug} "
        f"[version={LAUNCHER_VERSION}]"
    )

    if not record_id:
        return {"status": "error", "reason": "no record_id in payload"}
    if not client_slug:
        return {"status": "error", "reason": "no client_slug in payload"}

    _init_runtime()

    try:
        from error_agent import run_with_self_healing

        summary = run_with_self_healing(client_slug, record_id, dry_run=False)

        return {
            "status": "success",
            "client": client_slug,
            "campaign_id": summary.get("campaign_id"),
            "ads_created": len(summary.get("ad_results", [])),
        }

    except Exception as exc:
        import traceback

        traceback.print_exc()
        print(f"ERROR (after self-healing attempts): {exc}")

        slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")
        if slack_url:
            try:
                from notifier import notify_launch_error

                notify_launch_error(
                    slack_url,
                    client_slug=client_slug,
                    error=f"[v{LAUNCHER_VERSION}] {exc}",
                    record_id=record_id,
                )
            except Exception:
                print("Warning: Slack error notification failed")

        return {"status": "error", "reason": str(exc)}


# ─── Health Check Endpoint ────────────────────────────────────────────────────

@app.function(image=image, secrets=secrets, timeout=120)
@modal.fastapi_endpoint(method="GET")
def health(client_slug: str = ""):
    """GET /health[?client_slug=...] — run pre-flight checks."""

    _init_runtime()

    from config_loader import load_all, validate_config
    from preflight import resolve_instagram, run_preflight

    clients_dir = Path(os.environ.get("FB_ADS_CLIENTS_DIR", "/app/clients"))

    if client_slug:
        slugs = [client_slug]
    else:
        slugs = sorted(
            [
                d.name
                for d in clients_dir.iterdir()
                if d.is_dir()
                and not d.name.startswith("_")
                and (d / "fb_ads_config.json").exists()
            ]
        )

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
        except Exception as exc:
            results[slug] = {"status": "error", "errors": [str(exc)]}

    healthy = sum(1 for r in results.values() if r["status"] == "healthy")
    total = len(results)

    return {
        "summary": f"{healthy}/{total} clients healthy",
        "version": LAUNCHER_VERSION,
        "clients": results,
    }


# ─── Local Entrypoint (for testing) ───────────────────────────────────────────

@app.local_entrypoint()
def main():
    """modal run scripts/modal_webhook.py"""
    print("Webhook endpoint deployed. URL will be shown in Modal dashboard.")
    print("Test: curl -X POST <url> -H 'Content-Type: application/json' -d '{...}'")
