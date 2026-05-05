#!/usr/bin/env python3
"""Google Drive helper — download files/folders by share link.

First run opens a browser for OAuth consent; subsequent runs use the saved
refresh token. Credentials live under .credentials/drive/ (gitignored).

Usage:
    from drive_client import download_folder, download_file, parse_id

    # Download every file in a Drive folder link to a local dir
    paths = download_folder(
        "https://drive.google.com/drive/folders/ABC123?usp=drive_link",
        dest_dir="/Users/luis/Downloads/pp_primal20",
    )

    # Or a single file link
    path = download_file(
        "https://drive.google.com/file/d/XYZ/view?usp=sharing",
        dest_dir="~/Downloads",
    )

CLI:
    python3 scripts/drive_client.py <drive_url> [dest_dir]
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# scripts/foo.py — repo root is parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
CRED_DIR = WORKSPACE_ROOT / ".credentials" / "drive"
CLIENT_SECRET_PATH = CRED_DIR / "client_secret.json"
TOKEN_PATH = CRED_DIR / "token.json"

# Google Workspace mimes and the formats we'll export them as
EXPORT_MAP = {
    "application/vnd.google-apps.document":     ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet":  ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


def _get_service():
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(
            f"Missing OAuth client secret at {CLIENT_SECRET_PATH}.\n"
            "Follow the setup steps in README or README.DRIVE."
        )
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent", open_browser=True)
        TOKEN_PATH.write_text(creds.to_json())
        print(f"  Saved Drive token to {TOKEN_PATH}")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ─── URL / ID parsing ────────────────────────────────────────────────────────

_FILE_RE   = re.compile(r"/file/d/([A-Za-z0-9_-]+)")
_FOLDER_RE = re.compile(r"/folders/([A-Za-z0-9_-]+)")
_OPEN_RE   = re.compile(r"[?&]id=([A-Za-z0-9_-]+)")


def parse_id(url_or_id: str) -> tuple[str, str]:
    """Return (id, kind) where kind is 'file' or 'folder'.

    Accepts: raw IDs, /file/d/..., /folders/..., /open?id=...
    When kind is ambiguous (raw ID / ?id=...), returns 'unknown' — the caller
    should probe the Drive API.
    """
    s = url_or_id.strip()
    if m := _FOLDER_RE.search(s):
        return m.group(1), "folder"
    if m := _FILE_RE.search(s):
        return m.group(1), "file"
    if m := _OPEN_RE.search(s):
        return m.group(1), "unknown"
    # Looks like a bare ID?
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", s):
        return s, "unknown"
    raise ValueError(f"Could not extract a Drive ID from: {url_or_id!r}")


# ─── Download helpers ────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    # Strip path separators, collapse whitespace
    clean = re.sub(r"[\\/]+", "_", name).strip()
    return clean or "unnamed"


def _download_single(service, file_id: str, dest_path: Path) -> Path:
    meta = service.files().get(fileId=file_id, fields="id,name,mimeType,size").execute()
    mime = meta["mimeType"]
    if mime in EXPORT_MAP:
        export_mime, ext = EXPORT_MAP[mime]
        if dest_path.suffix.lower() != ext:
            dest_path = dest_path.with_suffix(ext)
        req = service.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        req = service.files().get_media(fileId=file_id)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.FileIO(dest_path, "wb")
    downloader = MediaIoBaseDownload(buf, req, chunksize=1024 * 1024 * 4)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    print(f"  \u2713 {meta['name']}  \u2192  {dest_path}")
    return dest_path


def download_file(url_or_id: str, dest_dir: str | Path, filename: str | None = None) -> Path:
    """Download a single Drive file. Returns local Path."""
    file_id, _ = parse_id(url_or_id)
    service = _get_service()
    meta = service.files().get(fileId=file_id, fields="id,name,mimeType").execute()
    name = _safe_filename(filename or meta["name"])
    return _download_single(service, file_id, Path(dest_dir).expanduser() / name)


def list_folder(url_or_id: str) -> list[dict]:
    """List files in a Drive folder. Returns list of {id, name, mimeType, size}."""
    folder_id, _ = parse_id(url_or_id)
    service = _get_service()
    items: list[dict] = []
    page_token: str | None = None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
            pageSize=200,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            orderBy="name",
        ).execute()
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def download_folder(url_or_id: str, dest_dir: str | Path,
                    recursive: bool = False,
                    mime_prefix: str | None = None) -> list[Path]:
    """Download every file in a Drive folder. Returns list of local Paths.

    mime_prefix: if set, only download files whose mimeType starts with this
                 (e.g. 'image/' or 'video/').
    recursive: also recurse into subfolders.
    """
    dest = Path(dest_dir).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    service = _get_service()
    folder_id, _ = parse_id(url_or_id)

    items = list_folder(folder_id)
    print(f"Folder {folder_id}: {len(items)} item(s)")

    paths: list[Path] = []
    for it in items:
        mime = it["mimeType"]
        if mime == "application/vnd.google-apps.folder":
            if recursive:
                sub = dest / _safe_filename(it["name"])
                paths.extend(download_folder(it["id"], sub, recursive=True, mime_prefix=mime_prefix))
            else:
                print(f"  (skip folder) {it['name']}")
            continue
        if mime_prefix and not mime.startswith(mime_prefix):
            print(f"  (skip {mime}) {it['name']}")
            continue
        paths.append(_download_single(service, it["id"], dest / _safe_filename(it["name"])))
    return paths


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 drive_client.py <drive_url_or_id> [dest_dir]")
        sys.exit(1)
    url = sys.argv[1]
    dest = sys.argv[2] if len(sys.argv) > 2 else "~/Downloads/drive_dl"
    _id, kind = parse_id(url)
    if kind == "file":
        download_file(url, dest)
    elif kind == "folder":
        download_folder(url, dest)
    else:
        # Probe: try as folder first
        try:
            list_folder(_id)
            download_folder(url, dest)
        except Exception:
            download_file(url, dest)
