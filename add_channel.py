"""Create a new channel folder.

Usage:
    python add_channel.py <name> [--source URL] [--language Tamil] [--code ta]
                                 [--niche TEXT] [--category 24]

Example:
    python add_channel.py hunchsag --source https://www.youtube.com/@SomeChannel/shorts
"""
import argparse
import json
import re
import sys

from common import CHANNELS_DIR, DEFAULTS, fix_console


def main():
    fix_console()
    ap = argparse.ArgumentParser(description="Create a new channel folder")
    ap.add_argument("name", help="short folder name: letters, numbers, - and _ only")
    ap.add_argument("--source", default="", help="Shorts page to download from")
    ap.add_argument("--language", default=DEFAULTS["language"], help="language for titles, e.g. Tamil")
    ap.add_argument("--code", default=DEFAULTS["language_code"], help="YouTube language code, e.g. ta")
    ap.add_argument("--niche", default="", help="optional hint for Gemini")
    ap.add_argument("--category", default=DEFAULTS["category_id"], help="YouTube category id")
    args = ap.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.name):
        print("Use only letters, numbers, - and _ in the channel name.")
        sys.exit(1)

    folder = CHANNELS_DIR / args.name
    if folder.exists():
        print(f"channels/{args.name} already exists. Nothing changed.")
        sys.exit(1)

    (folder / "videos").mkdir(parents=True)
    cfg = dict(DEFAULTS)
    cfg.update({
        "source_url": args.source,
        "language": args.language,
        "language_code": args.code,
        "niche": args.niche,
        "category_id": args.category,
    })
    (folder / "channel.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Created channels/{args.name}/")
    print("Next steps:")
    print(f"  1. Check or edit channels/{args.name}/channel.json")
    print(f"  2. python download.py {args.name}     (skip if your videos are already in channels/{args.name}/videos)")
    print(f"  3. python upload.py {args.name} --dry-run   (preview titles and times)")
    print(f"  4. python upload.py {args.name}             (the first run opens a browser: choose THIS channel)")
    print(f"  5. Optional, Instagram Reels: see README section 13, then  python instagram.py {args.name} --dry-run")


if __name__ == "__main__":
    main()
