#!/usr/bin/env python3
"""Dump full LAL_STACK config so we match it when creating the new broad ad set."""
import json, sys
from pathlib import Path
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from config_loader import load_all
from meta_api import _meta_request, BASE_URL

config = load_all("pp_primal_path")
token = config["fb_access_token"]
for adset_id in ["120238521835520227"]:
    data = _meta_request("GET", f"{BASE_URL}/{adset_id}", access_token=token, params={
        "access_token": token,
        "fields": "id,name,daily_budget,optimization_goal,billing_event,bid_strategy,destination_type,attribution_spec,promoted_object,targeting,is_dynamic_creative",
    })
    print(json.dumps(data, indent=2))
