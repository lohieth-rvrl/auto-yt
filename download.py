"""Download Shorts into a channel's videos folder.

Usage:
    python download.py <channel>               use source_url from channel.json
    python download.py <channel> --url URL     download from this page instead

Only download videos that are yours or that you have permission to use.
Safe to re-run: already downloaded videos are skipped (archive.txt).
"""
import argparse
import shutil
import sys

from common import fix_console, load_channel, partial_files


def main():
    fix_console()
    ap = argparse.ArgumentParser(description="Download Shorts for one channel")
    ap.add_argument("channel")
    ap.add_argument("--url", help="Shorts page to download from (overrides channel.json)")
    args = ap.parse_args()

    cfg = load_channel(args.channel)
    url = args.url or cfg["source_url"]
    if not url or "YOUR_" in url:
        print(f"No source set. Put a link in channels/{args.channel}/channel.json (source_url) "
              "or run with --url.")
        sys.exit(1)

    if not shutil.which("ffmpeg"):
        print("ffmpeg is not installed (or this terminal was opened before installing it).")
        print("Without it, videos download as silent video plus a separate audio file.")
        print("Install:  winget install Gyan.FFmpeg   then close and reopen the terminal.")
        sys.exit(1)

    import yt_dlp

    opts = {
        "outtmpl": str(cfg["videos_dir"] / "%(upload_date)s_%(id)s.%(ext)s"),
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "merge_output_format": "mp4",
        "writeinfojson": True,  # keeps the original title/description for new metadata
        "download_archive": str(cfg["dir"] / "archive.txt"),
        "ignoreerrors": True,
        "sleep_interval": 2,
        "max_sleep_interval": 6,
    }
    print(f"[{cfg['name']}] downloading from {url}")
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    leftovers = partial_files(cfg)
    if leftovers:
        print(f"Note: {len(leftovers)} leftover partial file(s) in videos/ (names like xxx.f616.mp4). "
              "They are ignored by upload.py and are safe to delete.")
    print("Download finished.")


if __name__ == "__main__":
    main()
