#!/usr/bin/env python3
from __future__ import annotations
"""
Targeting builder for FB Ads Launcher.
Constructs Meta targeting specs for broad, lookalike, and interest targeting.

Usage:
    from targeting import build_targeting_spec
    spec = build_targeting_spec(config, batch_fields)
"""

from meta_api import search_interests

# Gender mapping: ClickUp dropdown value → Meta API value
GENDER_MAP = {
    "all": [0],
    "women": [2],
    "female": [2],
    "men": [1],
    "male": [1],
}


def _parse_age_range(age_str: str) -> tuple[int, int]:
    """Parse age range string like '25-45' into (min, max).

    Defaults to 18-65 if parsing fails.
    """
    if not age_str:
        return 18, 65

    age_str = str(age_str).strip()
    try:
        if "-" in age_str:
            parts = age_str.split("-")
            return int(parts[0].strip()), int(parts[1].strip())
        if "to" in age_str.lower():
            parts = age_str.lower().split("to")
            return int(parts[0].strip()), int(parts[1].strip())
        # Single number — use as min, default max to 65
        return int(age_str), 65
    except (ValueError, IndexError):
        print(f"  Warning: Could not parse age range '{age_str}', using 18-65")
        return 18, 65


def _build_base_targeting(config: dict, batch_fields: dict) -> dict:
    """Build the base targeting spec (geo + age + gender).

    These fields apply to all targeting types.
    """
    age_min, age_max = _parse_age_range(batch_fields.get("age_range", ""))

    gender_raw = str(batch_fields.get("gender", "all")).strip().lower()
    genders = GENDER_MAP.get(gender_raw, [0])

    targeting = {
        "geo_locations": config.get("default_geo_locations", {"countries": ["US"]}),
        "age_min": age_min,
        "age_max": age_max,
    }

    # Only add genders if not "all" (0 means all, but omitting is cleaner)
    if genders != [0]:
        targeting["genders"] = genders

    # Exclusion audiences are passed separately via excluded_custom_audiences
    # (Meta deprecated targeting.exclusions.custom_audiences in API v21.0+)
    # See meta_api.create_adset() for how they're sent as a top-level param.

    return targeting


def _build_broad_targeting(config: dict, batch_fields: dict) -> dict:
    """Broad targeting: geo + age + gender only. No interests or audiences."""
    return _build_base_targeting(config, batch_fields)


def _build_lookalike_targeting(config: dict, batch_fields: dict) -> dict:
    """Lookalike targeting: base + custom audience IDs.

    Reads audience IDs from the 'custom_audience_ids' batch field.
    Accepts either a list of IDs (from multi-select dropdown) or a
    comma-separated string (legacy text field).
    """
    targeting = _build_base_targeting(config, batch_fields)

    audience_ids_raw = batch_fields.get("custom_audience_ids", "")
    if not audience_ids_raw:
        print("  Warning: Lookalike targeting selected but no custom_audience_ids provided")
        print("  Select audiences from the '10. Custom Audiences' dropdown")
        return targeting

    # Accept list (from multi-select) or comma-separated string (legacy text field)
    if isinstance(audience_ids_raw, list):
        audience_ids = [aid.strip() for aid in audience_ids_raw if aid.strip()]
    else:
        audience_ids = [
            aid.strip() for aid in str(audience_ids_raw).split(",")
            if aid.strip()
        ]

    if audience_ids:
        targeting["custom_audiences"] = [{"id": aid} for aid in audience_ids]
        print(f"  Lookalike targeting: {len(audience_ids)} audience(s)")

    return targeting


def _build_interest_targeting(config: dict, batch_fields: dict) -> dict:
    """Interest targeting: base + interests found via Meta search API.

    Reads keywords from the 'interest_keywords' batch field
    (comma-separated list of search terms).
    """
    targeting = _build_base_targeting(config, batch_fields)

    keywords_raw = batch_fields.get("interest_keywords", "")
    if not keywords_raw:
        print("  Warning: Interest targeting selected but no interest_keywords provided")
        return targeting

    keywords = [kw.strip() for kw in str(keywords_raw).split(",") if kw.strip()]
    interests = search_and_select_interests(
        config["fb_access_token"], keywords, max_per_keyword=3
    )

    if interests:
        targeting["flexible_spec"] = [{"interests": interests}]
        print(f"  Interest targeting: {len(interests)} interest(s) selected")
    else:
        print("  Warning: No interests found for the provided keywords")

    return targeting


def search_and_select_interests(access_token: str, keywords: list[str],
                                max_per_keyword: int = 3) -> list[dict]:
    """Search Meta interest API for each keyword and select top results.

    For each keyword, picks the top N results by audience_size_upper_bound,
    filtering out extremely small (<100K) or extremely large (>500M) audiences.
    Deduplicates across keywords.
    """
    seen_ids = set()
    selected = []

    for keyword in keywords:
        print(f"  Searching interests for: '{keyword}'")
        results = search_interests(access_token, keyword)

        # Filter by reasonable audience size
        filtered = [
            r for r in results
            if r["audience_size_upper_bound"] >= 100_000
            and r["audience_size_upper_bound"] <= 500_000_000
        ]

        # Sort by audience size (descending) and pick top N
        filtered.sort(key=lambda x: x["audience_size_upper_bound"], reverse=True)

        count = 0
        for interest in filtered:
            if interest["id"] in seen_ids:
                continue
            if count >= max_per_keyword:
                break

            seen_ids.add(interest["id"])
            selected.append({"id": interest["id"], "name": interest["name"]})
            size = interest["audience_size_upper_bound"]
            print(f"    + {interest['name']} (audience: {size:,})")
            count += 1

    return selected


def build_targeting_spec(config: dict, batch_fields: dict) -> dict:
    """Build the full targeting spec based on the targeting type.

    targeting_type should be one of: "broad", "lookalikes", "interest"
    """
    targeting_type = str(batch_fields.get("targeting", "broad")).strip().lower()

    if targeting_type == "broad":
        return _build_broad_targeting(config, batch_fields)
    elif targeting_type in ("lookalikes", "lookalike"):
        return _build_lookalike_targeting(config, batch_fields)
    elif targeting_type == "interest":
        return _build_interest_targeting(config, batch_fields)
    else:
        print(f"  Warning: Unknown targeting type '{targeting_type}', defaulting to broad")
        return _build_broad_targeting(config, batch_fields)
