"""Show every channel: videos waiting, videos uploaded, where the schedule ends.

Usage:
    python status.py
"""
from common import (fix_console, list_channels, load_channel, load_state,
                    partial_files, video_files)


def main():
    fix_console()
    names = list_channels()
    if not names:
        print("No channels yet. Create one with:  python add_channel.py <name>")
        return
    for name in names:
        cfg = load_channel(name)
        state = load_state(cfg)
        done = set(state["uploaded"])
        pending = [p for p in video_files(cfg) if p.name not in done]
        per_day = len(cfg["slots"])
        days = -(-len(pending) // per_day) if pending else 0  # round up
        print(f"== {name}")
        print(f"   source:       {cfg['source_url'] or '(not set)'}")
        print(f"   language:     {cfg['language']}   category: {cfg['category_id']}   "
              f"times (IST): {', '.join(f'{h:02d}:{m:02d}' for h, m in cfg['slots'])}")
        print(f"   uploaded:     {len(done)}")
        print(f"   pending:      {len(pending)}  (about {days} days of posts)")
        print(f"   last slot:    {state['last_slot'] or '(none yet)'}")
        print(f"   logged in:    {'yes' if (cfg['dir'] / 'token.json').exists() else 'no (first upload will open the browser)'}")
        leftovers = partial_files(cfg)
        if leftovers:
            print(f"   leftovers:    {len(leftovers)} partial file(s) in videos/, safe to delete")
        print()


if __name__ == "__main__":
    main()
