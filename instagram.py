"""Queue a channel's downloaded videos for Instagram Reels and publish them on a schedule.

Usage:
    python instagram.py <channel>                  queue new videos, then publish whatever is due
    python instagram.py <channel> --queue-only     only write captions and assign times
    python instagram.py <channel> --publish-only   only publish what is already due
    python instagram.py <channel> --limit 5        queue at most 5 new videos this run
    python instagram.py <channel> --dry-run        show captions and times, change nothing

Instagram's API has no "publish at" option (unlike YouTube), so this script keeps its own
schedule in channels/<channel>/ig_state.json and posts a Reel when its time has come.
That means it must RUN around the posting time: set it to run every 15-30 minutes
(Windows Task Scheduler / cron, see README section 13). Safe to run as often as you like.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

import requests

from common import (IST, fix_console, load_channel, load_env, next_slot,
                    parse_slots, video_files)
from upload import get_meta, read_original

CAPTION_MAX = 2200
MAX_ATTEMPTS = 3
# Meta error codes that mean "stop now, retrying other videos will fail too":
# 190 bad/expired token, 4/17/32/613 rate limits, 10/200 permissions.
FATAL_CODES = {190, 4, 17, 32, 613, 10, 200}


class IGError(Exception):
    def __init__(self, message, fatal=False):
        super().__init__(message)
        self.fatal = fatal


# ---------- state (separate from YouTube's state.json) ----------
def load_ig_state(cfg):
    path = cfg["dir"] / "ig_state.json"
    state = {"queue": [], "posted": {}, "failed": {}, "last_slot": None}
    if path.exists():
        state.update(json.loads(path.read_text(encoding="utf-8-sig")))
    return state


def save_ig_state(cfg, state):
    path = cfg["dir"] / "ig_state.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def when(text):
    return datetime.fromisoformat(text)


# ---------- Instagram login details (one account per channel) ----------
def load_ig_login(cfg):
    path = cfg["dir"] / "instagram.json"
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            print(f"{path} is not valid JSON ({e}).")
            sys.exit(1)
    login = {
        "ig_user_id": str(data.get("ig_user_id") or os.environ.get("IG_USER_ID", "")),
        "access_token": data.get("access_token") or os.environ.get("IG_ACCESS_TOKEN", ""),
        "api_version": data.get("api_version", "v23.0"),
        "graph_host": data.get("graph_host", "graph.facebook.com"),
    }
    if not login["ig_user_id"] or not login["access_token"]:
        print(f"Instagram is not set up for '{cfg['name']}'.")
        print(f"Create channels/{cfg['name']}/instagram.json with your ig_user_id and access_token")
        print("(see README section 13).")
        sys.exit(1)
    return login


# ---------- caption ----------
def build_caption(meta):
    """Turn the Gemini title/description/tags into an Instagram caption."""
    def strip_shorts(text):
        return re.sub(r"\s*#shorts\b", "", text, flags=re.IGNORECASE).strip()

    title = strip_shorts(meta["title"])
    desc = strip_shorts(meta["description"])
    tags, seen = [], {"reels"}
    for tag in meta["tags"]:
        tag = re.sub(r"[\s#.,!?'\"]+", "", tag)  # keep letters/marks (Tamil) intact
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append("#" + tag)
        if len(tags) >= 8:
            break
    tags.append("#Reels")
    caption = f"{title}\n\n{desc}\n\n{' '.join(tags)}".strip()
    return caption[:CAPTION_MAX]


# ---------- Instagram API ----------
def check(resp):
    """Return the JSON body, or raise IGError with Meta's own message."""
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400 or "error" in data:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        msg = err.get("error_user_msg") or err.get("message") or resp.text[:200]
        code = err.get("code")
        fatal = code in FATAL_CODES or resp.status_code in (401, 403, 429)
        raise IGError(f"{msg} (code {code}, HTTP {resp.status_code})", fatal=fatal)
    return data


def post_reel(ig, path, caption, share_to_feed):
    """Upload one video and publish it as a Reel. Returns (media_id, permalink)."""
    base = f"https://{ig['graph_host']}/{ig['api_version']}"
    token = ig["access_token"]
    try:
        # 1. create a container that accepts a direct (resumable) upload
        r = requests.post(f"{base}/{ig['ig_user_id']}/media", data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "share_to_feed": "true" if share_to_feed else "false",
            "access_token": token,
        }, timeout=60)
        container = check(r)["id"]

        # 2. send the file itself
        size = path.stat().st_size
        with open(path, "rb") as f:
            r = requests.post(
                f"https://rupload.facebook.com/ig-api-upload/{ig['api_version']}/{container}",
                headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
                data=f, timeout=(30, 900))
        body = {}
        try:
            body = r.json()
        except ValueError:
            pass
        if r.status_code >= 400 or not body.get("success"):
            info = body.get("debug_info", {}) if isinstance(body, dict) else {}
            raise IGError(f"upload failed: {info.get('message') or r.text[:200]}",
                          fatal=r.status_code in (401, 403, 429))

        # 3. wait until Instagram has processed it
        time.sleep(5)
        deadline = time.time() + 10 * 60
        while True:
            r = requests.get(f"{base}/{container}", params={
                "fields": "status_code,status", "access_token": token}, timeout=60)
            data = check(r)
            code = data.get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                raise IGError(f"Instagram could not process the video: {data.get('status', code)}")
            if time.time() > deadline:
                raise IGError("still processing after 10 minutes")
            time.sleep(20)

        # 4. publish
        r = requests.post(f"{base}/{ig['ig_user_id']}/media_publish",
                          data={"creation_id": container, "access_token": token}, timeout=60)
        media_id = check(r)["id"]
    except requests.RequestException as e:
        raise IGError(f"network problem: {e}", fatal=True)

    link = ""
    try:
        r = requests.get(f"{base}/{media_id}", params={
            "fields": "permalink", "access_token": token}, timeout=30)
        link = r.json().get("permalink", "")
    except Exception:
        pass
    return media_id, link


# ---------- step 1: captions and times ----------
def queue_videos(cfg, state, key, limit, dry):
    slots = parse_slots(cfg["ig_slots_ist"])
    queued = {q["file"] for q in state["queue"]}
    pending = [p for p in video_files(cfg)
               if p.name not in state["posted"] and p.name not in state["failed"]
               and p.name not in queued]
    print(f"[{cfg['name']}] Instagram: {len(pending)} video(s) not queued yet; "
          f"queuing up to {limit}{' (DRY RUN)' if dry else ''}")
    now = datetime.now(IST)
    cursor = max(now, when(state["last_slot"])) if state["last_slot"] else now
    count = 0
    for path in pending[:limit]:
        orig_title, orig_desc = read_original(path)
        meta = get_meta(cfg, orig_title, orig_desc, key)
        if meta is None:
            print("  Stopping: no caption could be made. Run again in a few minutes.")
            break
        slot = next_slot(cursor, slots)
        caption = build_caption(meta)
        print(f"{'Would queue' if dry else 'Queued'} {path.name} -> {slot:%Y-%m-%d %H:%M} IST")
        print(f"  source:   {meta['source']}")
        print(f"  ORIGINAL: {orig_title}")
        print(f"  CAPTION:  {caption.splitlines()[0]}")
        cursor = slot
        count += 1
        if dry:
            continue
        state["queue"].append({"file": path.name, "caption": caption,
                               "due": slot.isoformat(), "attempts": 0})
        state["last_slot"] = slot.isoformat()
        save_ig_state(cfg, state)
    return count


# ---------- step 2: publish what is due ----------
def reflow_overdue(cfg, state, dry):
    """If the PC was off and posts are very late, spread them over the next free slots
    instead of publishing them all in one burst."""
    slots = parse_slots(cfg["ig_slots_ist"])
    now = datetime.now(IST)
    grace = timedelta(minutes=cfg["ig_grace_minutes"])
    queue = sorted(state["queue"], key=lambda q: q["due"])
    late = [q for q in queue if now - when(q["due"]) > grace]
    if not late:
        return
    taken = {q["due"] for q in queue if q not in late}
    cursor = now
    for q in late:
        slot = next_slot(cursor, slots)
        while slot.isoformat() in taken:
            slot = next_slot(slot, slots)
        taken.add(slot.isoformat())
        print(f"  {q['file']} was due {when(q['due']):%d %b %H:%M}, too late to post now "
              f"-> moved to {slot:%d %b %H:%M} IST")
        if not dry:
            q["due"] = slot.isoformat()
        cursor = slot
    if not dry:
        state["last_slot"] = max(q["due"] for q in state["queue"])
        save_ig_state(cfg, state)


def publish_due(cfg, state, dry):
    reflow_overdue(cfg, state, dry)
    now = datetime.now(IST)
    due = sorted((q for q in state["queue"] if when(q["due"]) <= now), key=lambda q: q["due"])
    waiting = len(state["queue"]) - len(due)
    print(f"[{cfg['name']}] Instagram: {len(due)} due now, {waiting} waiting for their time")
    if not due:
        return 0
    ig = None if dry else load_ig_login(cfg)
    posted = 0
    for q in due[:cfg["ig_max_posts_per_run"]]:
        path = cfg["videos_dir"] / q["file"]
        if not path.exists():
            print(f"  {q['file']} is missing from videos/, removing it from the queue.")
            if not dry:
                state["queue"].remove(q)
                save_ig_state(cfg, state)
            continue
        print(f"{'Would post' if dry else 'Posting'} {q['file']} (was due {when(q['due']):%d %b %H:%M} IST)")
        if dry:
            continue
        try:
            media_id, link = post_reel(ig, path, q["caption"], cfg["ig_share_to_feed"])
        except IGError as e:
            q["attempts"] = q.get("attempts", 0) + 1
            q["last_error"] = str(e)[:300]
            print(f"  failed: {e}")
            if q["attempts"] >= MAX_ATTEMPTS and not e.fatal:
                print(f"  giving up on {q['file']} after {MAX_ATTEMPTS} tries (see ig_state.json).")
                state["queue"].remove(q)
                state["failed"][q["file"]] = {"error": q["last_error"]}
            save_ig_state(cfg, state)
            if e.fatal:
                print("  Stopping this run: check your token / limits (README section 13).")
                break
            continue
        print(f"  done: {link or media_id}")
        state["queue"].remove(q)
        state["posted"][q["file"]] = {"id": media_id, "link": link,
                                      "at": datetime.now(IST).isoformat()}
        save_ig_state(cfg, state)  # save right away so a crash can never cause a double post
        posted += 1
    return posted


def run(cfg, do_queue=True, do_publish=True, limit=None, dry=False):
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "")
    state = load_ig_state(cfg)
    if do_queue:
        queue_videos(cfg, state, key, limit if limit is not None else cfg["ig_queue_per_run"], dry)
    if do_publish:
        posted = publish_due(cfg, state, dry)
        if not dry:
            print(f"Posted {posted} this run. {len(state['queue'])} still queued.")


def main():
    fix_console()
    ap = argparse.ArgumentParser(description="Schedule and publish Instagram Reels for one channel")
    ap.add_argument("channel")
    ap.add_argument("--limit", type=int, help="queue at most this many new videos this run")
    ap.add_argument("--queue-only", action="store_true", help="only write captions and assign times")
    ap.add_argument("--publish-only", action="store_true", help="only publish posts that are due")
    ap.add_argument("--dry-run", action="store_true", help="preview only; post nothing, save nothing")
    args = ap.parse_args()
    if args.queue_only and args.publish_only:
        print("Use only one of --queue-only and --publish-only.")
        sys.exit(1)
    cfg = load_channel(args.channel)
    run(cfg, do_queue=not args.publish_only, do_publish=not args.queue_only,
        limit=args.limit, dry=args.dry_run)


if __name__ == "__main__":
    main()
