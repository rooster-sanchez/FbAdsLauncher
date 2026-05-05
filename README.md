# FB Ads Launcher

A safety-first Meta ads launcher. One Python codebase, 14 client accounts, every campaign shipped **PAUSED** — and it recovers from the six most common Meta API failures on its own.

No `facebook_business` SDK. Raw `requests`, Graph API **v25.0**, deployed serverless on Modal.

---

## What it does

Hand it a structured ad brief. It will:

1. **Pre-flight** the brief — six connectivity checks (token, ad account, page, Instagram, pixel, brief source). Bad configs fail fast, before any Meta object exists.
2. **Resolve** the Instagram account from the Facebook Page so a misconfigured IG never leaves you with an orphan campaign.
3. **Create** the campaign, ad sets, and ads — all PAUSED — and write the Meta IDs back to the brief.
4. **Self-heal** the usual failures: deprecated IG IDs, rate limits, transient 500s, narrow targeting, duplicate names, and large videos (chunked uploads kick in at 50 MB).
5. **Ping** Slack with the result and the next step.

Activation is always an explicit second step (`activate_ads.py`). Nothing spends money until you say so.

## How a launch flows

```
  Brief                Launcher                    Meta
  ─────                ────────                    ────
  Airtable record   ┐                            ┌─ Campaign  (PAUSED)
  ClickUp task      ├─►  preflight              ├─ Ad sets   (PAUSED)
  CLI invocation    ┘    │                       └─ Ads       (PAUSED)
                         ▼
                      self-heal ◄──── Meta API ◄─┘
                         │             (v25.0)
                         ▼
                    write IDs back
                    + Slack ping
```

Most clients drive launches from Airtable (status → "Ready to Launch" fires a Modal webhook). ClickUp and direct CLI invocation use the same launcher; only the brief reader changes.

## Quick start (Claude Code)

If you have [Claude Code](https://claude.com/claude-code), setup is a single command:

```bash
git clone https://github.com/rooster-sanchez/FbAdsLauncher.git
cd FbAdsLauncher
claude
```

Then in Claude:

```
/onboard
```

`/onboard` walks you through API keys, single-brand or agency setup, per-client config (auto-creating Airtable tables and resolving the linked Instagram account), and a live connection test. No README required after that point.

## Quick start (manual)

```bash
# 1. Install
python3 -m pip install -r requirements.txt

# 2. Configure secrets — get values from Luis
cp .env.example .env

# 3. Verify connectivity for a client
python3 scripts/test_connection.py <client_slug>

# 4. Dry-run a launch (no Meta API writes)
python3 scripts/main.py <client_slug> <brief_id> --dry-run

# 5. Live launch (everything created PAUSED)
python3 scripts/main.py <client_slug> <brief_id>

# 6. Activate when ready
python3 scripts/activate_ads.py <client_slug> <campaign_id>
```

### Required environment

| Key | Purpose |
|:----|:--------|
| `FB_ACCESS_TOKEN` | System user token from the Partner Business Manager |
| `AIRTABLE_API_KEY` | Personal access token for the brief base(s) |
| `SLACK_WEBHOOK_URL` | Channel for launch + error notifications |

Production secrets live in the Modal secret `fb-ads-launcher-env`. Ask Luis to add you to the `rooster` workspace if you need to deploy.

## The interesting bits

**Self-healing error agent** — `scripts/error_agent.py` wraps the launcher in a retry loop that auto-fixes broken Instagram accounts (strip IG, retry FB-only), rate limits (backoff), transient 500s (retry), too-narrow targeting (broaden), duplicate ad names (suffix), and large-video uploads (chunked protocol). Unfixable errors escalate with a human-readable next step.

**Rollback that doesn't bite you** — When a launch fails partway through, only **newly created** objects are deleted, in reverse order. Existing campaigns are never touched, even if the launch was scoped to them. They carry historical spend that no script gets to delete.

**Pre-flight, not post-mortem** — Six checks run *before* a single Meta object is created. The launcher refuses to start if the token, ad account, page, Instagram, pixel, or brief source isn't reachable. No more orphaned campaigns from a misconfigured IG.

**v25.0-aware** — Built around the current Meta API quirks: PAC creative limits (one ad_format per creative, one asset per label), `is_dynamic_creative` immutability, the 10-asset cap, and the deprecated `standard_enhancements` wrapper. Full list in [LESSONS.md](LESSONS.md).

**Rate-limit watchdog** — `meta_api.py` reads Meta's `X-Business-Use-Case-Usage` header on every call and warns at 75% utilization. You'll see throttling coming before it lands.

**Chunked video uploads at 50 MB** — Single-shot uploads above that threshold silently 413 on Meta's CDN. The launcher switches to `upload_phase=start/transfer/finish` automatically.

## Anatomy

| Script | Purpose |
|:-------|:--------|
| `main.py` | Orchestrator — reads brief, runs preflight, creates Meta objects, writes IDs back |
| `modal_webhook.py` | Modal webhook + health endpoint (auto-trigger from Airtable) |
| `config_loader.py` | Loads credentials + `fb_ads_config.json` |
| `airtable_reader.py` | Reads Ad Set + Ads, downloads attachments, writes back IDs |
| `clickup_reader.py` | Alternative brief source — reads from ClickUp |
| `meta_api.py` | All Meta Marketing API operations + rate-limit monitoring |
| `targeting.py` | Targeting spec builders (broad, lookalike, interest) |
| `notifier.py` | Slack webhook notifications |
| `preflight.py` | Six pre-flight checks + Instagram resolution |
| `error_agent.py` | Self-healing retry wrapper |
| `activate_ads.py` | Moves PAUSED objects to ACTIVE |
| `test_connection.py` | CLI pre-flight checks for a single client |
| `list_custom_audiences.py` | Lists custom / lookalike audiences for a client |
| `drive_client.py` | Google Drive asset fetcher |
| `setup_airtable_base.py` | Provisions tables in a new client's Airtable base |
| `setup_webhook.py` | Registers / lists / deletes Airtable automation webhooks |
| `sync_bases.py` | Syncs template-base schema to all client bases |
| `sync_meta_names.py` | Syncs Meta object names back to dropdowns |

## Client config

A client lives at `clients/{slug}/`:

```
clients/ts_twelve_south/
├── fb_ads_config.json          # account IDs, naming, UTM defaults
└── launch_preferences.yml      # budget, audience, exclusions, copy strategy
```

`fb_ads_config.json`:

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

`launch_preferences.yml` is optional but recommended — it holds default budget, audience type, exclusions (Klaviyo lists, 180-day purchasers, customer-list lookalikes), product list, and ad-copy strategy. Without it, every launch needs every parameter spelled out in the brief.

See [`clients/_example/`](clients/_example/) for a fully commented template.

## Safety contract

- **PAUSED is non-negotiable.** Every campaign, ad set, and ad ships paused. Activation is a separate explicit step.
- **Dry-run before live.** `--dry-run` prints the full Meta payload without writing.
- **Never delete without approval.** No script deletes anything — campaign, ad set, ad, audience, creative, custom audience — without an explicit human go. Not even "cleanup" of things just created. Applies in every permission mode.
- **Rollback respects history.** Failed launches only roll back the *new* objects they created. Existing campaigns with spend history are untouchable.
- **Soft-delete > delete.** Meta deletion is permanent (`status=DELETED` is irreversible). When soft-delete is wanted, the launcher uses `status=ARCHIVED`.

## Deploying the webhook

```bash
modal deploy scripts/modal_webhook.py     # ship it
modal app logs fb-ads-launcher            # tail logs
```

The webhook URL after deploy is `https://<modal-user>--fb-ads-launcher-webhook.modal.run`. Each client's Airtable automation POSTs `{"record_id": "...", "client_slug": "..."}` to it.

Health check (no auth):

```bash
curl https://rooster--fb-ads-launcher-health.modal.run
```

## Debugging launches

You never need to re-trigger from Airtable during a debug loop:

```bash
# 1. Fix code
# 2. Redeploy (only if the Modal image changed)
modal deploy scripts/modal_webhook.py
# 3. Re-run the same brief locally
python3 scripts/main.py <slug> <record_id>
# 4. Repeat
```

The local CLI hits the same code path as the webhook and produces the same Meta state.

## Meta API posture

- **System user token** in our Partner Business Manager, not a personal token.
- **Partner access** to all client ad accounts — we don't own them, the client does.
- **CAPI enabled** on every client.
- **Rate-limit monitoring** built into `meta_api.py`. 75% utilization triggers a warning; 90% backs off.

This posture limits the blast radius of a token compromise to our Partner BM. Background: Meta's [rate-limiting docs](https://developers.facebook.com/docs/graph-api/overview/rate-limiting).

## Project files

- [`LESSONS.md`](LESSONS.md) — running log of Meta API gotchas, v25.0 quirks, PAC rules. Read this before debugging anything weird.
- [`CLAUDE.md`](CLAUDE.md) — instructions for Claude Code when it drives the repo (most operators do).
- [`ROADMAP.md`](ROADMAP.md) — what shipped, what's next, what got scrapped.
