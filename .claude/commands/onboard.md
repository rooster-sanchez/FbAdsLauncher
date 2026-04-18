---
description: Walk a new user through first-time setup — API keys, per-client config, connection test
---

# /onboard — FB Ads Launcher first-time setup

You are onboarding a user who just cloned this repo. Your job is to get them to a working launcher without them ever touching the README. Be warm, concise, and concrete. Never assume prior knowledge of Meta Business Manager or Airtable internals.

Follow the stages below in order. Between stages, give a one-line progress update. Use the `AskUserQuestion` tool for any choice with a small option set; use free-form prompts for IDs/secrets (ask in chat, wait for reply).

**Ground rules for the whole flow:**
- Never echo a full secret back to the user. Confirm with last 4 chars only (e.g. `FB_ACCESS_TOKEN captured: ...ab12`).
- Never `git add` `.env` or any file containing a secret. `.gitignore` already excludes `.env`, but do not stage it.
- Never delete anything. If a client dir already exists, abort that stage and ask — don't overwrite.
- If the user wants to stop partway through, stop cleanly and tell them `/onboard` resumes from current state (the flow is idempotent — Stage 0 detects what's already done).

---

## Stage 0 — Detect current state

Run these checks silently:
- Does `.env` exist at repo root?
- Does `.env` contain real values (i.e. lines don't contain `your_` or `XXX`)?
- For each `clients/*/` dir except `_example`: does `fb_ads_config.json` have a real `airtable_base_id` (not `appXXXXXXXXXX`)?

Print a one-line summary:

```
Current state: Secrets [OK|missing]  Clients onboarded: [n]
```

If everything is already set up, say so and offer: "Looks like you're fully onboarded. Want to add another client, or run a connection check?" — branch accordingly. Otherwise continue.

---

## Stage 1 — Global secrets (`.env`)

Skip this stage if Stage 0 showed secrets OK.

If `.env` doesn't exist: `cp .env.example .env` first.

For each of the 3 keys below, if missing or placeholder, collect one at a time:

### 1a. `FB_ACCESS_TOKEN` (Meta Marketing API)

Say to the user:

> I need a Meta **System User access token** with permanent credentials. Here's how to get one:
>
> 1. Go to **business.facebook.com** → **Business Settings**
> 2. Left sidebar → **Users** → **System Users**
> 3. Click an existing system user or **Add** a new one (name it something like "Ads Launcher")
> 4. Hit **Generate New Token** → pick your Meta app → select scopes:
>    - `ads_management`
>    - `ads_read`
>    - `business_management`
>    - `pages_read_engagement`
> 5. **Copy the token** (you won't see it again).
>
> Paste it here.

After the user pastes, use `Edit` to replace the `FB_ACCESS_TOKEN=...` line in `.env`. Confirm with `Captured FB_ACCESS_TOKEN (...last4).`

### 1b. `AIRTABLE_API_KEY` (Airtable PAT)

Say:

> Now an **Airtable personal access token**:
>
> 1. Go to **airtable.com/create/tokens**
> 2. Click **Create new token**. Name it "FB Ads Launcher".
> 3. Scopes — add all four:
>    - `schema.bases:read`
>    - `data.records:read`
>    - `data.records:write`
>    - `webhook:manage`
> 4. Access — add **every** Airtable base you want this launcher to read from (you can add more later).
> 5. Click **Create token** and copy it.
>
> Paste here.

Replace in `.env`, confirm with last 4 chars.

### 1c. `SLACK_WEBHOOK_URL` (optional)

Say:

> Slack notifications are optional — I can skip this if you don't use Slack. If you want them:
>
> 1. Go to **api.slack.com/apps** → create or open an app
> 2. **Incoming Webhooks** → enable → **Add New Webhook to Workspace**
> 3. Pick the channel → copy the URL (starts with `https://hooks.slack.com/services/...`)
>
> Paste the URL, or type `skip`.

If `skip`, leave the line blank in `.env` — [scripts/notifier.py](../../scripts/notifier.py) no-ops on blank. Otherwise substitute.

---

## Stage 2 — Single brand or agency?

Use `AskUserQuestion`:

- **Question:** "Are you launching ads for one brand, or multiple clients?"
- **Options:**
  - "One brand" — run Stage 3 once
  - "Multiple clients (agency)" — run Stage 3 in a loop, asking "onboard another?" after each

---

## Stage 3 — Per-client config (loop body)

### 3a. Name + slug

Ask: "What's the brand/client name? (e.g. 'Primal Path')"

Derive the slug using this convention (matches every existing client in `clients/`):
- 2-3 character prefix (initials of the brand, lowercase)
- underscore
- full name, lowercase, spaces→underscores, strip punctuation

Examples: `Primal Path` → `pp_primal_path`, `Fix Tax Problems` → `ftp_fix_tax_problems`, `Twelve South` → `ts_twelve_south`.

Show the proposed slug and ask "Use this slug, or override?"

**Collision check:** if `clients/{slug}/` already exists, stop and say: "A client folder already exists at `clients/{slug}/`. I won't overwrite it — pick a different slug or exit `/onboard` and edit that folder by hand."

Otherwise: copy the template — `cp -r clients/_example clients/{slug}` — so the user gets both `fb_ads_config.json` and `launch_preferences.yml` placeholders.

### 3b. Collect IDs

Ask for each ID below, one at a time, with the guidance shown. Use `Edit` to substitute into `clients/{slug}/fb_ads_config.json` as each answer arrives.

1. **`fb_ad_account_id`** — "Open your ad account in **Ads Manager** (adsmanager.facebook.com). The top-left account dropdown shows `act_XXXXXXX` — paste the number only (no `act_` prefix)."

2. **`fb_page_id`** — "Go to your Facebook page → **About** → **Page transparency** → **Page ID**. Paste the number."

3. **`instagram_user_id`** — **auto-resolve first.** Call the helper via Bash:

   ```bash
   python3 -c "
   from scripts.preflight import resolve_instagram
   import json, os
   from dotenv import load_dotenv
   load_dotenv()
   cfg = json.load(open('clients/{slug}/fb_ads_config.json'))
   cfg['fb_access_token'] = os.environ['FB_ACCESS_TOKEN']
   ig = resolve_instagram(cfg)
   print(ig or '')
   "
   ```

   If it returns an ID, tell the user: "I auto-detected IG account `{id}` linked to this page. Use this?" and substitute on confirm.

   If it returns blank, ask: "Couldn't auto-resolve. Paste the Instagram user ID manually, or type `skip` if this client is Facebook-only." If `skip`, leave as `null` in the JSON (Facebook-only clients like `bc_bella_coterie` run fine without IG).

4. **`default_pixel_id`** — "In Meta **Events Manager** → **Data Sources**, find your pixel → **Details** → copy the ID. Type `skip` if no pixel yet (preflight will warn but not fail)."

5. **`airtable_base_id`** — "Do you already have an Airtable base for this client's ad briefs, or should I help create one?"
   - If existing: "Paste the base URL (from Airtable) or the `app...` ID directly."
     - Extract `app...` from URL if full URL given (it's the first path segment after `airtable.com/`).
   - If creating new: "Go to **airtable.com/create** → create a blank base → name it whatever you like → paste me the URL once you're on the base page."

6. **`airtable_ad_sets_table_id` + `airtable_ads_table_id`** — Ask: "Has this base already been set up with the Ad Sets + Ads tables, or is it empty?"

   - **Empty** → offer: "I can auto-create both tables with the correct schema. Run it now?" If yes:

     ```bash
     python3 scripts/setup_airtable_base.py {base_id}
     ```

     Parse the printed table IDs from output; substitute into JSON.

   - **Already set up** → "Paste the Ad Sets table ID (`tbl...`)" then "Paste the Ads table ID (`tbl...`)."

After all 6 IDs, verify the config JSON has no remaining `XXX` placeholders (except `instagram_user_id` and `default_pixel_id` which may be legitimately `null`).

---

## Stage 4 — Launch preferences (optional)

Ask via `AskUserQuestion`:
- "Want to set up launch defaults (budget, audience, exclusions) for this client now, or skip? You can always edit `launch_preferences.yml` later."
- Options: "Set up now" / "Skip — I'll edit later"

If skip: leave the `_example` copy of `launch_preferences.yml` in place (already has placeholder values), and tell the user it's there for later.

If setting up now, prompt for the minimal useful set:
- `default_daily_budget` (USD per ad set) — default 50
- `default_audience_type` — broad / lookalike / interest (AskUserQuestion)
- `default_geo_locations.countries` — accept comma-separated country codes, default `US`
- `default_optimization_goal` — default `OFFSITE_CONVERSIONS`
- `default_conversion_event` — default `PURCHASE`
- `standard_exclusions` — "Any custom audience IDs to always exclude? Paste IDs + labels, or `skip`."

Write into `clients/{slug}/launch_preferences.yml` using `Edit`.

---

## Stage 5 — Verify

Run the end-to-end connection test:

```bash
python3 scripts/test_connection.py {slug}
```

Relay the output verbatim. Interpret the result:

- **All OK** — celebrate, move to Stage 6.
- **Token FAIL** — "Your token is invalid or lacks scopes. Regenerate at business.facebook.com with the scopes I listed in Stage 1a, then re-run `/onboard`."
- **Ad account FAIL** — "The system user token doesn't have partner access to ad account `act_{id}`. In Meta Business Settings, under Partners → your Partner BM, make sure the client has shared ad account access with your BM."
- **Page FAIL with error code 10** — acceptable, note it and proceed (token lacks read on the page but ads still work).
- **Instagram WARN** — acceptable.
- **Pixel WARN** — acceptable if pixel was skipped.
- **Airtable FAIL** — "Airtable base ID `{id}` isn't accessible. Either the ID is wrong, or your PAT doesn't have access to that base. Go to airtable.com/create/tokens, edit your token, and add the base to its Access list."

Loop fix → re-run until clean.

---

## Stage 6 — Wrap

Print a tailored summary:

```
Setup complete for {slug}. ✅

Created:
  .env                                      (secrets — gitignored)
  clients/{slug}/fb_ads_config.json         (client config)
  clients/{slug}/launch_preferences.yml     (defaults — optional)

Next steps:
  1. Deploy the Modal webhook:
       python3 -m modal deploy scripts/modal_webhook.py
  2. In Airtable, add an automation on the Ad Sets table that POSTs
     {{"record_id": "{{record_id}}", "client_slug": "{slug}"}}
     to the Modal webhook URL when status changes to "Ready to Launch".
  3. Test a dry run:
       python3 scripts/main.py {slug} <any_record_id> --dry-run
```

**If agency mode:** ask "Onboard another client?" via `AskUserQuestion` (Yes / Done). Yes → loop back to Stage 3. Done → final summary listing all onboarded clients.
