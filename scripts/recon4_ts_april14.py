#!/usr/bin/env python3
"""Pull destination URLs and CTAs from existing HiRise + PowerBug ads."""
import json, sys
from pathlib import Path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from config_loader import load_all
from meta_api import BASE_URL, _meta_request

config = load_all("ts_twelve_south")
token = config["fb_access_token"]

# Most recent HiRise ad + PowerBug winner
targets = {
    "HiRise (03-09-26 most recent)": "6888083496475",
    "PowerBug (01-07 winner)": "6863518870475",
    "PowerBug (04-06 static flex)": "6902283466075",
}

for label, ad_id in targets.items():
    print(f"\n═══ {label}  (ad {ad_id})")
    resp = _meta_request(
        "GET", f"{BASE_URL}/{ad_id}",
        access_token=token,
        params={
            "access_token": token,
            "fields": (
                "creative{object_story_spec{link_data{link,call_to_action},"
                "video_data{call_to_action}},"
                "asset_feed_spec{link_urls,call_to_action_types},"
                "url_tags}"
            ),
        },
    )
    creative = resp.get("creative", {}) or {}
    afs = creative.get("asset_feed_spec") or {}
    oss = creative.get("object_story_spec") or {}
    if afs:
        print(f"  asset_feed_spec.link_urls: {afs.get('link_urls')}")
        print(f"  asset_feed_spec.call_to_action_types: {afs.get('call_to_action_types')}")
    ld = oss.get("link_data") or {}
    vd = oss.get("video_data") or {}
    if ld:
        print(f"  link_data.link: {ld.get('link')}")
        print(f"  link_data.call_to_action: {ld.get('call_to_action')}")
    if vd:
        print(f"  video_data.call_to_action: {vd.get('call_to_action')}")
    print(f"  url_tags: {creative.get('url_tags', '')}")
