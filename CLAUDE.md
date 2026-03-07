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
- NEVER delete existing campaigns/ad sets/ads without explicit user approval

## Meta Marketing API (v21.0) Gotchas

- Campaign creation requires `is_adset_budget_sharing_enabled: false` for ABO campaigns
- Ad set creation requires `bid_strategy: LOWEST_COST_WITHOUT_CAP` and `targeting_automation: {advantage_audience: 0}` in targeting spec
- Video ad creatives require a thumbnail (`image_url` in `video_data`) — fetch via `GET /{video_id}/thumbnails`
- Use `instagram_user_id` (not `instagram_actor_id`) in `object_story_spec` — get the correct ID from `GET /{page_id}?fields=instagram_business_account`
- `special_ad_categories` must be sent as string `"[]"` not empty array
