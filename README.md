# FB Ads Launcher

Autonomous agent that reads Airtable Ad Set briefs and launches Facebook/Meta ads via the Marketing API. Triggered automatically when an Airtable Ad Set's status changes to **Ready to Launch**.

## Architecture

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

- Python scripts on **Modal** (serverless), triggered by Airtable webhooks
- No `facebook_business` SDK — raw `requests` against **Graph API v25.0**
- **14 client ad accounts**, each with a config in `clients/{slug}/fb_ads_config.json`
- All ads are created **PAUSED** — activation is a separate step

## Quick Start (Claude Code)

If you use [Claude Code](https://claude.com/claude-code), setup is a conversation:

```bash
git clone <this-repo>
cd FbAdsLauncher
claude            # open Claude Code here
```

Then in Claude Code, type:

```
/onboard
```

Claude will walk you through API keys (Meta + Airtable), a single-brand or agency fork, per-client config (auto-creating Airtable tables and auto-resolving the linked Instagram account where possible), and a live connection test. No README required.

If you're not using Claude Code, follow the manual setup below.

## Setup for Teammates

This is a public repo. **Secrets are not committed.** To run the project locally, you need credentials Luis will share via a secure channel (1Password / direct handoff).

### 1. Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

(The launcher hits Airtable and Meta Graph directly via `requests` — no `pyairtable` or `facebook_business` SDK.)

### 2. Environment variables

Copy `.env.example` → `.env` and fill in the real values (get from Luis):

```bash
cp .env.example .env
```

Required keys:

| Key | Purpose |
|:----|:--------|
| `FB_ACCESS_TOKEN` | Meta Marketing API system user token (Partner BM) |
| `AIRTABLE_API_KEY` | Airtable personal access token |
| `SLACK_WEBHOOK_URL` | Slack notifications channel |

### 3. Modal workspace

Production runs on Modal under the `rooster` workspace. Ask Luis to add you as a member — all secrets live in the Modal secret `fb-ads-launcher-env`, so you don't need to manage them yourself for deploys.

```bash
python3 -m pip install modal
modal token new                  # auth with your Modal account
modal app logs fb-ads-launcher   # tail production logs
```

### 4. Verify connectivity

```bash
python3 scripts/test_connection.py <client_slug>
```

## Usage

### Manual launch

```bash
# Dry run (no Meta API calls)
python3 scripts/main.py <client_slug> <airtable_record_id> --dry-run

# Live (creates everything PAUSED)
python3 scripts/main.py <client_slug> <airtable_record_id>
```

### Activate paused ads

```bash
python3 scripts/activate_ads.py <client_slug> <campaign_id>
```

### Deploy Modal webhook

```bash
python3 -m modal deploy scripts/modal_webhook.py
```

### Health check

```bash
curl https://rooster--fb-ads-launcher-health.modal.run
```

## Key Scripts

| Script | Purpose |
|:-------|:--------|
| `main.py` | Main orchestrator — reads Airtable, creates Meta objects |
| `modal_webhook.py` | Modal webhook + health endpoint (auto-trigger from Airtable) |
| `config_loader.py` | Loads credentials + `fb_ads_config.json` |
| `airtable_reader.py` | Reads Ad Set + Ads, downloads attachments, writes back IDs |
| `clickup_reader.py` | Alternative brief source — reads from ClickUp |
| `meta_api.py` | All Meta Marketing API operations + rate-limit monitoring |
| `targeting.py` | Targeting spec builders (broad, lookalike, interest) |
| `notifier.py` | Slack webhook notifications |
| `preflight.py` | 6 pre-flight checks (token, ad account, page, IG, pixel, Airtable) |
| `error_agent.py` | Self-healing retry wrapper (IG strip, rate-limit backoff, etc.) |
| `activate_ads.py` | Moves PAUSED objects to ACTIVE |
| `test_connection.py` | Verifies Meta + Airtable connectivity |
| `list_custom_audiences.py` | Lists available custom / lookalike audiences for a client |
| `drive_client.py` | Google Drive asset fetcher |
| `setup_airtable_base.py` | Provisions tables in a new client's Airtable base |
| `setup_webhook.py` | Registers / lists / deletes Airtable automation webhooks |
| `sync_bases.py` | Syncs template-base structure to all client bases |
| `sync_meta_names.py` | Syncs Meta object names back to Airtable dropdowns |

## Client Config

Each client has a `clients/{slug}/fb_ads_config.json`:

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

Client launch defaults (budget, audience, exclusions, copy strategy) live in `clients/{slug}/launch_preferences.yml`.

## Safety Rules

- All ads are created **PAUSED** — nothing spends money until explicitly activated.
- Activation is a separate, manual step (`activate_ads.py`).
- Use `--dry-run` to preview before creating.
- **NEVER delete any object** (campaign, ad set, ad, audience, creative) without explicit user approval — not even "cleanup" of things you just created. Ask first.
- If an object becomes orphaned as a side effect of another action, leave it and inform the user.

## Meta API Access Posture

- **System user token** (not personal) — lives in our **Partner Business Manager**
- **Partner access** to all 14 client ad accounts (we don't own them)
- **CAPI** enabled on every client
- Rate-limit monitoring is built into [scripts/meta_api.py](scripts/meta_api.py) — warns at 75% utilization before Meta throttles

This posture limits the blast radius of any token compromise to our Partner BM. Read more in Meta's [rate limiting docs](https://developers.facebook.com/docs/graph-api/overview/rate-limiting).

## Debugging Launches

You don't need to re-trigger from Airtable during debugging:

```bash
# Fix code
python3 -m modal deploy scripts/modal_webhook.py
python3 scripts/main.py <slug> <record_id>  # run directly
# repeat
```

## Project Notes

- **LESSONS.md** — running log of Meta API gotchas, API v25.0 quirks, PAC rules. Read before debugging.
- **CLAUDE.md** — instructions for the Claude agent that often drives this repo.
