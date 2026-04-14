# FB Ads Launcher in Claude Code — Full YouTube Script
## "I Built a Facebook Ads Launcher Using AI That Does What a $5K/Month Media Buyer Does"

---

## 1. THE STAKES HOOK (0:00–0:15)

**[ON CAMERA — tight frame, high energy, straight to it]**

Most DTC brands are burning $2,000 to $5,000 a month on a media buyer just to *set up* campaigns — not even to strategize, just to physically build them inside Ads Manager. Click, click, click, naming conventions, targeting, uploading creatives — the operational grunt work.

I just built a system in Claude Code that does all of that in about 90 seconds. And everything it creates is paused — nothing spends a dollar until you say so.

---

## 2. CREDIBILITY DROP (0:15–0:30)

**[ON CAMERA — delivered fast, almost thrown away]**

For those who don't know — I'm Rooster. I'm a fractional CMO at Sanchez & Savage. We work with $1M to $20M DTC brands — Hostshare, Twelve South, about 14 accounts right now. Performance marketing is what I do all day — CPAs, ROAS, creative testing, account architecture. Foxwell Founders certified, if that matters to you.

What I'm about to show you is the system I actually use. This isn't a demo. This is production.

---

## 3. THE PROMISE + INVITATION (0:30–0:50)

**[ON CAMERA]**

By the end of this video, you're going to see how to build a Facebook Ads Launcher inside Claude Code that does three things:

One — reads a campaign brief from Airtable and creates the full campaign structure in Meta: campaign, ad sets, ads, creatives, targeting, the whole thing.

Two — validates everything *before* it touches your ad account. Token, page, Instagram, pixel — six checks before a single API call.

Three — if something breaks mid-launch, it diagnoses the error, fixes it, and retries automatically. Self-healing.

Let's get into it.

---

## 4. CONTEXT SETTING / "WHAT CHANGED" (0:50–3:30)

**[ON CAMERA — walking through the evolution]**

Right — so let me give you the quick history of how DTC brands have managed Meta ad launches, because it explains why this matters *now*.

**[Screen: simple timeline graphic or just talk to camera]**

First wave — agencies. You'd pay an agency $3K to $10K a month, and part of what you were paying for was literally someone clicking buttons inside Ads Manager. Building campaigns, naming them, uploading creatives, setting budgets. Skilled work, but operational.

Second wave — in-house media buyers. Brands brought it in-house. Same operational work, just on your payroll now. $60K to $80K a year for someone who spends a meaningful chunk of their time on *setup*, not strategy.

Third wave — and this is where most brands are right now — Meta's own AI tools. Advantage+, broad targeting, dynamic creative. And look, those are great for *delivery optimization*. Meta's algorithm is genuinely good at finding buyers once the campaign is live. But here's the thing — Advantage+ doesn't *build* your campaigns. It doesn't read your brief, name your ad sets correctly, upload your creatives, set your exclusions, wire up your UTMs. You still need a human for the setup. Or you did.

**[Lean in]**

Fourth wave — and this is what we're doing today — is using Claude Code as that operational layer. Not replacing your media buyer's brain. Replacing their hands. The 2 hours of setup work before Meta's AI even kicks in.

Now — if you're hearing "Claude Code" and thinking *what the hell is that* — here's the simplest way I can put it.

Claude Code is like having a junior media buyer that lives inside your terminal. You can talk to it in plain English, it can read files, write code, call APIs, and — this is the key part — it can *connect directly to the Meta Marketing API*. No middleman. No Zapier. No drag-and-drop builder. It writes the API calls, sends them, handles the responses.

Think of it like this — if Ads Manager is the steering wheel, Claude Code is the self-driving system underneath. You still decide where to go. It handles the driving.

---

## 5. THE THREE STEPS (3:30–4:00)

**[ON CAMERA]**

Alright — here's how we're going to build this. Three steps.

**Step 1 — Design it.** Define the problem, pick the tools, architect the system *before* writing any code. Most people skip this and end up rebuilding from scratch two weeks later.

**Step 2 — Wire it.** Connect everything — Claude Code to the Meta API, Airtable to the webhook, error handling, notifications. This is the bulk of the build.

**Step 3 — Ship it.** Dry run, live run, verify, deploy. The system is live and producing.

Simple as that. Let's go.

---

## 6. THE LIVE BUILD (4:00–35:00)

---

### STEP 1: DESIGN IT (4:00–16:00)

#### The Problem (4:00–6:00)

**[Screen: Airtable base with campaign briefs visible]**

Right — what problem are we solving and for who.

Here's the situation. I manage 14 DTC ad accounts. Every week, I'm launching new campaigns across these accounts — new products, new angles, seasonal pushes. Each launch means:

- Create a campaign in Meta
- Create one or more ad sets with targeting, budget, scheduling
- Upload creatives — images, videos, carousels
- Create the ads with headlines, primary text, CTAs, UTM parameters
- Name everything according to our naming convention
- Set exclusion audiences so we're not retargeting past buyers
- Make sure the pixel is wired, Instagram is connected, the page is right

For *one* launch. Multiply that by 14 accounts. That's what I was doing manually.

The goal is simple: I want to fill out a row in Airtable — client, budget, targeting, creatives, copy — and have Claude Code turn that into a fully built campaign in Meta. Everything paused. Nothing spends until I review it and explicitly activate.

**[Camera]**

And notice — the KPI here isn't some vanity metric. It's *hours saved per week* and *error rate*. Every manual launch is a chance to fat-finger a budget, forget an exclusion, or mis-name an ad set. The system should be faster *and* more accurate than doing it by hand.

---

#### The Tools (6:00–9:00)

**[Screen: architecture diagram or just the terminal]**

Right — here's what's in the stack:

**[Walk through each one]**

**Claude Code** — the brain. This is what orchestrates everything. It reads the brief, makes decisions, calls the APIs. I'm running it in the terminal, and later I deploy it on Modal so it can trigger automatically.

**Meta Marketing API v25.0** — and here's something important. I'm *not* using Facebook's Python SDK. I'm hitting the Graph API directly with raw HTTP requests. Why? Because the SDK is bloated, poorly documented for the latest API version, and Claude Code is actually better at constructing raw API calls than navigating the SDK's abstraction layers.

**[Camera — direct callout]**

Here's the thing — most tutorials will tell you to install the facebook_business SDK. Don't. At least not for this. Raw requests give you full control, and when something breaks — and it *will* break, Meta's API is... let's call it *character-building* — you can see exactly what went wrong in the request and response. No SDK abstraction hiding the error from you.

**Airtable** — the brief intake. This is where I fill out the campaign details. Each row is an ad set. Linked records are the individual ads with creatives attached. When I mark a row "Ready to Launch," that's the trigger.

**Modal** — serverless deployment. The launcher runs as a webhook on Modal. Airtable fires a POST request, Modal catches it, runs the launcher. No server to maintain. Costs basically nothing at this volume.

**Slack** — notifications. Success or failure, I get a Slack message with the campaign ID, a link to Ads Manager, and — if something failed — what went wrong and what to do about it.

**[Camera]**

Notice there's no Zapier, no Make, no n8n in this stack. Not because those tools are bad — I use n8n for other things. But for something this specific and this critical to ad spend, I want code. Code I can version control, test, and debug line by line.

---

#### The Architecture (9:00–16:00)

**[Camera]**

Now — before I write a single line of code, I need to design three things. This is the part most people skip, and it's the difference between a toy demo and a production system.

Three things: the data flow, the safety model, and the config structure.

**[Screen: show the flow]**

**Data flow.** An Airtable automation fires a webhook to Modal. Modal calls the main orchestrator script. That script:
1. Loads the client's config — ad account ID, page, pixel, Instagram, defaults
2. Reads the brief from Airtable — campaign name, budget, targeting, creatives
3. Runs six pre-flight checks before touching Meta
4. Creates the campaign, ad set, ads — in that order
5. Writes the Meta IDs back to Airtable
6. Sends a Slack notification

If anything fails at step 4, it rolls back — deletes whatever it already created, in reverse order. No orphaned campaigns cluttering up Ads Manager.

**[Camera — lean in]**

That rollback is critical. Here's why. Let's say the campaign and ad set get created fine, but the third ad fails because of a video encoding issue. Without rollback, you've got a half-built campaign sitting in your ad account that you have to manually clean up. Multiply that across 14 accounts and you're spending more time cleaning up messes than you saved.

**[Screen: show fb_ads_config.json]**

**Config structure.** Every client gets their own config file. Ad account ID, page ID, Instagram user ID, pixel, default targeting, naming convention, UTM parameters. This is what lets me run the same code across 14 completely different accounts.

**[Scroll through the config]**

And then there's `launch_preferences.yml` — this is where I store each client's defaults. Default budget, default audience type, standard exclusion audiences, preferred CTA. So when I fill out a brief, I only need to specify what's *different* from the defaults.

**[Camera]**

Right — and this is a strategic point, not a technical one. The reason I architect it this way — config per client, preferences per client — is because every DTC brand has a different account structure philosophy. Some brands run broad only. Some have lookalike stacks. Some exclude past 180-day purchasers, some exclude 30-day. If you hardcode any of that, the system breaks the moment you onboard a second client.

**Safety model.** Three rules, non-negotiable:

One — everything is created **PAUSED**. The system cannot spend money. Period. Activation is a completely separate script that I run manually after reviewing in Ads Manager.

Two — pre-flight validation runs *before* any Meta API call. If the access token is expired, the pixel doesn't exist, or Instagram isn't authorized — I want to know before I've created half a campaign.

Three — idempotency. If a record has already been launched — Meta IDs exist in Airtable — the system skips it. No duplicate campaigns.

**[Camera — productive tangent, ~30 seconds]**

And look — this is a broader principle that applies to any system you build, not just ads. The difference between the top 10% of operators and everyone else isn't the tools they use. It's that they design for failure *before* they design for success. Anyone can build a happy path. The system's value is in what happens when things go wrong — and things *will* go wrong with Meta's API. I promise you that.

---

### STEP 2: WIRE IT (16:00–28:00)

**[Screen: terminal with Claude Code open]**

Alright — step two. This is where we wire the pieces together. Let me walk you through the actual build.

**[Start showing the codebase]**

#### The Orchestrator — main.py

**[Screen: open main.py]**

This is the main script. When it runs, here's what happens step by step.

First — it loads the client config.

```
config = load_config(client_slug)
```

That reads `clients/{slug}/fb_ads_config.json` and merges in the credentials from the environment. One function call, and I have everything I need about this client's Meta setup.

**[Narrate while scrolling]**

Then it reads the brief from Airtable. The brief comes back as a dictionary — campaign name, budget, targeting type, destination URL, and an array of ads, each with their own headline, primary text, CTA, and attached creatives.

Watch this part — the brief validation. Before we go any further, the system checks: is there a budget? Is there at least one ad? Do the ads have creatives attached? Are the required fields filled in? If anything's missing, it stops here and tells you exactly what's wrong.

**[Camera]**

And that's a deliberate design choice. I'd rather have the system refuse to launch and tell me "Ad 3 is missing a headline" than create a broken campaign that I have to debug inside Ads Manager.

**[Screen: show preflight.py]**

#### Pre-flight Validation — preflight.py

Right — now the pre-flight checks. Six of them.

**[Walk through each check on screen]**

1. **Meta token** — is the access token valid? These expire, and a launch with an expired token is just a waste of everyone's time.
2. **Ad account** — can we actually reach this ad account?
3. **Facebook Page** — is the page ID correct and accessible?
4. **Instagram** — is the Instagram business account linked and authorized? This one is *character-building*, which I'll get to in a second.
5. **Pixel** — does the conversion pixel exist? Only checked if we're optimizing for conversions.
6. **Airtable** — is the API key working?

All six pass? Green light. Any one fails? Full stop, detailed error message, no Meta objects created.

**[Camera — showing the mess]**

Now — the Instagram check. Let me tell you about the most frustrating 3 hours of my life building this system.

**[Screen: show the error or LESSONS.md]**

Meta has deprecated their legacy Instagram user ID endpoint. If you use the old one, you get error code 36106 — "This endpoint is deprecated." No warning in the docs, no migration guide that's easy to find. I had four client accounts breaking because their Instagram IDs were from the legacy system.

The fix? Auto-resolution. The pre-flight check now calls `GET /{page_id}?fields=instagram_business_account` to get the *current* Instagram user ID directly from the Facebook Page. If there's no Instagram linked — some clients are Facebook-only — it just skips Instagram placement. No error, no failure, just adapts.

**[Camera]**

And that's the kind of thing you'd never see in a clean demo video. But it's the reality of working with the Meta API. There are about 20 gotchas like this, and I've documented every single one in a lessons file so the system — and I — don't make the same mistake twice.

**[Screen: show meta_api.py]**

#### The Meta API Layer — meta_api.py

This is where the actual Meta objects get created. Raw HTTP requests to the Graph API v25.0.

**[Walk through campaign creation]**

Campaign creation. Watch the parameters:

```python
params = {
    "name": campaign_name,
    "objective": "OUTCOME_SALES",
    "status": "PAUSED",
    "special_ad_categories": "[]",
}
```

**[Camera — direct callout]**

Notice that — `special_ad_categories` is a *string* `"[]"`, not an empty array. If you send an actual empty array, Meta returns an error. Took me an hour to figure that out. It's now in the lessons file, and I'll never lose that hour again.

**[Screen: show ad set creation]**

Ad set creation. This is where targeting, budget, and optimization come together.

```python
params = {
    "campaign_id": campaign_id,
    "name": adset_name,
    "daily_budget": int(budget * 100),  # Meta wants cents
    "optimization_goal": "OFFSITE_CONVERSIONS",
    "billing_event": "IMPRESSIONS",
    "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    "targeting": json.dumps(targeting_spec),
    "status": "PAUSED",
    "destination_type": "WEBSITE",
}
```

Budget is in cents — another gotcha. If you send `50` thinking that's $50, you just set a 50-cent daily budget. Ask me how I know.

**[Screen: show targeting.py]**

#### Targeting — targeting.py

Three targeting types: broad, lookalike, and interest-based.

**Broad** — geo, age, gender. That's it. Let Meta's algorithm do the finding. This is what most of my clients run these days, honestly.

**Lookalike** — broad plus a custom audience seed. Past purchasers, email list, whatever the client has.

**Interest** — broad plus Meta interest keywords. The system hits the `search?type=adinterest` endpoint to find the right interest IDs.

And then exclusions get layered on top — pulled from the client's `launch_preferences.yml`. Past purchasers, existing customers, whatever the client's standard exclusion set is.

**[Camera]**

The exclusions are non-negotiable. Even if the brief doesn't mention them, the system auto-applies the client's standard exclusions. Because — and every media buyer knows this — the fastest way to waste ad spend is showing acquisition ads to people who already bought.

**[Screen: show creative creation code]**

#### Creatives — The Fun Part

This is where it gets interesting. The system handles four creative formats:

**Single image** — downloads the image from Airtable, uploads to Meta, creates the ad creative with the headline, primary text, CTA, and link.

**Single video** — same flow, but videos over 50MB use Meta's chunked upload protocol. Three API calls: start, transfer, finish. The system detects file size and switches automatically.

**[Camera]**

And here's a fun one — video thumbnails. When you upload a video to Meta, it generates thumbnails automatically. But you have to explicitly *fetch* them with a separate API call and include the thumbnail URL in your creative. If you don't, your ad renders with a black frame. Another lesson learned the hard way.

**Carousel** — multiple images in a swipeable format. Each card gets its own headline, description, and link.

**Multi-placement (PAC)** — Placement Asset Customization. Different creatives for different placements — feed gets a square image, Stories gets a vertical video, Reels gets something else. This was the hardest one to get right.

**[Camera — showing the mess]**

PAC almost broke me. We upgraded from Meta API v22 to v25, and the entire Segment Asset Customization system was deprecated. The new PAC format requires an `ad_formats` field, must *not* include `optimization_type`, and — watch this — if you split Facebook and Instagram into separate rules, you get a "duplicate values" error. They have to be combined in the same rule.

Oh, and if you have duplicate media — same image hash appearing twice — you have to merge the labels before sending. Otherwise Meta rejects it.

All of that is in the code now. All of it was discovered through failing, reading the error, and fixing it.

**[Screen: show error_agent.py]**

#### Self-Healing — error_agent.py

**[Camera]**

Right — this is the part I'm genuinely proud of. The error agent.

The launcher is wrapped in a self-healing retry loop. When something fails, instead of just throwing an error, it *diagnoses* the failure and attempts an automatic fix.

**[Screen: walk through the error patterns]**

- **Instagram not authorized (error 200)** — strips Instagram from the creative, retries Facebook-only
- **Rate limited (error 32)** — waits 60 seconds, retries
- **Targeting too narrow (error 100)** — broadens age range and geo, retries
- **Duplicate campaign name** — appends a timestamp, retries
- **Transient server error (500/502/503)** — exponential backoff, retries up to 3 times

And if it *can't* fix it? Sends a detailed Slack message with the error code, the diagnosis, a suggested human action, and the full traceback.

**[Camera]**

Notice what this does economically. Without the error agent, every failed launch means I stop what I'm doing, read the error, figure out the fix, re-run manually. That's 15 to 30 minutes per failure. With the error agent, most failures resolve themselves, and the ones that don't come with a diagnosis that cuts my debugging time to under 5 minutes.

**[Screen: show notifier.py and Slack message]**

#### Notifications — notifier.py

Every launch — success or failure — hits Slack.

**[Show a success notification]**

Success message: green checkmark, campaign name, campaign ID, number of ads created, daily budget, and a direct link to Ads Manager so I can review immediately.

**[Show a failure notification]**

Failure message: red X, what went wrong, what the error agent tried, what I need to do manually. Plus the activation command I can copy-paste when I'm ready to go live.

**[Screen: show modal_webhook.py]**

#### Deployment — modal_webhook.py

Last piece of the connection — Modal.

**[Walk through the webhook code]**

The webhook receives a POST from Airtable with two fields: `record_id` and `client_slug`. That's it. The entire brief lives in Airtable. The webhook just says "go launch this record for this client."

It also has a health endpoint — `GET /health` — that runs all six pre-flight checks across all 14 clients. One URL tells me if anyone's credentials expired, any Instagram broke, any Airtable connection dropped.

**[Terminal: deploy to Modal]**

```bash
python3 -m modal deploy scripts/modal_webhook.py
```

That's it. Deployed. Serverless. Costs fractions of a cent per invocation.

---

### STEP 3: SHIP IT (28:00–33:00)

**[Camera]**

Step three — ship it. Let's launch something.

**[Screen: Airtable base with a real brief filled out]**

Alright — I've got a brief here for one of our clients. New prospecting campaign, broad targeting, $100 daily budget, three single-image ads. The creatives are uploaded, the copy is written, exclusions are set.

First — dry run.

**[Terminal]**

```bash
python3 scripts/main.py bc_bella_coterie recXXXXXXXX --dry-run
```

**[Watch the output]**

Watch this — it loads the config, reads the brief, runs all six pre-flight checks — token good, ad account good, page good, Instagram good, pixel good, Airtable good. Then it *shows* me exactly what it would create — campaign name, ad set parameters, targeting spec, each ad with its creative — without making a single API call.

**[Camera]**

This is my review step. I scan the dry run output, make sure the naming looks right, the budget is right, the targeting makes sense. Takes about 30 seconds.

**[Terminal — live run]**

Good. Let's go live.

```bash
python3 scripts/main.py bc_bella_coterie recXXXXXXXX
```

**[Watch it execute in real time]**

Pre-flight... passed. Creating campaign... got the ID. Creating ad set... targeting applied, budget set, exclusions added... got the ID. Uploading creative one... creating ad one... done. Creative two... ad two... done. Creative three... ad three... done. Writing IDs back to Airtable... done. Slack notification sent.

**[Show the Slack notification]**

There it is. Three ads created, $100 daily budget, all paused. Direct link to Ads Manager.

**[Switch to Ads Manager — show the created objects]**

And if we pop over to Ads Manager — there they are. Campaign, ad set, three ads. All paused. Naming convention matches. Creatives look right. Targeting is clean.

**[Camera]**

That entire launch — from brief to built — took about 90 seconds. No clicking through Ads Manager. No forgetting exclusions. No typos in UTMs. And if I want to activate it:

```bash
python3 scripts/activate_ads.py bc_bella_coterie act_XXXXXXX
```

That moves everything from paused to active. But I only run that after I've reviewed it. The system never spends money without my explicit approval.

---

## 7. PRE-EMPTIVE OBJECTIONS (33:00–35:00)

**[Camera — direct to viewer]**

Alright — there's going to be people watching this thinking two things. Let me address them.

**"Rooster, I already have a media buyer. Why would I need this?"**

You absolutely still need your media buyer. But think about what they're spending their time on right now. If they're spending 30% of their week on campaign setup — building, naming, uploading, wiring — that's 30% they're *not* spending on strategy, creative testing, and performance analysis. This takes the setup off their plate. It makes your media buyer *better*, not redundant. They go from a $70K setup-and-strategy hire to a $70K pure-strategy hire.

**"What about Meta's own AI — Advantage+, broad targeting, all that?"**

Love it. Use it. Advantage+ is *delivery* optimization — it's phenomenal at finding buyers once the campaign is live. But it doesn't *build* the campaign. It doesn't read your brief, create your naming convention, apply your exclusion audiences, upload your creatives with the right UTMs. There's a 2-hour operational gap between "I have a brief" and "Advantage+ is optimizing my delivery." This system closes that gap.

---

## 8. APPLICATION BRIDGE + CTA (35:00–38:00)

**[Camera]**

So now you've seen how to build it. Let me tell you how this actually changes the way I work as a fractional CMO.

**[Screen: show the weekly workflow]**

Monday morning. I review last week's performance across all 14 accounts. I identify which accounts need new creative, which need new audiences, which need budget shifts.

For any account that needs a new launch, I fill out a row in Airtable. Client, campaign type, targeting, budget, creatives, copy. Takes me 5 to 10 minutes per brief because the defaults are pre-loaded from launch preferences.

I mark it "Ready to Launch." The webhook fires. 90 seconds later, Slack tells me it's built. I glance at Ads Manager to verify, run the activation script, and I'm onto the next account.

**[Camera]**

Before this system, launching across 14 accounts took me the better part of a full day. Filling out Ads Manager, double-checking every field, uploading creatives one by one. Now it's about an hour total, including review time. That's roughly 6 hours a week back. Multiply that by 50 weeks — that's 300 hours a year. At a fractional CMO rate, that's... well, you can do the math.

**[Lean in]**

And here's the broader point — and I think this is the productive tangent for this video. The DTC operators who are going to win over the next 2 to 3 years aren't the ones with the best creative eye or the biggest budgets. They're the ones who build *systems*. Creative is important. Strategy is important. But the operators who systematize the operational layer — the boring, repetitive, error-prone stuff — free up all their cognitive bandwidth for the decisions that actually move the needle.

That's what this is. It's not an AI replacing a human. It's a system that handles the mechanical so the human can focus on the strategic.

**[Camera — CTA]**

If you want to see this system in action on your accounts — or if you want to talk about what a systematized performance marketing operation looks like for your brand — we do Strategic Blueprint sessions at Sanchez & Savage. Link's below. 30 minutes, no pitch, just architecture.

And if you want to see me build the next piece of this stack — the creative testing system that automatically spins up variations and kills underperformers — that's the next video. Subscribe so you don't miss it.

Right. Design it, wire it, ship it. Go build something.

---

## APPENDIX: TECHNICAL REFERENCE FOR B-ROLL / SCREEN RECORDINGS

These are the key screens to capture during the build section:

| Timestamp | Screen Recording Needed |
|-----------|------------------------|
| 4:00–6:00 | **Design It** — Airtable base with briefs, linked ads, creatives |
| 6:00–9:00 | **Design It** — Terminal showing project structure, `ls scripts/` |
| 9:00–11:00 | **Design It** — `fb_ads_config.json` and `launch_preferences.yml` open in editor |
| 11:00–13:00 | **Design It** — `main.py` scrolling through the orchestration flow |
| 13:00–15:00 | **Design It** — `preflight.py` showing the six checks |
| 15:00–16:00 | **Design It** — LESSONS.md showing real gotchas |
| 16:00–20:00 | **Wire It** — `meta_api.py` — campaign, ad set, creative creation |
| 20:00–22:00 | **Wire It** — `targeting.py` — broad, lookalike, interest |
| 22:00–25:00 | **Wire It** — Creative formats — PAC, carousel, video upload |
| 25:00–27:00 | **Wire It** — `error_agent.py` — self-healing patterns |
| 27:00–28:00 | **Wire It** — `modal_webhook.py` + `python3 -m modal deploy` |
| 28:00–30:00 | **Ship It** — Dry run in terminal |
| 30:00–33:00 | **Ship It** — Live run + Slack notification + Ads Manager verification |
| 35:00–37:00 | **Application** — Weekly workflow walkthrough (Airtable → Slack → Ads Manager) |

---

## PRODUCTION NOTES

**Estimated runtime:** 35–38 minutes

**Thumbnail concept:** Split screen — left side: Ads Manager with 14 campaigns, right side: terminal with the launcher running. Text: "I Automated Facebook Ads with AI"

**Title options:**
1. "I Built a Facebook Ads Launcher Using AI That Does What a $5K/Month Media Buyer Does"
2. "How I Launch Meta Ads Across 14 Accounts in 90 Seconds (Claude Code Build)"
3. "The DTC Ad Launcher I Built in Claude Code (Full Build)"

**Tags:** Claude Code, Facebook Ads, Meta Marketing API, DTC, performance marketing, AI automation, fractional CMO, ad account management

**Description CTA:** Link to Strategic Blueprint session, link to Sanchez & Savage, link to next video (creative testing system)
