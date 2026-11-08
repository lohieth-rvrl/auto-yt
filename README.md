# YouTube Shorts Scheduler (multi-channel)

Download Shorts you own, write fresh titles / descriptions / tags with Gemini (Tamil by default,
with emojis), upload them to a YouTube channel, and schedule them to go public automatically at
**6:00 AM and 4:00 PM IST**, one after another. Every channel has its own folder, so you can add
as many channels as you like without mixing up logins or schedules.

> Only download and upload videos that are yours or that you have permission to use.
> Reposting other people's videos can lead to copyright claims, strikes and a terminated channel.

---

## 1. What is in this folder

```
yt_shorts_multi/
├── README.md              this file
├── requirements.txt       Python packages
├── .env                   your Gemini key (you create this, never share it)
├── .env.example           template for .env
├── client_secret.json     Google login file (you download this, never share it)
├── .gitignore             keeps secrets out of GitHub
│
├── add_channel.py         create a new channel folder
├── download.py            download videos for a channel
├── upload.py              write titles, upload, and schedule
├── instagram.py           queue videos and post them as Instagram Reels on a schedule
├── status.py              see all channels at a glance
├── common.py              shared code (you don't run this)
│
├── docs/
│   └── gemini_models_notes.md   which Gemini models exist and what the errors mean
│
└── channels/
    └── <channel-name>/    one folder per YouTube channel (created by add_channel.py)
        ├── channel.json   settings for this channel
        ├── videos/        the .mp4 files and their .info.json files
        ├── token.json     saved YouTube login for this channel (created on first upload)
        ├── state.json     what was uploaded and the last scheduled time
        └── archive.txt    which videos were already downloaded
```

The rule that makes this work: **everything that belongs to one channel lives in its own
`channels/<name>/` folder.** The Google project file (`client_secret.json`) and the Gemini key
(`.env`) are shared by all channels.

---

## 2. Install (one time)

1. Install **Python 3.9 or newer**.
2. Open a terminal in this folder and create a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate          (Windows)
   source venv/bin/activate       (Mac / Linux)
   ```
3. Install the packages:
   ```
   pip install -r requirements.txt
   ```
4. Install **ffmpeg** (joins video and sound) and **Deno** (helps yt-dlp read YouTube):
   ```
   winget install Gyan.FFmpeg
   winget install DenoLand.Deno
   ```
   **Close the terminal (and VS Code completely) and open it again**, then check:
   ```
   ffmpeg -version
   deno --version
   ```
   Without ffmpeg, videos download with no sound. `download.py` refuses to run until it is installed.

---

## 3. Google setup (one time, free)

This lets the script upload to YouTube on your behalf.

1. Go to https://console.cloud.google.com and create a project (any name).
2. **Enable the API:** APIs & Services → Library → search **YouTube Data API v3** → **Enable**.
3. **Consent screen:** APIs & Services → OAuth consent screen (newer layout: Google Auth Platform).
   - Audience / user type: choose **External** (Internal only works for Google Workspace).
   - Fill in the app name and your email, then Create.
   - Open **Audience → Test users → Add users** and add **every Google account** you will sign in with.
     If you skip this you get `Error 403: access_denied`.
   - Leave the app in **Testing** mode. You do not need to publish or verify it.
4. **Login file:** Credentials (or Clients) → Create credentials → OAuth client ID →
   **Desktop app** → Download JSON. Rename it **`client_secret.json`** and put it in this folder
   (next to `upload.py`).
5. When you first sign in you will see "Google hasn't verified this app". That is normal for your
   own app. Click **Advanced → Go to (your app) (unsafe)**, tick the upload permission, Continue.

## 4. Gemini key (one time, free)

1. Create a key at https://aistudio.google.com/apikey.
2. Copy `.env.example` to a new file named exactly **`.env`** (no `.txt` at the end) and put:
   ```
   GEMINI_API_KEY=your_key_here
   ```
   No quote marks, no spaces around `=`.
3. Keys that start with **`AQ.`** are the new Google format and work fine. Do not look for `AIza`.
4. Never paste your key into chats, screenshots or GitHub. If it leaks, delete it in AI Studio and make a new one.

---

## 5. Your first channel (quick start)

```
python add_channel.py main --source https://www.youtube.com/@SOURCE_CHANNEL/shorts
https://www.youtube.com/@InfoMachi/shorts
python download.py main
python upload.py main --dry-run
python upload.py main --limit 2
python status.py
```

What each line does:

| Command | What happens |
|---|---|
| `add_channel.py main --source URL` | Creates `channels/main/` with a `channel.json`. `main` is just a folder name you choose. |
| `download.py main` | Downloads every Short from that page into `channels/main/videos/`. Takes hours for hundreds of videos; you can stop with `Ctrl + C` and run it again later, it continues. |
| `upload.py main --dry-run` | Shows the new title, tags and publish time for each video. **Uploads nothing and saves nothing.** Use it to check the Tamil text. |
| `upload.py main --limit 2` | Uploads 2 videos for real. The **first time, a browser opens: sign in and choose the YouTube channel that should receive these videos.** |
| `status.py` | Lists every channel, videos waiting, and where the schedule ends. |

Then check **YouTube Studio → Content** on that channel: the videos should show **Scheduled** with
the right dates. If they look right, raise the limit by running `python upload.py main` (uses the
channel's `max_uploads_per_run`, default 6).

### Daily routine

Run `python upload.py main` once a day (or every few days). Each run uploads up to 6 videos and
schedules them after the last scheduled time. Your PC does **not** need to be on at 6 AM or 4 PM;
YouTube publishes them by itself.

---

## 6. Adding another channel

This is all you do, no copying folders:

```
python add_channel.py second --source https://www.youtube.com/@ANOTHER_SOURCE/shorts --language English --code en --niche "funny animal clips"
python download.py second
python upload.py second --dry-run
python upload.py second --limit 2
```

- The first upload for `second` opens the browser again. **Choose the other YouTube channel there.**
  Its login is saved in `channels/second/token.json`, separate from the first channel.
- Each channel has its own schedule (`state.json`), so two channels can both post at 6 AM and 4 PM.
- **Videos you already have** (not downloaded by this script): put the `.mp4` files in
  `channels/second/videos/`. If you also have matching `.info.json` files (same name) the script
  uses the original title as input for Gemini; without them Gemini writes from nothing, so add titles
  if you can.
- **A different Google account** for the new channel: add that email to **Test users** (section 3, step 3)
  first.

### Shared daily limit

YouTube's default quota is about **6 uploads per day for the whole Google Cloud project**, not per
channel. Two channels together cannot upload more than that per day. If you need more, create a
second Google Cloud project, repeat section 3 with its own `client_secret.json`, and use it for the
other channel (replace `client_secret.json` before uploading for that channel).

---

## 7. Moving over from the first version of this project

If you used the earlier single-channel folder (`New folder`, with `upload.py`, `config.py`, `videos/`):

1. Create the channel: `python add_channel.py main --source <your old source URL>`
2. Copy these from the **old** folder into `channels/main/`:
   `videos/` (whole folder), `state.json`, `token.json`, `archive.txt`
3. Copy `client_secret.json` and `.env` into the **new** project folder (next to `upload.py`).
4. Check `channels/main/channel.json` (category, language, times).
5. Run `python status.py`. It should show your uploaded count and last scheduled slot.

The old `state.json` works as it is, so nothing is uploaded twice and scheduling continues after
the last slot.

---

## 8. Settings: `channels/<name>/channel.json`

| Field | Default | Meaning |
|---|---|---|
| `source_url` | `""` | Shorts page to download from, e.g. `https://www.youtube.com/@name/shorts` |
| `language` | `"Tamil"` | Language Gemini writes titles, descriptions and tags in |
| `language_code` | `"ta"` | YouTube language code (`ta`, `en`, `hi`, `te`, ...) |
| `niche` | `""` | Short hint for Gemini, e.g. `"funny animal clips"` |
| `category_id` | `"24"` | `24` Entertainment, `27` Education, `15` Pets & Animals, `22` People & Blogs |
| `made_for_kids` | `false` | Set `true` only if the videos are made for children |
| `slots_ist` | `["06:00","16:00"]` | Publish times in India time, 24-hour `HH:MM`. Add or remove times freely |
| `max_uploads_per_run` | `6` | Videos per run. Keep at 6 or less because of the daily limit |
| `gemini_models` | 3 models | Tried in order, so a busy model doesn't stop the upload |
| `require_ai` | `true` | If Gemini fails, **stop** instead of uploading with the old title |

Changing `slots_ist` only affects videos not yet uploaded. Already scheduled videos keep their times.

---

## 9. How scheduling works

- Each video is uploaded as **private** with a publish time. YouTube flips it to **public** at that time.
- The first video goes to the next free slot at least 30 minutes from now. Every following video
  goes to the next slot after the previous one (6 AM, 4 PM, next day 6 AM, ...).
- Progress is saved after every successful upload in `state.json`, so you can stop and re-run safely.
- `state.json` stores `"uploaded"` (file names) and `"last_slot"` (the last time used). Don't delete it,
  or the same videos will upload again.

**Start a channel's schedule later** (for example from 17 Oct, 6 AM): edit `last_slot` in
`channels/<name>/state.json` to the slot **before** the one you want:

```
"last_slot": "2026-10-16T16:00:00+05:30"
```

The next video then lands on 17 Oct 6:00 AM. Keep the quote marks and the `+05:30`.

---

## 10. Command reference

| Command | What it does |
|---|---|
| `python add_channel.py NAME [--source URL] [--language Tamil] [--code ta] [--niche TEXT] [--category 24]` | New channel folder |
| `python download.py NAME [--url URL]` | Download; `--url` overrides `source_url` |
| `python upload.py NAME [--limit N] [--dry-run]` | Upload and schedule |
| `python download.py NAME --instagram` | Download, then queue the new videos for Instagram (section 13) |
| `python instagram.py NAME [--limit N] [--queue-only] [--publish-only] [--dry-run]` | Queue Reels and publish the ones that are due |
| `python status.py` | Overview of all channels |

You can run these from any folder, the scripts find their own files.

---

## 11. Troubleshooting

| What you see | Why | Fix |
|---|---|---|
| `Error 403: access_denied` ... "has not completed the Google verification process" | Your Google account isn't a test user | Cloud console → Audience → Test users → add your email |
| `403 ... YouTube Data API v3 has not been used in project` | API not enabled | Enable **YouTube Data API v3** in the Cloud console, wait 2-5 minutes |
| Gemini `401 Unauthorized` | Key missing or wrong in `.env` | Check `.env` name and one-line format; no quotes; make a new key |
| Gemini `404` | Model name wrong or retired | Fix names in `gemini_models`; see `docs/gemini_models_notes.md` |
| Gemini `503` | Google is busy | Nothing to do: the script tries the next model, then waits and retries |
| "Stopping: no new title could be made" | Gemini failed on every try | Run again in a few minutes. Nothing was uploaded with the old title |
| Videos have no sound | ffmpeg wasn't installed when they downloaded | Install ffmpeg, delete the `.mp4`, `.info.json` and `archive.txt` for the channel, download again |
| Files like `xxx.f616.mp4` / `xxx.f140.m4a` in `videos/` | Leftover pieces from a download without ffmpeg | Safe to delete; `upload.py` ignores them |
| `ffmpeg` works in Command Prompt but not in VS Code | VS Code started before the install | Close VS Code fully and reopen |
| Login stops working after about a week | Apps in Testing mode expire logins after 7 days | Just run `upload.py` again: it signs you in again automatically |
| Daily upload limit / quota error | About 6 uploads per day per Google project | Run again tomorrow |
| Scheduled videos stay **private** after their time | Uploads from new, unverified API projects can be locked private | Fill in the audit form: https://support.google.com/youtube/contact/yt_api_form . Test with 2 videos first |
| `Channel 'x' was not found` | Typo or not created | `python status.py` lists names; create with `add_channel.py` |
| Videos went to the wrong YouTube channel | Wrong channel chosen in the browser | Delete `channels/<name>/token.json` and run `upload.py` again, choose the right one. Fix already uploaded videos in YouTube Studio |
| Tamil text shows as `???` in the terminal | Old console encoding | The scripts already switch to UTF-8; use Windows Terminal or VS Code if it still happens |

---

## 12. Keeping things safe

- **Never share:** `.env`, `client_secret.json`, `channels/*/token.json`. The `.gitignore` already blocks
  them if you put this folder on GitHub.
- If a key or token was shown anywhere public, delete it and create a new one.
- Test every new channel with `--dry-run`, then `--limit 2`, and check YouTube Studio before uploading hundreds.
- Titles and emojis are generated from the **original title only**, not from watching the video,
  so skim the first few yourself before trusting a big batch.

---

## 13. Instagram Reels (scheduled)

`instagram.py` takes the videos already in `channels/<name>/videos/`, writes a caption for each with
Gemini (same language and niche as the YouTube side), gives each one a time slot, and posts it as a
Reel when that time arrives.

**Important difference from YouTube:** Instagram's API cannot schedule a post for later. YouTube
publishes by itself at 6 AM / 4 PM, but for Instagram **this script must be running at the posting
time**. So the PC (or a server) has to be on, and the script runs every 15-30 minutes (below).
If the PC was off and a post is more than `ig_grace_minutes` late, it moves to the next free slot
instead of everything posting at once.

### One-time Instagram setup

1. The Instagram account must be a **Professional account** (Business or Creator), linked to a
   **Facebook Page**. (Instagram app → Settings → Account type and tools.)
2. Go to https://developers.facebook.com → create an app (type **Business**) and add the
   **Instagram** product. Add your own Facebook and Instagram accounts as testers/roles. While the app
   is in **Development mode** it works for your own accounts without app review.
3. Generate an access token with the permissions `instagram_basic`, `instagram_content_publish`
   and `pages_read_engagement` (Graph API Explorer is fine). Exchange it for a **long-lived** token.
   If you use **Instagram Login** instead of Facebook Login, the permissions are
   `instagram_business_basic` and `instagram_business_content_publish`, and `graph_host` below
   becomes `graph.instagram.com`.
4. Find your **Instagram user id** (the numeric id of the Instagram account, not the username).
5. Create `channels/<name>/instagram.json`:
   ```
   {
     "ig_user_id": "1784xxxxxxxxxxxx",
     "access_token": "PASTE_LONG_LIVED_TOKEN",
     "api_version": "v23.0",
     "graph_host": "graph.facebook.com"
   }
   ```
   `api_version` and `graph_host` are optional. Each channel can have its own Instagram account.
   This file is in `.gitignore`. Never share it.

Tokens expire (long-lived user tokens last about 60 days). When posting fails with a token error
(`code 190`), make a new token and replace it in `instagram.json`.

### Everyday use

```
python download.py main --instagram        download, then queue the new videos for Instagram
python instagram.py main --dry-run         preview captions and times, changes nothing
python instagram.py main                   queue anything new AND post whatever is due now
python status.py                           shows posted / queued / next time per channel
```

Times come from `ig_slots_ist` in `channel.json` (default `09:00` and `19:00` IST), separate from the
YouTube `slots_ist`. Each video goes to the next free slot after the previous one.

### Make it run by itself

Run `python instagram.py main` every 30 minutes. It does nothing when no post is due.

Windows (Task Scheduler), change the paths to yours:
```
schtasks /create /sc minute /mo 30 /tn "ig-main" /tr "C:\path\to\venv\Scripts\python.exe C:\path\to\auto-yt\instagram.py main"
```
Mac / Linux (cron, `crontab -e`):
```
*/30 * * * * cd /path/to/auto-yt && ./venv/bin/python instagram.py main
```

### Settings in `channel.json`

| Field | Default | Meaning |
|---|---|---|
| `ig_slots_ist` | `["09:00","19:00"]` | Reel times in India time, 24-hour `HH:MM` |
| `ig_queue_per_run` | `10` | New videos given a caption and time per run |
| `ig_max_posts_per_run` | `3` | Most Reels published in one run |
| `ig_grace_minutes` | `120` | Posts later than this are moved to the next free slot |
| `ig_share_to_feed` | `true` | Also show the Reel on the profile grid |

### Notes

- Progress is in `channels/<name>/ig_state.json` (queue, posted, failed). Don't delete it or videos can
  be posted twice. A video that fails 3 times is moved to `failed` and skipped.
- Instagram allows 100 API-published posts per 24 hours, far above what this schedule uses.
- Use only videos you own or have permission to post. Reposting other people's videos can get
  the Instagram account restricted.
- Reels should be vertical (9:16) MP4 files. Downloaded Shorts already are.
