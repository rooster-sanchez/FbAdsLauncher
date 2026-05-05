# FB Ads Launcher — Roadmap

Last updated: 2026-05-05

---

## Phase 1: Reliability Hardening [SHIPPED]

**Goal**: Make the launcher work 99% of the time across all client accounts.

### Completed

- [x] **Pre-flight validation** — 6 connectivity checks (token, ad account, page, Instagram, pixel, Airtable) run before any Meta objects are created. Catches bad configs upfront instead of failing mid-launch. → `scripts/preflight.py`
- [x] **Instagram resolution at startup** — Auto-resolves Instagram user ID from the Facebook Page before launch, not at creative-creation time. Prevents orphaned campaign/ad set objects when IG fails. → `scripts/preflight.py:resolve_instagram()`
- [x] **Rollback on partial failure** — When a launch fails mid-way, automatically deletes only **newly created** objects in reverse order (ads → ad sets → campaigns). Existing campaigns/ad sets are never touched, even if the launch was scoped to them — they carry historical spend. → `scripts/meta_api.py:delete_object()` + `scripts/main.py`
- [x] **Idempotency guard** — Detects already-launched records and skips them. Prevents duplicates when Airtable automation fires twice. → `scripts/main.py` + `scripts/airtable_reader.py`
- [x] **Health check endpoint** — `GET /health` on Modal checks all configured clients' connectivity and reports status. → `scripts/modal_webhook.py:health()`
- [x] **Self-healing error handler** — Wraps the launcher in an intelligent retry loop. Auto-fixes: broken Instagram (strips IG, retries FB-only), rate limits (backoff), transient 500s (retry), targeting too narrow (broaden), duplicate names (append suffix), large-video uploads (chunked protocol). Escalates unfixable errors with clear human instructions. → `scripts/error_agent.py`
- [x] **Expanded config validation** — Checks table IDs, warns on missing Instagram/pixel when optimization goal is CONVERSIONS. → `scripts/config_loader.py`
- [x] **Refactored `test_connection.py`** — Uses shared preflight module, also checks Instagram and pixel. → `scripts/test_connection.py`
- [x] **API v25.0 migration** — Migrated from v22.0 → v25.0 (Mar 2026) for PAC support and current Meta best-practices. Includes fixes for PAC creative limits (subcodes 1885374/1885878), `is_dynamic_creative` immutability, the 10-asset cap, and the deprecated `standard_enhancements` wrapper. See `LESSONS.md` for the full list.
- [x] **Instagram ID fixes** — Resolved deprecated IG user IDs (legacy endpoint error 36106). PP / RD / FM now use `@fatherscollective` (`17841411587000289`). FE uses `17841469065114612`.

### Current State

| Metric | Value |
|--------|-------|
| Active client configs | 14 |
| Self-healing coverage | IG auth, rate limits, transient errors, duplicates, targeting, video processing, chunked uploads |
| API version | v25.0 |
| Deployed | Modal webhook + health endpoint (`fb-ads-launcher` app) |

### Watchlist

- v25.0 deprecations to monitor: `degrees_of_freedom_spec.creative_features_spec.standard_enhancements` is already gone — Meta is moving toward per-feature enrollment. Keep checking the changelog at each version bump.
- `modal app logs` streams indefinitely — no easy way to pull historical logs. Lift-and-shift to a structured launch-log table is still on the table if it becomes painful (see Phase 2 below).

---

## Phase 2: Operational Polish [ACTIVE]

**Goal**: Quality-of-life improvements — no major architecture changes.

The previous Phase 2 ("Web UI: Replace Airtable with a Next.js + Supabase app") was **scrapped on 2026-03-31**. Airtable + this Python launcher remained the better tool for the job; the abandoned `web/` and `supabase/` directories are excluded via `.gitignore`. The team now drives the launcher via Airtable + Claude Code (`/onboard` for first-time setup, conversational launches for everything else).

### Candidates

- [ ] **Structured launch-logs table** — Persist every launch attempt (success, partial, failed) to an Airtable `Launch Logs` table or a lightweight Supabase row. Replaces the current "tail Modal logs" workflow.
- [ ] **Per-client rate-limit dashboard** — Surface the 75% / 90% utilization warnings already emitted by `meta_api.py` somewhere visible (Slack daily digest or simple status page).
- [ ] **Onboarding CLI polish** — `/onboard` already covers first-time setup; add `/onboard --client {slug}` for adding a new client to an existing install without re-doing API keys.
- [ ] **CAPI deduplication audit script** — Sanity-check that pixel events are correctly deduped against Meta's matched-events report.

---

## Phase 3: Natural-Language Launching [FUTURE]

**Goal**: "Upload these to 12 South with $50/day broad women 25-45 in the Flex campaign" — Claude parses the intent, prefills a brief, the operator confirms, the launcher runs.

This is now possible directly inside Claude Code without a custom UI: drop creatives into the conversation, describe the launch, Claude assembles the Airtable record (or calls `main.py` directly) and the existing pipeline takes over. Tracked here as a usage pattern rather than a code deliverable.

---

## File Reference

### Scripts (Python)

| File | Purpose |
|------|---------|
| `main.py` | Main orchestrator — reads brief, creates Meta objects |
| `modal_webhook.py` | Modal webhook + health endpoint |
| `error_agent.py` | Self-healing retry wrapper |
| `preflight.py` | Pre-flight validation + Instagram resolution |
| `config_loader.py` | Loads credentials + client config |
| `airtable_reader.py` | Reads Ad Set + Ads from Airtable |
| `clickup_reader.py` | Alternative brief source — reads from ClickUp |
| `meta_api.py` | All Meta Marketing API operations + rate-limit monitoring |
| `targeting.py` | Builds targeting specs |
| `notifier.py` | Slack notifications |
| `test_connection.py` | CLI pre-flight checks |
| `activate_ads.py` | Moves PAUSED → ACTIVE |
| `list_custom_audiences.py` | Lists available custom / lookalike audiences |
| `drive_client.py` | Google Drive asset fetcher |
| `setup_airtable_base.py` | Provisions tables in a new client's Airtable base |
| `setup_webhook.py` | Registers / lists / deletes Airtable automation webhooks |
| `sync_bases.py` | Syncs template-base structure to all client bases |
| `sync_meta_names.py` | Syncs Meta object names back to Airtable dropdowns |

### Endpoints

| Endpoint | Method | URL |
|----------|--------|-----|
| Webhook | POST | `https://rooster--fb-ads-launcher-webhook.modal.run` |
| Health | GET | `https://rooster--fb-ads-launcher-health.modal.run` |
