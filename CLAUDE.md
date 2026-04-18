# FB Ads Launcher

## First-Run Onboarding

Before responding to the first user request in a session, check:
1. Does `.env` exist at repo root (not just `.env.example`)?
2. Does any `clients/*/fb_ads_config.json` (excluding `_example`) have a real `airtable_base_id` (i.e. not `appXXXXXXXXXX`)?

If EITHER is false, surface this offer once, then wait:

> Looks like you haven't finished setup. I can walk you through it — API keys, client config, and a live connection test. Want to start now? Otherwise run `/onboard` anytime.

Do NOT auto-run `/onboard` — writing `.env` requires explicit consent. If the user asks an unrelated question, answer it first and surface the offer once at the end of that response. Do not re-surface in later turns unless the user asks.

## Self-Healing Rules

Every time we fix a bug, resolve an error, or discover a non-obvious behavior:
1. Read `LESSONS.md` first to check for existing lessons
2. Add the new lesson to `LESSONS.md` (format: what went wrong → what to do instead)
3. If a lesson exists but was insufficient, strengthen it

---

Autonomous agent that reads Airtable Ad Set briefs and launches Facebook/Meta ads via the Marketing API. Triggered automatically when an Airtable Ad Set status changes to "Ready to Launch".

## How It Works

```
Airtable Ad Set status → "Ready to Launch"
    ↓
Airtable automation fires POST to Modal endpoint
    (payload: record_id + client_slug)
    ↓
Modal loads client config, reads Ad Set + linked Ads from Airtable
    ↓
Creates campaign, ad sets, ads (PAUSED) in Meta Ads Manager
    ↓
Writes Meta IDs back to Airtable + Slack notification
```

## Manual Usage

```bash
# Dry run (no Meta API calls)
python3 scripts/main.py <client_slug> <airtable_record_id> --dry-run

# Live run (creates everything PAUSED)
python3 scripts/main.py <client_slug> <airtable_record_id>

# Test connections
python3 scripts/test_connection.py <client_slug>

# Activate ads (go live)
python3 scripts/activate_ads.py <client_slug> <campaign_id>
```

## Scripts

| Script | Purpose |
|:-------|:--------|
| `main.py` | Main orchestrator — reads Airtable, creates Meta objects |
| `modal_webhook.py` | Modal webhook endpoint (auto-trigger) |
| `config_loader.py` | Loads credentials and fb_ads_config.json |
| `airtable_reader.py` | Reads Ad Set + Ads, downloads attachments, writes back IDs |
| `meta_api.py` | All Meta Marketing API operations |
| `targeting.py` | Builds targeting specs (broad, lookalike, interest) |
| `notifier.py` | Slack webhook notifications |
| `activate_ads.py` | Moves PAUSED objects to ACTIVE |
| `test_connection.py` | Verifies Meta + Airtable connectivity |
| `list_custom_audiences.py` | Lists available custom/lookalike audiences |
| `sync_bases.py` | Syncs template base structure to all client bases |
| `setup_airtable_base.py` | Creates tables in a new client base |
| `sync_meta_names.py` | Syncs Meta naming back to Airtable |

## Client Config

Each client needs a `clients/{slug}/fb_ads_config.json`:

```json
{
  "airtable_base_id": "appXXXXXXXXXX",
  "airtable_ad_sets_table_id": "tblXXXXXXXXXX",
  "airtable_ads_table_id": "tblXXXXXXXXXX",
  "fb_ad_account_id": "act_XXXXXXX",
  "fb_page_id": "XXXXXXX",
  "instagram_user_id": "XXXXXXX",
  "default_pixel_id": "XXXXXXX",
  "default_optimization_goal": "OFFSITE_CONVERSIONS",
  "default_billing_event": "IMPRESSIONS",
  "default_geo_locations": { "countries": ["US"] },
  "naming_convention": { ... },
  "utm_defaults": { ... }
}
```

## Required Credentials

| Key | Location | Description |
|:----|:---------|:------------|
| `FB_ACCESS_TOKEN` | `.env` + Modal secret | Meta API access token |
| `AIRTABLE_API_KEY` | `.env` + Modal secret | Airtable personal access token |
| `SLACK_WEBHOOK_URL` | `.env` + Modal secret | Slack notifications |

Modal secret name: `fb-ads-launcher-env`

## Deployment

```bash
python3 -m modal deploy scripts/modal_webhook.py
modal app logs fb-ads-launcher
```

## Syncing Base Structure

The template base (`applXM4Udl33lKIst`) is the source of truth. When you change fields in the template:

```bash
python3 scripts/sync_bases.py          # Preview
python3 scripts/sync_bases.py --apply  # Apply to all client bases
```

## Safety

- All ads are created **PAUSED** — nothing spends money until explicitly activated
- Activation is a separate script (`activate_ads.py`)
- Use `--dry-run` to preview everything before creating
- **NEVER delete ANYTHING without explicit user approval. This includes campaigns, ad sets, ads, audiences, creatives, custom audiences, pixels, pages, or any other object on any ad account, Airtable base, or external system. No exceptions — not even "cleanup" of objects you just created. Always ask first.**
- This applies regardless of permission mode, including Bypass mode.
- If an object becomes orphaned or empty as a side effect of another action (e.g., moving ad sets out of a campaign), leave it alone and inform the user. Let them decide whether to delete it.

## Debugging Launches

When the user asks to debug/fix a launch error, you can trigger launches manually instead of requiring them to click "Ready to Launch" in Airtable:

```bash
# Run the launch directly (same as what Modal webhook does)
python3 scripts/main.py <client_slug> <record_id>

# With dry run first to inspect payload
python3 scripts/main.py <client_slug> <record_id> --dry-run
```

**Workflow for iterative debugging:**
1. Fix the code
2. Deploy: `python3 -m modal deploy scripts/modal_webhook.py`
3. Run locally: `python3 scripts/main.py <slug> <record_id>`
4. If it fails, fix and repeat from step 1
5. No need for the user to re-trigger from Airtable each time

## Meta Marketing API (v25.0) Gotchas

See `LESSONS.md` for the full list — kept external to avoid bloating this file.
