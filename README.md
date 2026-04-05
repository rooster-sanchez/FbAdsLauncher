# FB Ads Launcher

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

## Quick Start

1. Clone the repo
2. Copy `.env.example` to `.env` and fill in your credentials
3. Copy `clients/_example/` to `clients/your_client/` and fill in your IDs
4. Install dependencies: `pip install -r requirements.txt`
5. Test connectivity: `python3 scripts/test_connection.py your_client`
6. Dry run: `python3 scripts/main.py your_client <airtable_record_id> --dry-run`

## Usage

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

## Client Config

Each client needs a `clients/{slug}/fb_ads_config.json` — see `clients/_example/` for the template.

### Required fields:
| Field | Description |
|:------|:------------|
| `airtable_base_id` | Your Airtable base ID |
| `airtable_ad_sets_table_id` | Ad Sets table ID |
| `airtable_ads_table_id` | Ads table ID |
| `fb_ad_account_id` | Meta ad account ID (e.g., `act_XXXXXXX`) |
| `fb_page_id` | Facebook Page ID |
| `instagram_user_id` | Instagram business account ID (optional) |
| `default_pixel_id` | Meta Pixel ID |

## Required Credentials

| Key | Description |
|:----|:------------|
| `FB_ACCESS_TOKEN` | Meta Marketing API access token |
| `AIRTABLE_API_KEY` | Airtable personal access token |
| `SLACK_WEBHOOK_URL` | Slack webhook for notifications |

## Deployment (Modal)

```bash
pip install modal
python3 -m modal deploy scripts/modal_webhook.py
```

## Scripts

| Script | Purpose |
|:-------|:--------|
| `main.py` | Main orchestrator — reads Airtable, creates Meta objects |
| `modal_webhook.py` | Modal webhook endpoint (auto-trigger) |
| `config_loader.py` | Loads credentials and client config |
| `airtable_reader.py` | Reads Ad Set + Ads, downloads attachments |
| `meta_api.py` | All Meta Marketing API operations |
| `targeting.py` | Builds targeting specs |
| `notifier.py` | Slack webhook notifications |
| `activate_ads.py` | Moves PAUSED objects to ACTIVE |
| `preflight.py` | Pre-flight validation checks |
| `error_agent.py` | Self-healing error handler |

## Safety

- All ads are created **PAUSED** — nothing spends money until explicitly activated
- Activation is a separate script (`activate_ads.py`)
- Use `--dry-run` to preview everything before creating
- Pre-flight checks validate all credentials before making any API calls
- Rollback on partial failure cleans up orphaned objects

## Meta API Version

Currently uses Meta Marketing API **v25.0**. See `LESSONS.md` for known gotchas.

## License

MIT
