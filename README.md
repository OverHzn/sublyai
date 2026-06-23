# SublyAI

**Paste link. Generate Indonesian subtitles instantly.**

SublyAI is a self-hosted web app that turns any public video URL — or a
local file you drop into the browser — into:

- Translated subtitles in **20+ languages** as `.srt`, `.vtt`, and `.ass`
- Plain-text transcript (`.txt`)
- The original downloaded video or audio
- Optional video with subtitles **burned in** (custom font, size, color and position)

Other goodies built into the UI:

- Per-job choice of Whisper model size (`tiny` … `large-v3`)
- Drag-and-drop local file uploads (≤ 1 GiB)
- Batch mode — paste many URLs, run them sequentially
- **Inline subtitle editor** — fix transcription mistakes and regenerate every output
- Job history sidebar (last 10 jobs, stored locally in your browser)
- One-click "Copy transcript" to clipboard
- Installable as a PWA on mobile / desktop
- Production deploy templates for Docker, systemd + nginx, and Caddy

It runs on Windows, Ubuntu (or any Linux VPS), and works behind an
[ngrok](https://ngrok.com/) tunnel for NAT VPSes.

---

## How it works

1. You paste a video URL and click **Generate**.
2. The server downloads the media with [`yt-dlp`](https://github.com/yt-dlp/yt-dlp).
3. `ffmpeg` extracts a 16 kHz mono WAV.
4. [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) transcribes
   the audio into timestamped segments.
5. Each segment is translated to Indonesian via
   [`deep-translator`](https://github.com/nidhaloff/deep-translator)
   (Google).
6. The server writes a valid `.srt` and a `.txt`, plus an optional
   `video_subtitle.mp4` when **Burn subtitle to video** is checked.
7. The web UI surfaces download buttons for everything that was produced.

---

## Quality presets

| Option | yt-dlp format |
| --- | --- |
| `audio` | `bestaudio/best` |
| `480` | `bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]/best[height<=480]/best` |
| `720` | `bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/best[height<=720]/best` |
| `1080` | `bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/best[height<=1080]/best` |
| `best` | `bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best` |

Defaults are kept light to avoid huge downloads:

- Default quality is **480p**.
- For subtitle-only workflows, choose **Audio only** — you'll still get the
  `.srt` and `.txt`.
- Enabling **Burn subtitle to video** with audio-only auto-upgrades to 480p
  so there's a video stream to render onto.

---

## Project layout

```
sublyai/
├─ app.py                # FastAPI app + background worker
├─ config.py             # paths, quality presets, model config
├─ requirements.txt
├─ utils/
│  ├─ downloader.py      # yt-dlp wrapper
│  ├─ media.py           # ffmpeg audio extraction + subtitle burn-in
│  ├─ transcriber.py     # faster-whisper, lazy-loaded model
│  ├─ translator.py      # deep-translator, fault-tolerant per segment
│  ├─ subtitle.py        # SRT/TXT writers
│  └─ jobs.py            # job lifecycle + status JSON
├─ templates/index.html  # Jinja2 UI
├─ static/
│  ├─ style.css          # premium SaaS dashboard styling
│  └─ app.js             # form submit + 2.5s status polling
├─ downloads/            # downloaded media per job_id
├─ outputs/              # audio.wav, subtitle_id.srt, transcript_id.txt, video_subtitle.mp4
└─ jobs/                 # <job_id>.json status files
```

---

## Run with Docker (recommended)

This is the fastest path on a fresh server — no manual ffmpeg / Python / venv
setup. You only need Docker (with the Compose plugin) installed.

```bash
git clone https://github.com/OverHzn/sublyai.git
cd sublyai
docker compose up -d --build
```

Open `http://<server-ip>:8000`. That's it.

### Useful Docker commands

```bash
docker compose logs -f sublyai      # tail logs
docker compose ps                   # is it healthy?
docker compose restart sublyai      # restart after pulling new code
docker compose down                 # stop and remove the container
docker compose up -d --build        # rebuild after code changes
```

### Where files live

The compose file bind-mounts the runtime directories so the artifacts survive
container rebuilds and are inspectable from the host:

| Host path     | Container path  | Contents |
| ---           | ---             | --- |
| `./downloads` | `/app/downloads` | yt-dlp raw downloads, per `job_id` |
| `./outputs`   | `/app/outputs`   | `audio.wav`, `subtitle_id.srt`, `transcript_id.txt`, `video_subtitle.mp4` |
| `./jobs`      | `/app/jobs`      | `<job_id>.json` status files |
| named volume `whisper_cache` | `/home/app/.cache/huggingface` | Whisper model weights (downloaded once, ~500 MB for `small`) |

The container starts as `root` so the entrypoint can `chown` the bind-mounted
directories to UID 1000 on first launch (otherwise a fresh `git clone` as root
would leave them root-owned and unwritable to the in-container user). It then
drops privileges via `gosu` and runs uvicorn as a non-root `app` user. If you
mount filesystems where `chown` is not allowed (CIFS, some NFS setups), set
`SUBLYAI_RUN_AS_ROOT=1` in your environment to keep the container running as
root.

### Tuning Whisper

Override these via environment variables (in your shell, a `.env` file next to
`docker-compose.yml`, or by editing the compose file directly):

```bash
SUBLYAI_WHISPER_MODEL=base       # tiny | base | small | medium | large-v3
SUBLYAI_WHISPER_DEVICE=cpu       # cuda for GPU
SUBLYAI_WHISPER_COMPUTE_TYPE=int8 # float16 / float32 on GPU
```

Smaller VPS? Use `base` or `tiny`. Beefy box? Try `medium`.

### Behind a reverse proxy

The container only listens on port 8000 inside Docker; the compose file maps
that to the host's `:8000`. Point your nginx/Caddy/Traefik at `127.0.0.1:8000`.
For a one-command HTTPS tunnel without owning a domain, see the
[ngrok section](#expose-publicly-with-ngrok) below.

---

## Run on Ubuntu (or any Linux VPS) — without Docker

```bash
# 1. system deps
sudo apt update
sudo apt install -y ffmpeg python3-venv

# 2. project deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. start the server
uvicorn app:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000`.

If your VPS has a public IPv4 address you can bind directly:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

---

## Expose publicly with ngrok

The fastest way to make SublyAI reachable from the public internet without
owning a domain or configuring DNS. ngrok's free tier gives you HTTPS, one
reserved static URL, and ~120 requests/minute — plenty for personal use.

### 1. Sign up and get your authtoken

Create a free account at <https://dashboard.ngrok.com/signup> and copy the
token from <https://dashboard.ngrok.com/get-started/your-authtoken>.

### 2. Install the agent on your VPS

```bash
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install -y ngrok
ngrok config add-authtoken YOUR_AUTHTOKEN
```

### 3. Reserve a static domain (optional but recommended)

The free tier includes one reserved domain so your URL doesn't change on
every restart. Click **+ New Domain** at
<https://dashboard.ngrok.com/domains> and copy the result, e.g.
`kucing-ganteng-1234.ngrok-free.app`.

### 4. Test the tunnel

```bash
# Make sure SublyAI is running first
docker compose up -d

# Then start the tunnel
ngrok http --url=kucing-ganteng-1234.ngrok-free.app 8000
```

Open the URL in any browser, on any network — SublyAI loads with HTTPS and
no further config (it has no hardcoded domains). Press Ctrl+C to stop.

### 5. Run ngrok as a systemd service

So the tunnel survives reboots and crashes, install the bundled unit:

```bash
sudo cp deploy/ngrok-sublyai.service /etc/systemd/system/ngrok-sublyai.service
sudo nano /etc/systemd/system/ngrok-sublyai.service       # edit --url=...
sudo systemctl daemon-reload
sudo systemctl enable --now ngrok-sublyai
sudo systemctl status ngrok-sublyai                       # should be active (running)
sudo journalctl -u ngrok-sublyai -f                       # live logs
```

If you also enable `sudo systemctl enable docker`, the entire stack
(Docker → SublyAI container → ngrok tunnel) restarts automatically when
the VPS reboots.

### Free-tier caveats

- **Browser warning page.** First-time visitors see a "Visit Site" interstitial.
  Upgrade to ngrok Personal ($8/month) to remove it, or switch to Cloudflare
  Tunnel which has no warning page.
- **One simultaneous tunnel** and 120 req/min — fine for one or two users.
- **Bandwidth is unmetered but rate limited** — fast enough for SublyAI but
  large multi-GB media downloads from `/download/{job_id}/video` may feel
  slower than direct LAN.

When you outgrow ngrok, the [systemd + nginx/Caddy](#run-on-a-vps-with-systemd--nginxcaddy)
section below shows how to host on your own domain with HTTPS.

---

## Run on a VPS with systemd + nginx/Caddy

The repo ships ready-to-edit templates under `deploy/`:

- [`deploy/sublyai.service`](deploy/sublyai.service) — systemd unit
- [`deploy/nginx.conf.example`](deploy/nginx.conf.example) — nginx reverse proxy with HTTPS hooks for certbot
- [`deploy/Caddyfile.example`](deploy/Caddyfile.example) — Caddy alternative (auto HTTPS)
- [`deploy/ngrok-sublyai.service`](deploy/ngrok-sublyai.service) — auto-start ngrok tunnel (no domain required, see [ngrok section](#expose-publicly-with-ngrok))

Quick install (Ubuntu, no Docker):

```bash
# 1. System deps
sudo apt update
sudo apt install -y git ffmpeg python3-venv

# 2. App user + clone
sudo useradd --system --create-home --home /opt/sublyai --shell /usr/sbin/nologin sublyai
sudo -u sublyai git clone https://github.com/OverHzn/sublyai.git /opt/sublyai
cd /opt/sublyai
sudo -u sublyai python3 -m venv .venv
sudo -u sublyai .venv/bin/pip install -r requirements.txt

# 3. Systemd unit
sudo cp deploy/sublyai.service /etc/systemd/system/sublyai.service
sudo systemctl daemon-reload
sudo systemctl enable --now sublyai
sudo systemctl status sublyai

# 4. Reverse proxy — pick one
# nginx
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/sublyai
sudo ln -s /etc/nginx/sites-available/sublyai /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d sublyai.example.com

# OR Caddy (auto-HTTPS)
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Override config (Whisper model, target language, etc.) by dropping a
`/etc/sublyai.env` file with `SUBLYAI_WHISPER_MODEL=base`,
`SUBLYAI_TRANSLATE_TARGET=en`, etc.

---

## Desktop App (Windows) — tanpa browser

SublyAI bisa dibuka sebagai **aplikasi desktop** (jendela sendiri, bukan tab browser).

**Cara tercepat:**

1. Double-click **`setup-app.bat`** (sekali saja — setup Python + Electron)
2. Double-click **`start-app.bat`** — app terbuka langsung

**Build installer (.exe):**

```powershell
.\build-app.bat
# hasil di desktop\dist\SublyAI Setup x.x.x.exe
```

> Setelah install, pastikan folder `.venv` ada di project root (jalankan
> `setup-app.bat` sekali). Whisper model (~500 MB) di-download otomatis saat
> job pertama.

---

## Run on Windows (local — via browser)

**Double-click `start.bat`** (auto setup venv + buka browser).

Atau manual:

1. Install Python 3.10+.
2. Install ffmpeg and make sure `ffmpeg` is on your `PATH`
   (`ffmpeg -version` from PowerShell should work).
3. From the project folder:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python run_local.py
   ```

   `run_local.py` menjalankan server di `127.0.0.1:8000` dan membuka browser
   otomatis. Alternatif: `.\start.ps1` atau `uvicorn app:app --host 127.0.0.1 --port 8000`.

4. Buka <http://127.0.0.1:8000> kalau browser tidak terbuka sendiri.

> **Tip:** SublyAI bisa di-install sebagai PWA dari browser (Chrome/Edge →
> menu → *Install app*) supaya terasa seperti desktop app.

---

## API

All endpoints return JSON unless they're file downloads.

### `POST /api/jobs`

`multipart/form-data` body. Provide **either** `url` *or* a `file` upload.

| Field | Required | Notes |
| --- | --- | --- |
| `url` | one of url/file | Any URL [yt-dlp can handle](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md). |
| `file` | one of url/file | Drop a local mp4/mkv/mp3/wav/m4a/webm (≤ 1 GiB). |
| `quality` | no | One of `audio`, `480`, `720`, `1080`, `best`. Default `480`. |
| `burn_video` | no | Truthy ("on", "true", "1") enables burn-in. |
| `target_lang` | no | Translation target. Any code Google Translate accepts. Default `id`. |
| `whisper_model` | no | One of `tiny`, `base`, `small`, `medium`, `large-v3`. Default `small`. |
| `style` | no | JSON string with burn-in styling: `{font_name, font_size, font_color, outline_color, alignment, outline}`. Only applied when `burn_video` is on. |

Returns `{"job_id": "..."}` and starts a background job.

### `GET /api/jobs/{job_id}`

Returns the job status JSON:

```json
{
  "job_id": "abc123…",
  "url": "https://…",
  "quality": "480",
  "burn_video": false,
  "status": "processing",
  "progress": 65,
  "message": "AI is creating timestamps…",
  "error": null,
  "files": {
    "srt": null, "txt": null, "original": null, "video": null
  }
}
```

`status` is one of `queued`, `processing`, `done`, `failed`.

### `GET /api/jobs/{job_id}/segments`

Returns the editable segments dump:

```json
{ "segments": [ { "start": 0.0, "end": 2.4, "text": "…" }, … ] }
```

### `PUT /api/jobs/{job_id}/segments`

JSON body `{ "segments": [...], "rerender_video": true }`. Replaces the
editable segments and regenerates SRT/TXT/VTT/ASS. With `rerender_video=true`
the burn-in is also re-rendered (only allowed for jobs that originally had
`burn_video=true` and whose source media is still on disk).

### `GET /download/{job_id}/{kind}`

`kind` is one of:

- `srt` → `outputs/<job_id>/subtitle_id.srt`
- `txt` → `outputs/<job_id>/transcript_id.txt`
- `vtt` → `outputs/<job_id>/subtitle.vtt`
- `ass` → `outputs/<job_id>/subtitle.ass`
- `original` → newest media file in `downloads/<job_id>/`
- `video` → `outputs/<job_id>/video_subtitle.mp4` (only when burn-in succeeded)

Missing artifacts return a clean 404.

---

## Configuration

All paths and tunables live in `config.py` and can be overridden with
environment variables:

| Variable | Default |
| --- | --- |
| `SUBLYAI_DOWNLOADS_DIR` | `./downloads` |
| `SUBLYAI_OUTPUTS_DIR` | `./outputs` |
| `SUBLYAI_JOBS_DIR` | `./jobs` |
| `SUBLYAI_WHISPER_MODEL` | `small` |
| `SUBLYAI_WHISPER_DEVICE` | `cpu` |
| `SUBLYAI_WHISPER_COMPUTE_TYPE` | `int8` |
| `SUBLYAI_TRANSLATE_TARGET` | `id` |

The first job will download the Whisper model weights (a few hundred MB for
`small`) into the user cache, then reuse them.

---

## Resilience notes

- yt-dlp uses `retries`, `fragment_retries`, `continuedl` and a 30 s
  `socket_timeout` to ride out flaky links.
- Translation is best-effort: if Google translate refuses a segment, the
  original text is kept so the job still completes.
- Burn-in failures don't fail the whole job — you still get the SRT/TXT.
- Each job is isolated under its own `job_id` directory, and a worker
  exception is converted into a clean `failed` status so one bad URL never
  takes the server down.
