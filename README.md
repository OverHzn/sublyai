# SublyAI

**Paste link. Generate Indonesian subtitles instantly.**

SublyAI is a self-hosted web app that turns any public video URL into:

- Bahasa Indonesia subtitles (`.srt`) with accurate Whisper timestamps
- Indonesian transcript (`.txt`)
- The original downloaded video or audio
- Optional video with subtitles burned in

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

### Tuning Whisper

Override these via environment variables (in your shell, a `.env` file next to
`docker-compose.yml`, or by editing the compose file directly):

```bash
SUBLYAI_WHISPER_MODEL=base       # tiny | base | small | medium | large-v3
SUBLYAI_WHISPER_DEVICE=cpu       # cuda for GPU
SUBLYAI_WHISPER_COMPUTE_TYPE=int8 # float16 / float32 on GPU
```

Smaller VPS? Use `base` or `tiny`. Beefy box? Try `medium`.

### Behind a reverse proxy / ngrok

The container only listens on port 8000 inside Docker; the compose file maps
that to the host's `:8000`. Point your nginx/Caddy/Traefik at `127.0.0.1:8000`,
or simply run `ngrok http 8000` on the host.

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

### Behind NAT — use ngrok

```bash
ngrok http 8000
```

Open the `https://<random>.ngrok-free.app` URL ngrok prints. SublyAI works
unchanged: there are no hardcoded domains.

---

## Run on Windows (local)

1. Install Python 3.10+.
2. Install ffmpeg and make sure `ffmpeg` is on your `PATH`
   (`ffmpeg -version` from PowerShell should work).
3. From the project folder:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn app:app --host 127.0.0.1 --port 8000
   ```

4. Open <http://127.0.0.1:8000>.

---

## API

All endpoints return JSON unless they're file downloads.

### `POST /api/jobs`

Form fields:

| Field | Required | Notes |
| --- | --- | --- |
| `url` | yes | Any URL [yt-dlp can handle](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md). |
| `quality` | no | One of `audio`, `480`, `720`, `1080`, `best`. Default `480`. |
| `burn_video` | no | Truthy ("on", "true", "1") enables burn-in. |

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

### `GET /download/{job_id}/{kind}`

`kind` is one of:

- `srt` → `outputs/<job_id>/subtitle_id.srt`
- `txt` → `outputs/<job_id>/transcript_id.txt`
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
