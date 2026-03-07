#!/usr/bin/env python3
"""
Meta Marketing API operations for FB Ads Launcher.
Handles campaign, ad set, ad creative, and ad creation via the Graph API.

All objects are created in PAUSED status by default.
Uses requests directly (no facebook_business SDK dependency).
"""

from __future__ import annotations

import json
import time

import requests

API_VERSION = "v21.0"
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

        error_msg = error_data.get("message", resp.text[:300])
        error_code = error_data.get("code", resp.status_code)
        error_subcode = error_data.get("error_subcode", 0)

        # Only retry on server errors
        if resp.status_code in (500, 502, 503) and attempt < retries - 1:
            wait = 2 ** attempt
            print(f"  Meta API {resp.status_code}, retrying in {wait}s...")
            time.sleep(wait)
            continue

        raise MetaApiError(error_msg, error_code, error_subcode)

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


def create_adset(config: dict, campaign_id: str, name: str,
                 targeting: dict, daily_budget_cents: int,
                 optimization_goal: str = None, billing_event: str = None,
                 destination_url: str = "", status: str = "PAUSED",
                 is_dynamic_creative: bool = False,
                 attribution_window: str = "",
                 start_time: str = "") -> str:
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

    payload = {
        "name": name,
        "campaign_id": campaign_id,
        "daily_budget": str(daily_budget_cents),
        "optimization_goal": opt_goal,
        "billing_event": bill_event,
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "targeting": json.dumps(targeting),
        "status": status,
        "access_token": config["fb_access_token"],
    }

    # Attribution window optimization (e.g., "7d_click_1d_view", "7d_click", "1d_click")
    if attribution_window:
        attribution_spec = _build_attribution_spec(attribution_window)
        if attribution_spec:
            payload["attribution_spec"] = json.dumps(attribution_spec)

    if is_dynamic_creative:
        payload["is_dynamic_creative"] = "true"

    if start_time:
        payload["start_time"] = start_time

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


def upload_video(config: dict, file_path: str, poll_interval: int = 5,
                 max_wait: int = 300) -> str:
    """Upload a video to Meta. Returns video_id.

    Video upload is async — this function polls until processing is complete.
    """
    ad_account_id = config["fb_ad_account_id"]
    url = f"{BASE_URL}/act_{ad_account_id}/advideos"

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

    data = _meta_request("POST", url, access_token=config["fb_access_token"], data=payload)
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
    ad_format = "SINGLE_IMAGE" if media_type == "image" else "SINGLE_VIDEO"

    # Build media entries with labels
    media_entries = []
    labels = ["FEED", "VERTICAL", "OTHER"]
    for i, media in enumerate(media_refs):
        label = labels[i] if i < len(labels) else f"MEDIA_{i}"
        entry = {"adlabels": [{"name": label}]}
        if media["type"] == "image":
            entry["hash"] = media["ref"]
        else:
            entry["video_id"] = media["ref"]
            thumb = get_video_thumbnail(config["fb_access_token"], media["ref"])
            if thumb:
                entry["thumbnail_url"] = thumb
        media_entries.append(entry)

    media_key = "images" if media_type == "image" else "videos"

    # Build customization rules mapping labels to placements
    customization_rules = [
        {
            "customization_spec": {
                "publisher_platforms": ["facebook", "instagram"],
                "facebook_positions": ["feed", "marketplace", "search", "video_feeds"],
                "instagram_positions": ["stream", "profile_feed", "explore", "explore_home"],
            },
            f"{media_type}_label": {"name": "FEED"},
        },
    ]
    if len(media_refs) >= 2:
        customization_rules.append({
            "customization_spec": {
                "publisher_platforms": ["facebook", "instagram"],
                "facebook_positions": ["story", "facebook_reels"],
                "instagram_positions": ["story", "reels"],
            },
            f"{media_type}_label": {"name": "VERTICAL"},
        })
    if len(media_refs) >= 3:
        customization_rules.append({
            "customization_spec": {
                "publisher_platforms": ["facebook", "instagram"],
                "facebook_positions": ["right_hand_column", "instant_article"],
                "instagram_positions": [],
            },
            f"{media_type}_label": {"name": "OTHER"},
        })

    asset_feed_spec = {
        "ad_formats": [ad_format],
        media_key: media_entries,
        "bodies": [{"text": pt}],
        "titles": [{"text": h}],
        "link_urls": [{"website_url": destination_url}],
        "call_to_action_types": [cta_upper],
        "asset_customization_rules": customization_rules,
    }

    if desc:
        asset_feed_spec["descriptions"] = [{"text": desc}]

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

    data = _meta_request("POST", url, access_token=config["fb_access_token"], data=payload)
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

    object_story_spec = {
        "page_id": page_id,
        "link_data": {
            "message": primary_text,
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

    data = _meta_request("POST", url, access_token=config["fb_access_token"], data=payload)
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
            "fields": "id,name,subtype,approximate_count",
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
