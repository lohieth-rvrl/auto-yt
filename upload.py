"""Upload a channel's downloaded Shorts and schedule them.

Usage:
    python upload.py <channel>                upload up to the channel's limit
    python upload.py <channel> --limit 2      upload only 2 this run
    python upload.py <channel> --dry-run      show titles and times, upload nothing

Each video is uploaded as private with a publish time, and YouTube makes it
public by itself at that time (6 AM and 4 PM IST by default).
Safe to re-run: progress is kept in channels/<channel>/state.json.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import timezone

import requests

from common import (CLIENT_SECRET, IST, fix_console, load_channel, load_env,
                    load_state, next_slot, partial_files, save_state,
                    start_cursor, video_files)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class GeminiAuthError(Exception):
    """The Gemini key was rejected, so retrying is pointless."""


# ---------- YouTube login (one saved login per channel) ----------
def get_service(cfg):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token = cfg["dir"] / "token.json"
    creds = None
    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except Exception as e:
                print(f"Saved login for '{cfg['name']}' has expired ({e}). Signing in again...")
        if not refreshed:
            if not CLIENT_SECRET.exists():
                print("client_secret.json is missing. Put it in the project folder (see README, step 3).")
                sys.exit(1)
            print(f"A browser will open. Sign in and choose the YouTube channel for '{cfg['name']}'.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        token.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


# ---------- title / description / tags ----------
def clean(text):
    return str(text).replace("<", "").replace(">", "").strip()


def clean_tags(tags):
    out, seen, total = [], set(), 0
    for tag in tags:
        tag = clean(tag).replace("#", "").strip()
        if not tag or len(tag) > 30 or tag.lower() in seen:
            continue
        if total + len(tag) + 1 > 450:  # YouTube allows about 500 characters of tags
            break
        seen.add(tag.lower())
        out.append(tag)
        total += len(tag) + 1
    return out[:15]


def fallback_meta(orig_title):
    title = clean(orig_title or "Short")[:90]
    if "#shorts" not in title.lower():
        title += " #Shorts"
    return {"title": title, "description": f"{title}\n\n#Shorts", "tags": ["shorts"],
            "source": "FALLBACK (original title, Gemini not used)"}


def build_prompt(cfg, orig_title, orig_desc):
    lang = cfg["language"]
    niche = f"Channel niche: {cfg['niche']}.\n" if cfg["niche"] else ""
    return (
        f"You write YouTube Shorts metadata in {lang}.\n{niche}"
        f"Original title: {orig_title}\nOriginal description: {orig_desc[:500]}\n\n"
        f"Return ONLY JSON with keys: title (max 85 chars, catchy, in {lang}, "
        f"start with 1-2 emojis that match the video's topic and emotion (for example "
        f"funny, cute, shocking, sad, heartwarming, amazing), and you may add one more "
        f"emoji at the end; do not include #Shorts), description (2-3 short lines in "
        f"{lang}, each line may start with a fitting emoji, plus 3-5 hashtags, "
        f"must include #Shorts), tags (list of 8-12 short tags, mix of {lang} "
        f"and English, plain text only, no emojis, no # symbol). "
        f"Choose emojis from the original title's meaning and mood; do not use more than "
        f"3 emojis in the title."
    )


def call_gemini(model, prompt, key):
    base = os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    r = requests.post(
        f"{base}/models/{model}:generateContent",
        headers={"x-goog-api-key": key},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json"}},
        timeout=60,
    )
    if r.status_code in (401, 403):
        raise GeminiAuthError(f"HTTP {r.status_code}: {r.text[:200]}")
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    data = json.loads("".join(p.get("text", "") for p in parts if not p.get("thought")))
    if isinstance(data, list):
        data = data[0]
    title = clean(data["title"])[:90]
    if "#shorts" not in title.lower():
        title += " #Shorts"
    desc = clean(data["description"])
    if "#shorts" not in desc.lower():
        desc += "\n#Shorts"
    return {"title": title[:100], "description": desc[:4900],
            "tags": clean_tags(data.get("tags", [])), "source": f"GEMINI ({model})"}


def get_meta(cfg, orig_title, orig_desc, key):
    """Ask Gemini, trying each model and retrying when busy.
    Returns None if it keeps failing (unless require_ai is false)."""
    if not key:
        print("  GEMINI_API_KEY is not set (put it in .env).")
        return None if cfg["require_ai"] else fallback_meta(orig_title)
    prompt = build_prompt(cfg, orig_title, orig_desc)
    for wait in (0, 10, 30, 60):
        if wait:
            print(f"  all models busy, retrying in {wait}s...")
            time.sleep(wait)
        for model in cfg["gemini_models"]:
            try:
                return call_gemini(model, prompt, key)
            except GeminiAuthError as e:
                print(f"  Gemini key rejected ({e}). Check GEMINI_API_KEY in .env.")
                return None if cfg["require_ai"] else fallback_meta(orig_title)
            except Exception as e:
                print(f"  {model} failed: {str(e)[:160]}")
    return None if cfg["require_ai"] else fallback_meta(orig_title)


# ---------- upload ----------
def upload_one(yt, cfg, path, meta, publish_at):
    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": str(cfg["category_id"]),
            "defaultLanguage": cfg["language_code"],
            "defaultAudioLanguage": cfg["language_code"],
        },
        "status": {
            # "privacyStatus": "private",  # becomes public automatically at publishAt
            # "publishAt": publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            # "selfDeclaredMadeForKids": bool(cfg["made_for_kids"]),

            "privacyStatus": "public",
            "selfDeclaredMadeForKids": bool(cfg["made_for_kids"]),
        },
    }
    media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%", end="\r")
    return resp["id"]


def read_original(path):
    info_path = path.with_suffix(".info.json")
    if not info_path.exists():
        return "", ""
    info = json.loads(info_path.read_text(encoding="utf-8"))
    return info.get("title", ""), re.sub(r"\s+", " ", info.get("description", "") or "")


def main():
    fix_console()
    load_env()
    ap = argparse.ArgumentParser(description="Upload and schedule Shorts for one channel")
    ap.add_argument("channel")
    ap.add_argument("--limit", type=int, help="upload at most this many videos this run")
    ap.add_argument("--dry-run", action="store_true", help="preview only; upload nothing, save nothing")
    args = ap.parse_args()

    cfg = load_channel(args.channel)
    state = load_state(cfg)
    key = os.environ.get("GEMINI_API_KEY", "")
    limit = args.limit if args.limit is not None else cfg["max_uploads_per_run"]
    tag = " (DRY RUN)" if args.dry_run else ""

    leftovers = partial_files(cfg)
    if leftovers:
        print(f"Note: ignoring {len(leftovers)} leftover partial file(s) in videos/ "
              "(names like xxx.f616.mp4). They are safe to delete.")

    done = set(state["uploaded"])
    pending = [p for p in video_files(cfg) if p.name not in done]
    print(f"[{cfg['name']}] {len(pending)} videos pending; this run: up to {limit}{tag}")
    if not pending:
        return

    yt = None if args.dry_run else get_service(cfg)
    cursor = start_cursor(state)
    uploaded = 0

    for path in pending[:limit]:
        orig_title, orig_desc = read_original(path)
        meta = get_meta(cfg, orig_title, orig_desc, key)
        if meta is None:
            print("  Stopping: no new title could be made, so nothing was uploaded with the old title. "
                  "Run again in a few minutes.")
            break
        slot = next_slot(cursor, cfg["slots"])
        print(f"{'Would upload' if args.dry_run else 'Uploading'} {path.name} -> {slot:%Y-%m-%d %H:%M} IST")
        print(f"  source:   {meta['source']}")
        print(f"  ORIGINAL: {orig_title}")
        print(f"  NEW:      {meta['title']}")
        print(f"  tags:     {', '.join(meta['tags'])}")
        if args.dry_run:
            cursor = slot
            continue
        try:
            vid = upload_one(yt, cfg, path, meta, slot)
        except Exception as e:
            text = str(e).lower()
            print(f"  upload failed: {e}")
            if "quota" in text or "uploadlimitexceeded" in text:
                print("  Daily upload limit reached. Run again tomorrow.")
            elif "accessnotconfigured" in text or "has not been used" in text:
                print("  Enable 'YouTube Data API v3' in your Google Cloud project, wait a few minutes, retry.")
            break
        print(f"  done: https://youtube.com/shorts/{vid}")
        state["uploaded"].append(path.name)
        state["last_slot"] = slot.isoformat()
        state["videos"][path.name] = {"id": vid, "slot": slot.isoformat(), "title": meta["title"]}
        save_state(cfg, state)
        cursor = slot
        uploaded += 1

    if not args.dry_run:
        print(f"Uploaded {uploaded} this run. {len(pending) - uploaded} still pending.")


if __name__ == "__main__":
    main()
