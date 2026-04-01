#!/usr/bin/env python3
"""
Meta Marketing API operations for FB Ads Launcher.
Handles campaign, ad set, ad creative, and ad creation via the Graph API.

All objects are created in PAUSED status by default.
Uses requests directly (no facebook_business SDK dependency).
"""

from __future__ import annotations

import json
import os
import time

import requests

API_VERSION = "v25.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# Valid CTA types for Meta ads
VALID_CTAS = {
    "SHOP_NOW", "LEARN_MORE", "SIGN_UP", "SUBSCRIBE", "GET_OFFER",
    "BOOK_NOW", "CONTACT_US", "DOWNLOAD", "APPLY_NOW", "GET_QUOTE",
    "NO_BUTTON", "WATCH_MORE", "ORDER_NOW", "BUY_NOW",
}

# File extensions for media type detection
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class MetaApiError(Exception):
    """Raised when a Meta API call returns an error."""
    def __init__(self, message: str, code: int = 0, subcode: int = 0):
        self.code = code
        self.subcode = subcode
        super().__init__(f"Meta API Error {code}: {message}")


def _meta_request(method: str, url: str, access_token: str, retries: int = 3, **kwargs) -> dict:
    """Make a request to Meta API with retry logic for transient errors.

    Retries on 500/502/503 with exponential backoff. Never retries 4xx errors.
    """
    for attempt in range(retries):
        resp = requests.request(method, url, timeout=120, **kwargs)

        if resp.ok:
            return resp.json()

        # Parse Meta error format
        try:
            error_data = resp.json().get("error", {})
        except (ValueError, AttributeError):
            error_data = {}

        error_msg = error_data.get("message", resp.text[:300]) or f"HTTP {resp.status_code}"
        error_code = error_data.get("code", resp.status_code)
        error_subcode = error_data.get("error_subcode", 0)
        error_user_msg = error_data.get("error_user_msg", "")
        error_user_title = error_data.get("error_user_title", "")
        if error_user_msg:
            print(f"  Meta user error: {error_user_title}: {error_user_msg}")
        print(f"  Meta full error response: {resp.text[:500]}")

        # Only retry on server errors
        if resp.status_code in (500, 502, 503) and attempt < retries - 1:
            wait = 2 ** attempt
            print(f"  Meta API {resp.status_code}, retrying in {wait}s...")
            time.sleep(wait)
            continue

        # Include user-facing detail if available (otherwise Slack only shows "Invalid parameter")
        full_msg = error_msg
        if error_user_msg:
            full_msg = f"{error_msg} — {error_user_title}: {error_user_msg}"
        raise MetaApiError(full_msg, error_code, error_subcode)

    raise MetaApiError("Max retries exceeded", 0)


# ─── Campaigns ────────────────────────────────────────────────────────────────

def search_campaigns(config: dict, name_contains: str) -> list[dict]:
    """Search for existing campaigns by name (partial match)."""
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/campaigns"
    data = _meta_request(
        "GET", url,
        access_token=config["fb_access_token"],
        params={
            "access_token": config["fb_access_token"],
            "fields": "id,name,status,objective",
            "filtering": json.dumps([{
                "field": "name",
                "operator": "CONTAIN",
                "value": name_contains,
            }]),
            "limit": 50,
        },
    )
    return data.get("data", [])


def create_campaign(config: dict, name: str, objective: str = "OUTCOME_SALES",
                    status: str = "PAUSED") -> str:
    """Create a new campaign. Returns campaign_id."""
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/campaigns"

    payload = {
        "name": name,
        "objective": objective,
        "status": status,
        "special_ad_categories": "[]",
        "is_adset_budget_sharing_enabled": "false",
        "access_token": config["fb_access_token"],
    }

    data = _meta_request("POST", url, access_token=config["fb_access_token"], data=payload)
    campaign_id = data.get("id")
    if not campaign_id:
        raise MetaApiError(f"No campaign ID returned: {data}")
    print(f"  Created campaign: {name} (ID: {campaign_id})")
    return campaign_id


# ─── Attribution ──────────────────────────────────────────────────────────────

# Maps Airtable dropdown values to Meta attribution_spec format
ATTRIBUTION_WINDOWS = {
    "1d_click":            [{"event_type": "CLICK_THROUGH", "window_days": 1}],
    "7d_click":            [{"event_type": "CLICK_THROUGH", "window_days": 7}],
    "1d_click_1d_view":    [{"event_type": "CLICK_THROUGH", "window_days": 1},
                            {"event_type": "VIEW_THROUGH", "window_days": 1}],
    "7d_click_1d_view":    [{"event_type": "CLICK_THROUGH", "window_days": 7},
                            {"event_type": "VIEW_THROUGH", "window_days": 1}],
}


def _build_attribution_spec(window: str) -> list[dict] | None:
    """Convert an attribution window label to Meta's attribution_spec format."""
    key = window.strip().lower()
    spec = ATTRIBUTION_WINDOWS.get(key)
    if spec is None and key:
        print(f"  Warning: Unknown attribution window '{window}', skipping. "
              f"Valid options: {', '.join(ATTRIBUTION_WINDOWS.keys())}")
    return spec


# ─── Ad Sets ──────────────────────────────────────────────────────────────────

def search_adsets(config: dict, campaign_id: str, name_contains: str = "") -> list[dict]:
    """Search for existing ad sets within a campaign."""
    url = f"{BASE_URL}/{campaign_id}/adsets"
    params = {
        "access_token": config["fb_access_token"],
        "fields": "id,name,status,daily_budget,targeting",
        "limit": 100,
    }
    if name_contains:
        params["filtering"] = json.dumps([{
            "field": "name",
            "operator": "CONTAIN",
            "value": name_contains,
        }])

    data = _meta_request("GET", url, access_token=config["fb_access_token"], params=params)
    return data.get("data", [])


def restrict_adset_to_facebook(config: dict, adset_id: str) -> bool:
    """Patch an existing ad set's targeting to Facebook-only placements.

    Used when no Instagram account is configured — removes IG placements
    so creatives don't require an instagram_user_id.
    """
    url = f"{BASE_URL}/{adset_id}"

    # Fetch current targeting, add publisher_platforms restriction
    try:
        data = _meta_request(
            "GET", url,
            access_token=config["fb_access_token"],
            params={"access_token": config["fb_access_token"], "fields": "targeting"},
        )
        targeting = data.get("targeting", {})
        if targeting.get("publisher_platforms") == ["facebook"]:
            return True  # Already restricted

        targeting["publisher_platforms"] = ["facebook"]
        _meta_request(
            "POST", url,
            access_token=config["fb_access_token"],
            data={
                "targeting": json.dumps(targeting),
                "access_token": config["fb_access_token"],
            },
        )
        print(f"  Updated ad set {adset_id} to Facebook-only placements")
        return True
    except Exception as e:
        print(f"  Warning: Could not restrict ad set to Facebook-only: {e}")
        return False


def enable_dynamic_creative(config: dict, adset_id: str) -> bool:
    """Enable is_dynamic_creative on an existing ad set.

    Required when adding Flexible (dynamic creative) ads to an existing
    ad set that wasn't originally created with dynamic creative enabled.
    """
    url = f"{BASE_URL}/{adset_id}"
    try:
        _meta_request(
            "POST", url,
            access_token=config["fb_access_token"],
            data={
                "is_dynamic_creative": "true",
                "access_token": config["fb_access_token"],
            },
        )
        print(f"  Enabled dynamic creative on ad set {adset_id}")
        return True
    except Exception as e:
        print(f"  Warning: Could not enable dynamic creative on ad set: {e}")
        return False


def create_adset(config: dict, campaign_id: str, name: str,
                 targeting: dict, daily_budget_cents: int,
                 optimization_goal: str = None, billing_event: str = None,
                 destination_url: str = "", status: str = "PAUSED",
                 is_dynamic_creative: bool = False,
                 attribution_window: str = "",
                 start_time: str = "",
                 exclusion_audience_ids: list[str] = None) -> str:
    """Create a new ad set. Returns adset_id.

    daily_budget_cents: budget in cents (e.g., $50/day = 5000)
    start_time: ISO 8601 date or datetime string (e.g., "2026-03-10T00:00:00-0500").
                If set, the ad set will start spending at this time.
    """
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/adsets"

    opt_goal = optimization_goal or config["default_optimization_goal"]
    bill_event = billing_event or config["default_billing_event"]

    # Inject Advantage Audience off into targeting (Meta requires this flag)
    targeting.setdefault("targeting_automation", {"advantage_audience": 0})

    # If no Instagram account is configured, restrict to Facebook-only placements
    # (Meta rejects creatives without instagram_user_id when IG placements are enabled)
    if not config.get("instagram_user_id"):
        targeting.setdefault("publisher_platforms", ["facebook"])
        print("  No Instagram account configured — restricting to Facebook placements")

    # Check if the campaign uses CBO (campaign budget optimization)
    # If so, skip ad set budget — Meta doesn't allow both
    is_cbo = False
    try:
        camp_data = _meta_request(
            "GET", f"{BASE_URL}/{campaign_id}",
            access_token=config["fb_access_token"],
            params={"fields": "daily_budget,lifetime_budget,budget_remaining", "access_token": config["fb_access_token"]},
        )
        if camp_data.get("daily_budget") or camp_data.get("lifetime_budget"):
            is_cbo = True
            print(f"  Campaign has CBO budget — skipping ad set daily_budget")
    except Exception:
        pass  # If check fails, proceed with ad set budget

    payload = {
        "name": name,
        "campaign_id": campaign_id,
        "optimization_goal": opt_goal,
        "billing_event": bill_event,
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "destination_type": "WEBSITE",
        "targeting": json.dumps(targeting),
        "status": status,
        "access_token": config["fb_access_token"],
    }

    if not is_cbo:
        payload["daily_budget"] = str(daily_budget_cents)

    # Attribution window optimization (e.g., "7d_click_1d_view", "7d_click", "1d_click")
    if attribution_window:
        attribution_spec = _build_attribution_spec(attribution_window)
        if attribution_spec:
            payload["attribution_spec"] = json.dumps(attribution_spec)

    if is_dynamic_creative:
        payload["is_dynamic_creative"] = "true"

    if start_time:
        payload["start_time"] = start_time

    # Exclusion audiences: top-level param (Meta deprecated targeting.exclusions.custom_audiences)
    if exclusion_audience_ids:
        payload["excluded_custom_audiences"] = json.dumps(
            [{"id": aid} for aid in exclusion_audience_ids]
        )

    # Add promoted object (pixel) if available and using conversion optimization
    if config.get("default_pixel_id") and "CONVERSION" in opt_goal.upper():
        payload["promoted_object"] = json.dumps({
            "pixel_id": config["default_pixel_id"],
            "custom_event_type": "PURCHASE",
        })

    data = _meta_request("POST", url, access_token=config["fb_access_token"], data=payload)
    adset_id = data.get("id")
    if not adset_id:
        raise MetaApiError(f"No ad set ID returned: {data}")
    print(f"  Created ad set: {name} (ID: {adset_id}, ${daily_budget_cents/100:.0f}/day)")
    return adset_id


# ─── Creative Upload ──────────────────────────────────────────────────────────

def detect_media_type(filename: str) -> str:
    """Detect whether a file is an image or video based on extension."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    raise ValueError(f"Unknown media type for file: {filename}")


def upload_image(config: dict, file_path: str) -> str:
    """Upload an image to Meta. Returns image_hash."""
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/adimages"

    with open(file_path, "rb") as f:
        data = _meta_request(
            "POST", url,
            access_token=config["fb_access_token"],
            data={"access_token": config["fb_access_token"]},
            files={"filename": f},
        )

    # Response: {"images": {"filename": {"hash": "abc123"}}}
    images = data.get("images", {})
    for key, val in images.items():
        image_hash = val.get("hash")
        if image_hash:
            print(f"  Uploaded image: {file_path} (hash: {image_hash})")
            return image_hash

    raise MetaApiError(f"No image hash returned: {data}")


CHUNKED_UPLOAD_THRESHOLD = 20 * 1024 * 1024  # 20 MB — Meta gateways can reject single uploads above ~25 MB
CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB per chunk


def _upload_video_chunked(config: dict, file_path: str) -> str:
    """Upload a large video using Meta's chunked upload protocol."""
    ad_account_id = config["fb_ad_account_id"]
    token = config["fb_access_token"]
    url = f"{BASE_URL}/act_{ad_account_id}/advideos"
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    # Phase 1: Start
    start_data = _meta_request(
        "POST", url, access_token=token,
        data={
            "access_token": token,
            "upload_phase": "start",
            "file_size": file_size,
        },
    )
    video_id = start_data.get("video_id")
    session_id = start_data["upload_session_id"]
    start_offset = int(start_data["start_offset"])
    end_offset = int(start_data["end_offset"])
    print(f"  Chunked upload started (video {video_id}, {file_size / 1024 / 1024:.0f} MB)")

    # Phase 2: Transfer chunks
    with open(file_path, "rb") as f:
        while start_offset < file_size:
            f.seek(start_offset)
            chunk = f.read(end_offset - start_offset)
            chunk_resp = _meta_request(
                "POST", url, access_token=token,
                data={
                    "access_token": token,
                    "upload_phase": "transfer",
                    "upload_session_id": session_id,
                    "start_offset": start_offset,
                },
                files={"video_file_chunk": (file_name, chunk, "application/octet-stream")},
            )
            start_offset = int(chunk_resp["start_offset"])
            end_offset = int(chunk_resp["end_offset"])

    # Phase 3: Finish
    finish_data = _meta_request(
        "POST", url, access_token=token,
        data={
            "access_token": token,
            "upload_phase": "finish",
            "upload_session_id": session_id,
            "title": file_name,
        },
    )
    # video_id comes from the start phase; finish just confirms success
    vid = finish_data.get("video_id") or finish_data.get("id") or video_id
    if not vid:
        raise MetaApiError(f"No video ID from chunked upload: start={start_data}, finish={finish_data}")
    return str(vid)


def upload_video(config: dict, file_path: str, poll_interval: int = 5,
                 max_wait: int = 300) -> str:
    """Upload a video to Meta. Returns video_id.

    Uses chunked upload for files > 50 MB, single-request otherwise.
    Video upload is async — this function polls until processing is complete.
    """
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/advideos"
    file_size = os.path.getsize(file_path)

    if file_size > CHUNKED_UPLOAD_THRESHOLD:
        video_id = _upload_video_chunked(config, file_path)
    else:
        try:
            with open(file_path, "rb") as f:
                data = _meta_request(
                    "POST", url,
                    access_token=config["fb_access_token"],
                    data={"access_token": config["fb_access_token"]},
                    files={"source": f},
                )
            video_id = data.get("id")
            if not video_id:
                raise MetaApiError(f"No video ID returned: {data}")
        except MetaApiError as e:
            if e.code == 413:
                print(f"  Single upload rejected (413), retrying with chunked upload...")
                video_id = _upload_video_chunked(config, file_path)
            else:
                raise

    print(f"  Uploaded video: {file_path} (ID: {video_id}), waiting for processing...")

    # Poll for video processing status
    elapsed = 0
    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        status_resp = _meta_request(
            "GET", f"{BASE_URL}/{video_id}",
            access_token=config["fb_access_token"],
            params={
                "access_token": config["fb_access_token"],
                "fields": "status",
            },
        )
        status = status_resp.get("status", {})
        processing_phase = status.get("processing_phase", {})
        phase = processing_phase.get("status", "unknown") if isinstance(processing_phase, dict) else str(processing_phase)

        if phase == "complete" or status.get("video_status") == "ready":
            print(f"  Video ready (ID: {video_id})")
            return video_id

        if phase in ("error", "failed"):
            raise MetaApiError(f"Video processing failed: {status}")

    # If we get here, return the video_id anyway — Meta may still be processing
    # but the video can often be used in ads before processing fully completes
    print(f"  Video still processing after {max_wait}s, proceeding with ID: {video_id}")
    return video_id


def get_video_thumbnail(access_token: str, video_id: str) -> str:
    """Get the auto-generated thumbnail URL for a video."""
    url = f"{BASE_URL}/{video_id}/thumbnails"
    data = _meta_request(
        "GET", url,
        access_token=access_token,
        params={"access_token": access_token, "fields": "uri"},
    )
    thumbs = data.get("data", [])
    if thumbs:
        return thumbs[0].get("uri", "")
    return ""


# ─── Ad Creative ──────────────────────────────────────────────────────────────

def _resolve_instagram_user_id(config: dict) -> str:
    """Get the Instagram user ID, auto-fetching from the page if not in config.

    Meta requires instagram_user_id for creatives that run on Instagram.
    Tries multiple methods:
    1. Config value (fb_ads_config.json)
    2. Page's instagram_business_account field
    3. Page's connected_instagram_account field
    4. Page's /instagram_accounts edge
    """
    # If IG was explicitly stripped by self-healing, don't re-resolve
    if config.get("_ig_stripped"):
        return ""

    ig_id = config.get("instagram_user_id", "")
    if ig_id:
        return ig_id

    page_id = config.get("fb_page_id", "")
    if not page_id:
        return ""

    access_token = config["fb_access_token"]

    # Method 1: instagram_business_account + connected_instagram_account
    try:
        data = _meta_request(
            "GET", f"{BASE_URL}/{page_id}",
            access_token=access_token,
            params={
                "access_token": access_token,
                "fields": "instagram_business_account,connected_instagram_account",
            },
        )
        for field in ("instagram_business_account", "connected_instagram_account"):
            ig_account = data.get(field, {})
            ig_id = ig_account.get("id", "") if isinstance(ig_account, dict) else ""
            if ig_id:
                print(f"  Auto-resolved Instagram user ID from page ({field}): {ig_id}")
                config["instagram_user_id"] = ig_id
                return ig_id
    except Exception as e:
        print(f"  Warning: Could not fetch Instagram account from page fields: {e}")

    # Method 2: /instagram_accounts edge
    try:
        data = _meta_request(
            "GET", f"{BASE_URL}/{page_id}/instagram_accounts",
            access_token=access_token,
            params={"access_token": access_token, "fields": "id,username"},
        )
        accounts = data.get("data", [])
        if accounts:
            ig_id = accounts[0].get("id", "")
            if ig_id:
                print(f"  Auto-resolved Instagram user ID from page edge: {ig_id} ({accounts[0].get('username', '')})")
                config["instagram_user_id"] = ig_id
                return ig_id
    except Exception as e:
        print(f"  Warning: Could not fetch Instagram accounts from page edge: {e}")

    print(f"  No Instagram account found for page {page_id}")
    return ""


def _post_creative(url: str, payload: dict, access_token: str, config: dict = None) -> dict:
    """Post an ad creative, auto-retrying without instagram_user_id on Error 200.

    If instagram_user_id is in the payload and causes a permissions error,
    strip it and retry so ads run on Facebook-only placements.
    """
    try:
        return _meta_request("POST", url, access_token=access_token, data=payload)
    except MetaApiError as e:
        if e.code != 200:
            raise
        # Strip instagram_user_id from object_story_spec and retry
        oss_raw = payload.get("object_story_spec")
        if not oss_raw:
            raise
        oss = json.loads(oss_raw)
        if "instagram_user_id" not in oss:
            raise
        ig_id = oss.pop("instagram_user_id")
        print(f"  ⚠ Instagram user {ig_id} not authorised for this page — "
              f"retrying without Instagram placements")
        payload["object_story_spec"] = json.dumps(oss)
        return _meta_request("POST", url, access_token=access_token, data=payload)


def _has_multiple_options(headline, primary_text, description) -> bool:
    """Check if any text field has multiple options (is a list)."""
    return (isinstance(headline, list) or isinstance(primary_text, list)
            or isinstance(description, list))


def _to_list(value) -> list[str]:
    """Ensure a value is a list (wrap single strings)."""
    if isinstance(value, list):
        return value
    if value:
        return [value]
    return []


def create_ad_creative(config: dict, name: str, media_type: str, media_ref: str,
                       headline, primary_text, description,
                       destination_url: str, cta: str,
                       additional_media_refs: list[dict] | None = None,
                       url_tags: str = "") -> str:
    """Create an ad creative. Returns creative_id.

    media_type: "image" or "video"
    media_ref: image_hash (for images) or video_id (for videos)
    headline/primary_text/description: str or list[str].
        When any field is a list, uses asset_feed_spec (Flexible Ads)
        so Meta tests all combinations automatically.
    """
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/adcreatives"

    # Normalize CTA
    cta_upper = cta.upper().replace(" ", "_") if cta else "LEARN_MORE"
    if cta_upper not in VALID_CTAS:
        print(f"  Warning: CTA '{cta_upper}' may not be valid, using anyway")

    page_id = config["fb_page_id"]
    use_flexible = _has_multiple_options(headline, primary_text, description)

    # Multi-format (multiple images/videos) always requires asset_feed_spec
    if additional_media_refs:
        use_flexible = True

    if use_flexible:
        # ── Flexible Ads (asset_feed_spec) ──
        # Multiple text options → Meta tests combinations
        headlines = _to_list(headline)
        bodies = _to_list(primary_text)
        descriptions = _to_list(description)

        print(f"    Using Flexible Ads: {len(headlines)} headlines, {len(bodies)} bodies, {len(descriptions)} descriptions")

        asset_feed_spec = {
            "titles": [{"text": h} for h in headlines],
            "bodies": [{"text": b} for b in bodies],
            "link_urls": [{"website_url": destination_url}],
            "call_to_action_types": [cta_upper],
        }

        if descriptions:
            asset_feed_spec["descriptions"] = [{"text": d} for d in descriptions]

        if additional_media_refs:
            # Multi-format: multiple images/videos for different placements
            if media_type == "image":
                images_list = [{"hash": media_ref}]
                for extra in additional_media_refs:
                    if extra["type"] == "image":
                        images_list.append({"hash": extra["ref"]})
                asset_feed_spec["images"] = images_list
                asset_feed_spec["ad_formats"] = ["SINGLE_IMAGE"]
            elif media_type == "video":
                videos_list = [{"video_id": media_ref}]
                thumb = get_video_thumbnail(config["fb_access_token"], media_ref)
                if thumb:
                    videos_list[0]["thumbnail_url"] = thumb
                for extra in additional_media_refs:
                    if extra["type"] == "video":
                        entry = {"video_id": extra["ref"]}
                        t = get_video_thumbnail(config["fb_access_token"], extra["ref"])
                        if t:
                            entry["thumbnail_url"] = t
                        videos_list.append(entry)
                asset_feed_spec["videos"] = videos_list
                asset_feed_spec["ad_formats"] = ["SINGLE_VIDEO"]
        elif media_type == "image":
            asset_feed_spec["images"] = [{"hash": media_ref}]
            asset_feed_spec["ad_formats"] = ["SINGLE_IMAGE"]
        elif media_type == "video":
            thumb_url = get_video_thumbnail(config["fb_access_token"], media_ref)
            video_entry = {"video_id": media_ref}
            if thumb_url:
                video_entry["thumbnail_url"] = thumb_url
            asset_feed_spec["videos"] = [video_entry]
            asset_feed_spec["ad_formats"] = ["SINGLE_VIDEO"]
        else:
            raise ValueError(f"Unknown media_type: {media_type}")

        # Instagram actor
        ad_format_page = {"page_id": page_id}
        if config.get("instagram_user_id"):
            ad_format_page["instagram_user_id"] = config["instagram_user_id"]

        payload = {
            "name": name,
            "asset_feed_spec": json.dumps(asset_feed_spec),
            "object_story_spec": json.dumps(ad_format_page),
            "access_token": config["fb_access_token"],
        }
        if url_tags:
            payload["url_tags"] = url_tags

    else:
        # ── Standard single-option creative (object_story_spec) ──
        h = headline if isinstance(headline, str) else (headline[0] if headline else "")
        pt = primary_text if isinstance(primary_text, str) else (primary_text[0] if primary_text else "")
        desc = description if isinstance(description, str) else (description[0] if description else "")

        if media_type == "image":
            object_story_spec = {
                "page_id": page_id,
                "link_data": {
                    "message": pt,
                    "link": destination_url,
                    "name": h,
                    "description": desc,
                    "image_hash": media_ref,
                    "call_to_action": {
                        "type": cta_upper,
                        "value": {"link": destination_url},
                    },
                },
            }
        elif media_type == "video":
            thumb_url = get_video_thumbnail(config["fb_access_token"], media_ref)
            video_data = {
                "video_id": media_ref,
                "message": pt,
                "title": h,
                "link_description": desc,
                "call_to_action": {
                    "type": cta_upper,
                    "value": {"link": destination_url},
                },
            }
            if thumb_url:
                video_data["image_url"] = thumb_url
            object_story_spec = {
                "page_id": page_id,
                "video_data": video_data,
            }
        else:
            raise ValueError(f"Unknown media_type: {media_type}")

        if config.get("instagram_user_id"):
            object_story_spec["instagram_user_id"] = config["instagram_user_id"]

        payload = {
            "name": name,
            "object_story_spec": json.dumps(object_story_spec),
            "access_token": config["fb_access_token"],
        }
        if url_tags:
            payload["url_tags"] = url_tags

    data = _post_creative(url, payload, access_token=config["fb_access_token"], config=config)
    creative_id = data.get("id")
    if not creative_id:
        raise MetaApiError(f"No creative ID returned: {data}")
    mode = "flexible" if use_flexible else "standard"
    print(f"  Created creative ({mode}): {name} (ID: {creative_id})")
    return creative_id


def create_pac_creative(config: dict, name: str, media_refs: list[dict],
                        headline: str, primary_text: str, description: str,
                        destination_url: str, cta: str, url_tags: str = "") -> str:
    """Create a Placement Asset Customization creative.

    Assigns different image/video sizes to different placements (Feed vs Stories/Reels).
    Works on standard (non-dynamic) ad sets, so multiple ads per ad set are OK.

    Args:
        media_refs: list of {"type": "image"|"video", "ref": image_hash or video_id}
            - [0]: Feed placements (1:1 or 4:5)
            - [1]: Stories/Reels placements (9:16)
            - [2+]: Additional (mapped to remaining placements)
    Returns:
        creative_id
    """
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/adcreatives"
    page_id = config["fb_page_id"]
    cta_upper = cta.upper().replace(" ", "_") if cta else "LEARN_MORE"

    # Use first headline/text only (PAC doesn't support multiple texts)
    h = headline[0] if isinstance(headline, list) else headline
    pt = primary_text[0] if isinstance(primary_text, list) else primary_text
    desc = description[0] if isinstance(description, list) else description if description else ""

    # Determine if all media are images or videos
    media_type = media_refs[0]["type"]

    # Deduplicate media refs — Meta rejects duplicate asset values.
    # When two slots have the same ref (e.g., user uploaded same file twice),
    # merge their labels onto one entry and track which labels map to which ref.
    labels = ["FEED", "VERTICAL", "OTHER"]
    seen_refs = {}  # ref → index in media_entries
    media_entries = []
    ref_to_label = {}  # ref → list of labels assigned to this ref

    for i, media in enumerate(media_refs):
        label = labels[i] if i < len(labels) else f"MEDIA_{i}"
        ref = media["ref"]

        if ref in seen_refs:
            # Duplicate ref — add this label to the existing entry
            idx = seen_refs[ref]
            media_entries[idx]["adlabels"].append({"name": label})
            ref_to_label[ref].append(label)
            print(f"    Dedup: {label} shares asset with {ref_to_label[ref][0]}")
        else:
            entry = {"adlabels": [{"name": label}]}
            if media["type"] == "image":
                entry["hash"] = ref
            else:
                entry["video_id"] = ref
                thumb = get_video_thumbnail(config["fb_access_token"], ref)
                if thumb:
                    entry["thumbnail_url"] = thumb
            seen_refs[ref] = len(media_entries)
            ref_to_label[ref] = [label]
            media_entries.append(entry)

    media_key = "images" if media_type == "image" else "videos"

    # Build customization rules mapping labels to placements
    # Only include Instagram placements when an IG account is configured
    # NOTE: v22+ deprecated Segment Asset Customization — no geo_locations in rules
    has_ig = bool(config.get("instagram_user_id"))

    # Combined FB+IG per rule — avoids "duplicate values" error from split rules
    platforms = ["facebook", "instagram"] if has_ig else ["facebook"]

    # Feed placements
    feed_spec = {
        "publisher_platforms": platforms,
        "facebook_positions": ["feed", "marketplace", "search", "video_feeds"],
    }
    if has_ig:
        feed_spec["instagram_positions"] = ["stream", "profile_feed", "explore", "explore_home"]

    customization_rules = [
        {"customization_spec": feed_spec, f"{media_type}_label": {"name": "FEED"}},
    ]

    # Vertical placements: Stories/Reels
    if len(media_refs) >= 2:
        vertical_spec = {
            "publisher_platforms": platforms,
            "facebook_positions": ["story", "facebook_reels"],
        }
        if has_ig:
            vertical_spec["instagram_positions"] = ["story", "reels"]
        customization_rules.append(
            {"customization_spec": vertical_spec, f"{media_type}_label": {"name": "VERTICAL"}}
        )

    # Right hand column (Facebook only)
    rhc_label = "OTHER" if len(media_refs) >= 3 else "FEED"
    other_spec = {
        "publisher_platforms": ["facebook"],
        "facebook_positions": ["right_hand_column"],
    }
    customization_rules.append(
        {"customization_spec": other_spec, f"{media_type}_label": {"name": rhc_label}}
    )

    ad_format = "SINGLE_IMAGE" if media_type == "image" else "SINGLE_VIDEO"

    asset_feed_spec = {
        media_key: media_entries,
        "ad_formats": [ad_format],
        "bodies": [{"text": pt}],
        "titles": [{"text": h}],
        "link_urls": [{"website_url": destination_url}],
        "call_to_action_types": [cta_upper],
        "asset_customization_rules": customization_rules,
    }

    if desc:
        asset_feed_spec["descriptions"] = [{"text": desc}]

    ad_format_page = {"page_id": page_id}
    if has_ig:
        ad_format_page["instagram_user_id"] = config["instagram_user_id"]

    print(f"  PAC creative: {len(media_refs)} placements, {len(customization_rules)} rules, IG={has_ig}")

    payload = {
        "name": name,
        "asset_feed_spec": json.dumps(asset_feed_spec),
        "object_story_spec": json.dumps(ad_format_page),
        "access_token": config["fb_access_token"],
    }
    if url_tags:
        payload["url_tags"] = url_tags

    data = _post_creative(url, payload, access_token=config["fb_access_token"], config=config)
    creative_id = data.get("id")
    if not creative_id:
        raise MetaApiError(f"No creative ID returned for PAC: {data}")
    print(f"  Created PAC creative: {name} (ID: {creative_id}, {len(media_refs)} placements)")
    return creative_id


def create_carousel_creative(config: dict, name: str, media_refs: list[dict],
                              headline: str, primary_text: str, description: str,
                              destination_url: str, cta: str, url_tags: str = "") -> str:
    """Create a carousel ad creative with multiple cards.

    Args:
        media_refs: list of {"type": "image"|"video", "ref": image_hash or video_id}
        headline: shared headline for all cards
        primary_text: message shown above the carousel
        description: link description for cards
    Returns:
        creative_id
    """
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/adcreatives"

    cta_upper = cta.upper().replace(" ", "_") if cta else "LEARN_MORE"
    page_id = config["fb_page_id"]

    child_attachments = []
    for media in media_refs:
        card = {
            "link": destination_url,
            "name": headline,
            "description": description or "",
            "call_to_action": {"type": cta_upper, "value": {"link": destination_url}},
        }
        if media["type"] == "image":
            card["image_hash"] = media["ref"]
        else:
            card["video_id"] = media["ref"]
            thumb_url = get_video_thumbnail(config["fb_access_token"], media["ref"])
            if thumb_url:
                card["picture"] = thumb_url
        child_attachments.append(card)

    print(f"  Carousel: {len(child_attachments)} cards (limit: 10)")

    object_story_spec = {
        "page_id": page_id,
        "link_data": {
            "message": primary_text or "",
            "link": destination_url,
            "child_attachments": child_attachments,
        },
    }

    if config.get("instagram_user_id"):
        object_story_spec["instagram_user_id"] = config["instagram_user_id"]

    payload = {
        "name": name,
        "object_story_spec": json.dumps(object_story_spec),
        "access_token": config["fb_access_token"],
    }
    if url_tags:
        payload["url_tags"] = url_tags

    data = _post_creative(url, payload, access_token=config["fb_access_token"], config=config)
    creative_id = data.get("id")
    if not creative_id:
        raise MetaApiError(f"No creative ID returned for carousel: {data}")
    print(f"  Created carousel creative: {name} (ID: {creative_id}, {len(child_attachments)} cards)")
    return creative_id


# ─── Ads ──────────────────────────────────────────────────────────────────────

def create_ad(config: dict, name: str, adset_id: str, creative_id: str,
              status: str = "PAUSED") -> str:
    """Create an ad. Returns ad_id.

    Handles the case where a 500 error already created the ad (phantom success).
    If we get error 1885553 (dynamic ad set already has an ad), look it up instead.
    """
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/ads"

    payload = {
        "name": name,
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": creative_id}),
        "status": status,
        "access_token": config["fb_access_token"],
    }

    try:
        data = _meta_request("POST", url, access_token=config["fb_access_token"], data=payload)
    except MetaApiError as e:
        if e.subcode == 1885553:
            # Dynamic ad set already has an ad (likely from phantom 500 success)
            print(f"  Ad set already has an ad (phantom 500), looking it up...")
            existing = _meta_request(
                "GET", f"{BASE_URL}/{adset_id}/ads",
                access_token=config["fb_access_token"],
                params={"access_token": config["fb_access_token"], "fields": "id,name", "limit": 1},
            )
            ads = existing.get("data", [])
            if ads:
                ad_id = ads[0]["id"]
                print(f"  Found existing ad: {ads[0].get('name', '')} (ID: {ad_id})")
                return ad_id
        raise
    ad_id = data.get("id")
    if not ad_id:
        raise MetaApiError(f"No ad ID returned: {data}")
    print(f"  Created ad: {name} (ID: {ad_id})")
    return ad_id


# ─── Status Updates ──────────────────────────────────────────────────────────

def update_status(config: dict, object_id: str, status: str) -> bool:
    """Update the status of a campaign, ad set, or ad."""
    url = f"{BASE_URL}/{object_id}"
    data = _meta_request(
        "POST", url,
        access_token=config["fb_access_token"],
        data={
            "status": status,
            "access_token": config["fb_access_token"],
        },
    )
    return data.get("success", False)


# ─── Interest Search ──────────────────────────────────────────────────────────

def search_interests(access_token: str, query: str, limit: int = 25) -> list[dict]:
    """Search Meta's targeting interest database.

    Returns list of {id, name, audience_size_lower_bound, audience_size_upper_bound, path}.
    """
    url = f"{BASE_URL}/search"
    data = _meta_request(
        "GET", url,
        access_token=access_token,
        params={
            "access_token": access_token,
            "type": "adinterest",
            "q": query,
            "limit": limit,
        },
    )
    results = []
    for item in data.get("data", []):
        results.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "audience_size_lower_bound": item.get("audience_size_lower_bound", 0),
            "audience_size_upper_bound": item.get("audience_size_upper_bound", 0),
            "path": item.get("path", []),
        })
    return results


# ─── Custom Audiences ────────────────────────────────────────────────────────

def get_custom_audiences(config: dict) -> list[dict]:
    """List custom audiences in the ad account (including lookalikes)."""
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/customaudiences"

    data = _meta_request(
        "GET", url,
        access_token=config["fb_access_token"],
        params={
            "access_token": config["fb_access_token"],
            "fields": "id,name,subtype,approximate_count_lower_bound,approximate_count_upper_bound",
            "limit": 200,
        },
    )
    return data.get("data", [])


# ─── Ad Sets in Campaign ─────────────────────────────────────────────────────

def get_ads_in_campaign(config: dict, campaign_id: str) -> list[dict]:
    """Get all ads in a campaign (for activation)."""
    url = f"{BASE_URL}/{campaign_id}/ads"
    data = _meta_request(
        "GET", url,
        access_token=config["fb_access_token"],
        params={
            "access_token": config["fb_access_token"],
            "fields": "id,name,status,adset_id",
            "limit": 200,
        },
    )
    return data.get("data", [])


# ─── Cleanup / Rollback ─────────────────────────────────────────────────────


def delete_object(config: dict, object_id: str) -> bool:
    """Delete a Meta Ads object (campaign, ad set, or ad) by ID.

    Used for rollback when a launch fails partway through.
    Note: Deleting a campaign also deletes its child ad sets and ads.
    """
    url = f"{BASE_URL}/{object_id}"
    _meta_request(
        "DELETE", url,
        access_token=config["fb_access_token"],
        params={"access_token": config["fb_access_token"]},
        retries=2,
    )
    return True
