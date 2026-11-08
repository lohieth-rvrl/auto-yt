"""Shared helpers used by every script in this project."""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHANNELS_DIR = ROOT / "channels"
CLIENT_SECRET = ROOT / "client_secret.json"
IST = timezone(timedelta(hours=5, minutes=30))

# Every channel starts from these values. channels/<name>/channel.json
# overrides any of them.
DEFAULTS = {
    "source_url": "",                  # channel Shorts page to download from
    "language": "Tamil",               # language for generated titles/descriptions
    "language_code": "ta",              # YouTube language code (ta, en, hi, ...)
    "niche": "",                       # optional hint for Gemini, e.g. "funny animal clips"
    "category_id": "24",               # 24 Entertainment, 27 Education, 15 Pets & Animals, 22 People & Blogs
    "made_for_kids": False,
    "slots_ist": ["06:00", "16:00"],   # publish times, 24-hour HH:MM, India time
    "max_uploads_per_run": 6,          # YouTube API default quota is about 6 uploads per day
    "gemini_models": [                 # tried in this order if one is busy or missing
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-flash-latest",
    ],
    "require_ai": True,                # True = never upload with the old title if Gemini fails
}

PARTIAL = re.compile(r"\.f\d+\.mp4$")  # video-only leftovers such as xxx.f616.mp4


def fix_console():
    """Stop Windows consoles crashing on Tamil text and emojis."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_env():
    """Read KEY=value lines from .env in the project folder."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def parse_slots(items):
    slots = []
    for item in items:
        try:
            hour, minute = str(item).split(":")
            hour, minute = int(hour), int(minute)
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError
        except ValueError:
            print(f'Bad time "{item}" in channel.json. Use 24-hour HH:MM, for example "06:00".')
            sys.exit(1)
        slots.append((hour, minute))
    if not slots:
        print("channel.json needs at least one time in slots_ist.")
        sys.exit(1)
    return sorted(set(slots))


def list_channels():
    if not CHANNELS_DIR.exists():
        return []
    return sorted(p.name for p in CHANNELS_DIR.iterdir() if (p / "channel.json").exists())


def load_channel(name):
    folder = CHANNELS_DIR / name
    cfg_path = folder / "channel.json"
    if not cfg_path.exists():
        names = list_channels()
        print(f"Channel '{name}' was not found.")
        print("Existing channels: " + (", ".join(names) if names else "(none yet)"))
        print(f"Create it with:  python add_channel.py {name}")
        sys.exit(1)
    try:
        user_cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        print(f"{cfg_path} is not valid JSON ({e}). Check commas and quote marks.")
        sys.exit(1)
    cfg = dict(DEFAULTS)
    cfg.update(user_cfg)
    cfg["name"] = name
    cfg["dir"] = folder
    cfg["videos_dir"] = folder / "videos"
    cfg["videos_dir"].mkdir(exist_ok=True)
    cfg["slots"] = parse_slots(cfg["slots_ist"])
    return cfg


def video_files(cfg):
    """Finished .mp4 files (partial pieces such as xxx.f616.mp4 are ignored)."""
    return sorted(p for p in cfg["videos_dir"].glob("*.mp4") if not PARTIAL.search(p.name))


def partial_files(cfg):
    return sorted(cfg["videos_dir"].glob("*.f[0-9]*.*"))


def load_state(cfg):
    path = cfg["dir"] / "state.json"
    state = {"uploaded": [], "last_slot": None, "videos": {}}
    if path.exists():
        state.update(json.loads(path.read_text(encoding="utf-8-sig")))
    state.setdefault("videos", {})
    return state


def save_state(cfg, state):
    path = cfg["dir"] / "state.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def next_slot(after, slots):
    """First configured IST slot strictly after `after` (a timezone-aware datetime)."""
    day = after.astimezone(IST).date()
    for offset in range(0, 3):
        d = day + timedelta(days=offset)
        for hour, minute in slots:
            slot = datetime(d.year, d.month, d.day, hour, minute, tzinfo=IST)
            if slot > after:
                return slot
    raise RuntimeError("could not compute the next slot")


def start_cursor(state):
    """Where scheduling continues from: 30 minutes from now, or the last used slot."""
    now = datetime.now(IST) + timedelta(minutes=30)  # YouTube needs publishAt in the future
    if state.get("last_slot"):
        return max(now, datetime.fromisoformat(state["last_slot"]))
    return now
