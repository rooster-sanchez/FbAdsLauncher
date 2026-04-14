# Lessons Learned

<!-- Format: - **Context** → Fix/Rule -->

## Meta Marketing API

- Campaign creation requires `is_adset_budget_sharing_enabled: false` for ABO campaigns
- Ad set creation requires `bid_strategy: LOWEST_COST_WITHOUT_CAP` and `targeting_automation: {advantage_audience: 0}` in targeting spec
- Video ad creatives require a thumbnail (`image_url` in `video_data`) — fetch via `GET /{video_id}/thumbnails`
- Use `instagram_user_id` (not `instagram_actor_id`) in `object_story_spec` — get the correct ID from `GET /{page_id}?fields=instagram_business_account`
- `special_ad_categories` must be sent as string `"[]"` not empty array

- Instagram user IDs using legacy endpoints (error code 36106) are deprecated and will fail. Fixed by updating configs with correct IG IDs: PP/RD/FM use @fatherscollective (17841411587000289), FE uses 17841469065114612. To find the correct IG for a client, check existing ads: `GET /{adset_id}/ads?fields=creative{object_story_spec}`.
- Instagram auto-resolution via `GET /{page_id}?fields=instagram_business_account,connected_instagram_account` and `/instagram_accounts` edge doesn't always work — some pages have no IG linked. This is fine, they run Facebook-only.
- Pre-flight validation should run BEFORE any Meta objects are created, not at creative-creation time. Otherwise orphaned campaigns/ad sets accumulate when IG fails.

- **API version must stay current.** Meta deprecates old API versions. Using deprecated versions can cause misleading errors (e.g., PAC broken on v22.0 due to Segment Asset Customization deprecation). Currently on v25.0. Check `meta_api.py:API_VERSION`.

- **PAC (Placement Asset Customization) creatives on v25.0:** Require `ad_formats` field (`["SINGLE_IMAGE"]` or `["SINGLE_VIDEO"]`) in `asset_feed_spec`. Do NOT include `optimization_type` — it triggers deprecated Segment Asset Customization. Customization rules must combine FB+IG in the same rule (not split per-platform), otherwise Meta returns "duplicate ad asset values" error.

- **PAC + standard creatives can coexist on v25.0.** An ad set can mix PAC (`asset_feed_spec`) and standard (`object_story_spec`) creatives — no `force_pac` needed. This was broken on v22.0.

- **Plain Flexible Ads (asset_feed_spec WITHOUT `asset_customization_rules`) require `is_dynamic_creative=true` ad sets — and those allow only 1 ad.** When mixing video ads + a multi-format (1:1 + 9:16) static in the same ad set, DO NOT use `create_ad_creative` with `additional_media_refs` for the static — Meta will accept the creative, then reject the `create_ad` call with error subcode 1885553 "maximum one active ad in dynamic-content ad set". Use `create_pac_creative` instead: it adds `asset_customization_rules` mapping media to placements, which Meta treats as PAC (not dynamic creative) and allows in standard ad sets alongside other ads.

- **`excluded_custom_audiences` must be nested INSIDE the `targeting` JSON, not a top-level param.** On v25.0 Meta silently drops a top-level `excluded_custom_audiences` field (returns `{success: true}` but the audiences are never stored — verifiable via GET /{adset_id}?fields=targeting). Setting them via `targeting.exclusions.custom_audiences` is also rejected (subcode 1870221: "Custom audiences can no longer be used with the exclusions field"). The only path Meta actually persists is `targeting.excluded_custom_audiences = [{id: "..."}]`. Fixed in `create_adset` — always inject into the targeting dict before `json.dumps`.

- **PAC duplicate asset dedup:** When two media slots share the same hash/video_id (e.g., user uploads same file for 9:16 and right_hand_column), merge their labels onto a single media entry. Meta rejects entries with duplicate asset values.

- **PAC customization rules must only reference placements available to the ad set.** If no Instagram account is configured (Facebook-only placements), the customization_spec must not include `instagram_positions`. Similarly, the third placement group (right_hand_column) should be Facebook-only.

- **When launching ads into an EXISTING ad set, match the identity its current active ads use.** The ad set's `targeting.publisher_platforms` dictates whether IG placements are enabled; if IG is on (default when `publisher_platforms: None`), a FB-only creative will fail with subcode 1772103 ("Falta la cuenta de Instagram"). And if the existing ads reference a page/IG your access token can't manage, you'll get error code 10 subcode 1341012 ("No tienes permisos para acceder a este perfil"). Before launching, `GET /{adset_id}/ads?fields=creative{object_story_spec}` on ACTIVE ads to see the exact `page_id` + `instagram_user_id` in use — then either reuse those, or confirm the client wants a different identity (some ad sets in the same campaign run under different pages for historical/legacy reasons).

- **CRITICAL: Rollback must NEVER delete existing objects.** When using "Existing" campaign/ad set mode, those objects are the user's live campaigns with spend history. The rollback must only delete NEWLY CREATED objects (`is_new=True`). Deleting an existing campaign cascades to delete all its ad sets and ads — including ones with historical data. This was a catastrophic bug that deleted a campaign with $3,769 in spend. Fixed by tracking `is_new` flag in `created_objects` tuples.

- **Meta campaign deletion is permanent.** `DELETE /{campaign_id}` is a hard delete — you cannot restore by setting `status=PAUSED`. The campaign goes to DELETED state and can only be duplicated (empty shell). Always use `status=ARCHIVED` instead if you need soft-delete behavior.

- **Cannot fetch DELETED objects via list endpoints.** `GET /act_{id}/campaigns?effective_status=["DELETED"]` returns error 100 subcode 1815001 ("No se pueden solicitar objetos eliminados en este extremo"). When fetching all statuses, exclude `DELETED` from the `effective_status` filter. Use all other statuses: ACTIVE, PAUSED, ARCHIVED, IN_PROCESS, WITH_ISSUES, CAMPAIGN_PAUSED, ADSET_PAUSED, DISAPPROVED, PENDING_REVIEW, PREAPPROVED, PENDING_BILLING_INFO.

## Self-Healing / Error Agent

- **`run_launcher` must accept `config_override`.** The self-healing wrapper mutates config in-place (e.g., strips IG), but if `run_launcher` always calls `load_all()` it gets a fresh config and the fix is lost. Always pass the mutated config through on retries.

- **Error diagnosis operator precedence matters.** `code == 190 or "oauthexception" in msg` matches ANY OAuthException error (including IG legacy #36106), not just token expiry. Use parentheses: `code == 190 or ("token" in msg and "expired" in msg)`.

- **`strip_instagram` must set `_ig_stripped` flag.** After stripping IG, `resolve_instagram()` in preflight.py will re-resolve the IG from the page on retry, undoing the fix. Set `config["_ig_stripped"] = True` and check it in `resolve_instagram` and `_resolve_instagram_user_id` to skip resolution.

- **Large video uploads (>50 MB) can return HTTP 413 (Payload Too Large) with an empty response body.** This is not a Meta Graph API error — it's the web server/CDN rejecting the single-request upload. Fix: use Meta's chunked upload protocol (`upload_phase=start/transfer/finish`) for files over 50 MB. The threshold in `meta_api.py` is `CHUNKED_UPLOAD_THRESHOLD = 50 * 1024 * 1024`.

- **preflight.py must use the same API version as meta_api.py.** A mismatch (e.g., v21.0 vs v25.0) means preflight checks hit a different API version than actual ad creation. This can cause misleading preflight results and inconsistent API behavior from the same token. Both files should reference the same `API_VERSION` constant ideally, or at minimum stay in sync manually.

- **Meta collapses single `\n` in ad primary text.** Airtable stores line breaks as single `\n`, but Meta's ad rendering swallows them — only `\n\n` (double newline) produces a visible paragraph break. Fix: `_normalize_line_breaks()` in `airtable_reader.py` converts any sequence of 1+ newlines to `\n\n` before the text reaches the API.

- **Flex (Flexible) Ads cannot mix images and videos.** `asset_feed_spec` requires either `images` + `ad_formats: ["SINGLE_IMAGE"]` OR `videos` + `ad_formats: ["SINGLE_VIDEO"]`, not both. When both types are present, use images only and drop videos. Previously, the first media's type determined the branch, silently discarding all assets of the other type.

## General
