# FB Ads Launcher — Roadmap

Last updated: 2026-03-23

---

## Phase 1: Reliability Hardening [SHIPPED]

**Goal**: Make the launcher work 99% of the time across all accounts.

### Completed (2026-03-23)

- [x] **Pre-flight validation** — 6 connectivity checks (token, ad account, page, Instagram, pixel, Airtable) run before any Meta objects are created. Catches bad configs upfront instead of failing mid-launch. → `scripts/preflight.py`
- [x] **Instagram resolution at startup** — Auto-resolves Instagram user ID from the Facebook Page before launch, not at creative-creation time. Prevents orphaned campaign/ad set objects when IG fails. → `scripts/preflight.py:resolve_instagram()`
- [x] **Rollback on partial failure** — When a launch fails mid-way, automatically deletes created objects in reverse order (ads → ad sets → campaigns). No more orphaned Meta objects. → `scripts/meta_api.py:delete_object()` + `scripts/main.py`
- [x] **Idempotency guard** — Detects already-launched records and skips them. Prevents duplicates when Airtable automation fires twice. → `scripts/main.py` + `scripts/airtable_reader.py`
- [x] **Health check endpoint** — `GET /health` on Modal checks all 14 clients' connectivity and reports status. → `scripts/modal_webhook.py:health()`
- [x] **Self-healing error handler** — Wraps the launcher in an intelligent retry loop. Auto-fixes: broken Instagram (strips IG, retries FB-only), rate limits (backoff), transient 500s (retry), targeting too narrow (broaden), duplicate names (append suffix). Escalates unfixable errors with clear human instructions. → `scripts/error_agent.py`
- [x] **Expanded config validation** — Now checks table IDs, warns on missing Instagram/pixel when optimization goal is CONVERSIONS. → `scripts/config_loader.py`
- [x] **Refactored test_connection.py** — Uses shared preflight module, now also checks Instagram and pixel. → `scripts/test_connection.py`

### Current State

| Metric | Value |
|--------|-------|
| Healthy clients | 10/14 |
| Unhealthy (broken IG IDs) | 4 (fe_fig_and_eagle, fm_forming_men, pp_primal_path, rd_resilient_daughters) |
| Self-healing coverage | IG auth, rate limits, transient errors, duplicates, targeting, video processing |
| Deployed | Modal webhook + health endpoint |

### Known Issues to Watch

- 4 clients have deprecated Instagram IDs (legacy endpoint error 36106). Self-healing auto-strips IG and retries Facebook-only. Long-term fix: update IG IDs or remove from config.
- `modal app logs` streams indefinitely — no easy way to pull historical logs. Consider adding launch logging to a database (Phase 2 will solve this with `launch_logs` table).
- API version upgraded from v21.0 → v22.0 (v21.0 deprecated Sep 2025). Monitor for any v22.0 deprecation announcements — latest is v25.0 as of Mar 2026.

---

## Phase 2: Web UI [NEXT]

**Goal**: Replace Airtable with a proper web app. Nova-inspired but better.

### Tech Stack

| Component | Choice |
|-----------|--------|
| Frontend | Next.js 14+ (App Router) |
| UI | Tailwind + shadcn/ui |
| Database | Supabase (Postgres + Auth + File Storage + Realtime) |
| Auth | Supabase magic link (2-5 users) |
| Backend | Keep Modal for launching |

### 2A. Database Schema

Replace Airtable + JSON config files with Supabase tables:
- `clients` — replaces fb_ads_config.json
- `creatives` — NEW creative library with dimensions, tags, launch status
- `multi_placement_groups` — pairs 1:1 + 4:5/9:16 creative variants
- `ad_copy_templates` — reusable copy templates
- `drafts` — replaces Airtable Ad Sets table
- `draft_ads` — replaces Airtable Ads table
- `launch_logs` — audit trail (what was created, when, by whom, any errors)

### 2B. Python Backend Adapter

- `scripts/supabase_reader.py` — Same interface as airtable_reader (zero changes to main.py)
- `scripts/supabase_writer.py` — Writes back to Supabase + launch_logs
- Dual-source support in modal_webhook.py (Airtable + Supabase payloads)

### 2C. Frontend Pages (Nova-inspired)

| Section | Route | Page |
|---------|-------|------|
| — | `/` | Dashboard — recent launches, health status |
| Launch | `/launch` | Launch Ads — table of creatives with ad name, ad profiles (FB + IG per ad), primary text, links, CTA, ad set assignment. Save Draft, Bulk Edit, Load Template, Group Creatives. "Launch Ads" button. |
| | `/launch/multi-placement` | Multi-placement grouping — visual pairing of aspect ratios |
| | `/creatives` | Creative Library — upload from local/Google Drive/Dropbox. Browse with filters. |
| | `/launched` | Launched Ads — audit trail with status badges |
| | `/drafts` | Saved drafts |
| Ad Copy | `/ad-copy/defaults` | Default Ad Copy per client — auto-fills new launches |
| | `/ad-copy/templates` | Reusable copy templates |
| Setup | `/settings/accounts` | Client config — FB Page + IG selectors with validation |
| | `/settings/naming` | Ad Naming Convention builder (drag-drop tags, live preview) |
| | `/settings/launch` | Launch Settings — tracking, paused toggle, geo |
| System | `/health` | Health Dashboard — all clients green/red |

### UI Improvements Over Nova

- Per-ad Instagram validation with warning icons
- Pre-launch validation panel (checklist of checks with green/red)
- Real-time launch progress via Supabase realtime
- Google Drive link integration for bulk creative import

### Migration Strategy

- Run Airtable + Supabase in parallel (adapter pattern)
- Migrate client configs first (JSON → clients table)
- Switch clients one at a time
- Keep Airtable reader as fallback

---

## Phase 3: Prompt/Chat Interface [FUTURE]

**Goal**: Natural language ad launching — "Upload these to 12 South with $50/day broad women 25-45"

### 3A. Natural Language Parser

- `scripts/prompt_parser.py` — Claude API parses NL into structured ad_set JSON
- System prompt includes client name→slug mapping, valid field schemas
- Tool use for guaranteed structured output
- Returns partial brief that **pre-fills the form** (doesn't auto-launch for safety)

### 3B. Chat UI

- `/launch/chat` page — text input + file drag-drop
- Files upload to Supabase Storage
- Claude parses command → pre-fills launch form → user reviews → confirms

---

## File Reference

### Scripts (Python)

| File | Purpose |
|------|---------|
| `main.py` | Main orchestrator — reads brief, creates Meta objects |
| `modal_webhook.py` | Modal webhook + health endpoint |
| `error_agent.py` | Self-healing error handler |
| `preflight.py` | Pre-flight validation + Instagram resolution |
| `config_loader.py` | Loads credentials + client config |
| `airtable_reader.py` | Reads Ad Set + Ads from Airtable |
| `meta_api.py` | All Meta Marketing API operations |
| `targeting.py` | Builds targeting specs |
| `notifier.py` | Slack notifications |
| `test_connection.py` | CLI pre-flight checks |
| `activate_ads.py` | Moves PAUSED → ACTIVE |
| `sync_meta_names.py` | Syncs Meta naming back to Airtable |

### Endpoints

| Endpoint | Method | URL |
|----------|--------|-----|
| Webhook | POST | `https://rooster--fb-ads-launcher-webhook.modal.run` |
| Health | GET | `https://rooster--fb-ads-launcher-health.modal.run` |
