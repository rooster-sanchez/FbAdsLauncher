#!/usr/bin/env python3
from __future__ import annotations
"""
ClickUp Reader for FB Ads Launcher
Reads parent task (batch config) and subtasks (individual ads) from ClickUp.

Usage:
    from clickup_reader import get_batch_brief
    brief = get_batch_brief("task_id_here", api_token)
"""

import os
import tempfile
from pathlib import Path

import requests

CLICKUP_BASE = "https://api.clickup.com/api/v2"


def _headers(api_token: str) -> dict:
    return {"Authorization": api_token}


def _get(endpoint: str, api_token: str, params: dict = None) -> dict:
    """Make a GET request to ClickUp API."""
    resp = requests.get(
        f"{CLICKUP_BASE}{endpoint}",
        headers=_headers(api_token),
        params=params or {},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"ClickUp GET {endpoint} failed [{resp.status_code}]: {resp.text[:300]}")
    return resp.json()


def _put(endpoint: str, api_token: str, data: dict) -> dict:
    """Make a PUT request to ClickUp API."""
    resp = requests.put(
        f"{CLICKUP_BASE}{endpoint}",
        headers={**_headers(api_token), "Content-Type": "application/json"},
        json=data,
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"ClickUp PUT {endpoint} failed [{resp.status_code}]: {resp.text[:300]}")
    return resp.json()


def _post(endpoint: str, api_token: str, data: dict) -> dict:
    """Make a POST request to ClickUp API."""
    resp = requests.post(
        f"{CLICKUP_BASE}{endpoint}",
        headers={**_headers(api_token), "Content-Type": "application/json"},
        json=data,
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"ClickUp POST {endpoint} failed [{resp.status_code}]: {resp.text[:300]}")
    return resp.json()


def parse_custom_fields(task: dict) -> dict:
    """Flatten ClickUp's custom_fields array into {field_name_lower: value}.

    Handles different field types (text, number, drop_down, url, etc.).
    When duplicate field names exist (e.g. old text + new dropdown),
    dropdown fields take priority over text fields.
    """
    fields = {}
    field_types = {}  # Track type per key to resolve duplicates
    for cf in task.get("custom_fields", []):
        name = cf.get("name", "").strip().lower().replace(" ", "_")
        field_type = cf.get("type", "")
        value = cf.get("value")

        # If this key already exists and was set by a dropdown, skip text override
        if name in fields and field_types.get(name) == "drop_down" and field_type != "drop_down":
            continue
        # If this key exists from a text field and we now have a dropdown, override
        override = name in fields and field_types.get(name) != "drop_down" and field_type == "drop_down"

        if value is None and not override:
            fields[name] = None
            field_types[name] = field_type
            continue

        if field_type == "drop_down":
            # Value is the option index; get the label
            type_config = cf.get("type_config", {})
            options = type_config.get("options", [])
            if isinstance(value, int) and value < len(options):
                fields[name] = options[value].get("name", "")
            elif isinstance(value, dict):
                fields[name] = value.get("name", str(value))
            elif value is None:
                fields[name] = None
            else:
                fields[name] = str(value)
        elif field_type == "number":
            fields[name] = float(value) if value else 0
        elif field_type in ("short_text", "text", "url", "email"):
            fields[name] = str(value)
        else:
            fields[name] = value

        field_types[name] = field_type

    return fields


def parse_description_fields(description: str) -> dict:
    """Parse ad copy fields from a task's description body.

    Supports flexible formats:
        Headline: The Ultimate Travel Hack
        Primary Text: Your ad copy here...
        Primary copy: Also accepted as primary_text
        Description: Short link description

    Values can be on the same line as the key or on following lines.
    Multi-line values are captured until the next recognized key.
    """
    if not description:
        return {}

    # Map of recognized labels → normalized field name
    key_aliases = {
        "headline": "headline",
        "primary text": "primary_text",
        "primary copy": "primary_text",
        "primary_text": "primary_text",
        "description": "description",
        "link description": "description",
    }

    fields = {}
    current_key = None

    for line in description.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Skip ClickUp attachment preview URLs that leak into descriptions
        if "clickup-attachments.com/" in stripped:
            continue

        # Check if line starts with a recognized key label
        matched = False
        lower = stripped.lower()
        for alias, norm_key in key_aliases.items():
            prefix = alias + ":"
            if lower.startswith(prefix):
                value = stripped[len(prefix):].strip()
                if value:
                    fields[norm_key] = value
                else:
                    # Value is on the next line(s)
                    fields[norm_key] = ""
                current_key = norm_key
                matched = True
                break

        if not matched and current_key:
            # Continuation line — append to current field
            if fields[current_key]:
                fields[current_key] += "\n" + stripped
            else:
                fields[current_key] = stripped

    # Clean up and split multi-line headline/description into lists
    result = {}
    for k, v in fields.items():
        v = v.strip()
        if not v:
            continue
        if k in ("headline", "description"):
            # Multiple lines = multiple options for Meta's Flexible Ads
            lines = [line.strip() for line in v.split("\n") if line.strip()]
            result[k] = lines if len(lines) > 1 else lines[0]
        else:
            result[k] = v
    return result


def get_task(task_id: str, api_token: str) -> dict:
    """Get a single ClickUp task with custom fields."""
    task = _get(f"/task/{task_id}", api_token, params={"include_subtasks": "true"})
    return task


def get_subtasks(task_id: str, api_token: str) -> list[dict]:
    """Get subtasks of a parent task.

    ClickUp returns subtasks when include_subtasks=true on the parent,
    but we may also need to query them separately for full custom field data.
    """
    parent = get_task(task_id, api_token)
    subtask_ids = []

    # Check if subtasks are embedded
    for sub in parent.get("subtasks", []):
        sub_id = sub if isinstance(sub, str) else sub.get("id", "")
        if sub_id:
            subtask_ids.append(sub_id)

    # Fetch each subtask fully to get custom fields and attachments
    subtasks = []
    for sub_id in subtask_ids:
        sub_task = _get(f"/task/{sub_id}", api_token)
        subtasks.append(sub_task)

    return subtasks


def get_task_attachments(task_id: str, api_token: str) -> list[dict]:
    """Get attachments for a task. Returns list of {name, url, type}."""
    # ClickUp doesn't have a dedicated attachments endpoint;
    # attachments are in the task's 'attachments' field
    task = _get(f"/task/{task_id}", api_token)
    attachments = task.get("attachments", [])
    return [
        {
            "name": att.get("title", att.get("name", "unknown")),
            "url": att.get("url", ""),
            "type": att.get("extension", att.get("type", "")),
        }
        for att in attachments
    ]


def download_attachment(url: str, save_dir: str, filename: str, api_token: str) -> str:
    """Download a file from a ClickUp attachment URL.

    Returns the local file path.
    """
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)

    resp = requests.get(
        url,
        headers=_headers(api_token),
        timeout=120,
        stream=True,
    )
    if not resp.ok:
        raise RuntimeError(f"Failed to download attachment [{resp.status_code}]: {url[:100]}")

    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    return save_path


def update_task_status(task_id: str, status: str, api_token: str) -> bool:
    """Update a task's status. Returns True on success."""
    try:
        _put(f"/task/{task_id}", api_token, {"status": status})
        return True
    except RuntimeError as e:
        print(f"Warning: Failed to update ClickUp status: {e}")
        return False


def add_task_comment(task_id: str, comment_text: str, api_token: str) -> bool:
    """Post a comment on a ClickUp task. Returns True on success."""
    try:
        _post(f"/task/{task_id}/comment", api_token, {"comment_text": comment_text})
        return True
    except RuntimeError as e:
        print(f"Warning: Failed to post ClickUp comment: {e}")
        return False


def get_batch_brief(task_id: str, api_token: str) -> dict:
    """Read a complete batch brief from a ClickUp parent task + subtasks.

    Returns:
        {
            "task_id": str,
            "task_name": str,
            "batch_fields": {field_name: value, ...},
            "ads": [
                {
                    "task_id": str,
                    "ad_name": str,
                    "fields": {headline: ..., primary_text: ..., description: ...},
                    "attachments": [{name, url, type}, ...],
                },
                ...
            ]
        }
    """
    parent = get_task(task_id, api_token)
    batch_fields = parse_custom_fields(parent)

    subtasks = get_subtasks(task_id, api_token)
    ads = []
    for sub in subtasks:
        # Parse ad copy from description body (Headline, Primary Text, Description)
        desc_fields = parse_description_fields(sub.get("description", "") or sub.get("text_content", ""))

        # Fall back to custom fields if description doesn't have the data
        custom_fields = parse_custom_fields(sub)
        merged_fields = {**custom_fields, **desc_fields}  # description wins

        sub_attachments = sub.get("attachments", [])

        ads.append({
            "task_id": sub.get("id", ""),
            "ad_name": sub.get("name", ""),
            "fields": merged_fields,
            "attachments": [
                {
                    "name": att.get("title", att.get("name", "unknown")),
                    "url": att.get("url", ""),
                    "type": att.get("extension", att.get("type", "")),
                }
                for att in sub_attachments
            ],
        })

    return {
        "task_id": task_id,
        "task_name": parent.get("name", ""),
        "task_url": parent.get("url", ""),
        "batch_fields": batch_fields,
        "ads": ads,
    }
