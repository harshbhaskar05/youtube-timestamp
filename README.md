# YouTube Topic Timestamp Finder (FastAPI)

This service implements `POST /ask` for the assignment:
- Input: YouTube URL + spoken topic/phrase
- Flow: `yt-dlp` audio download -> Gemini Files API upload (via `aipipe.org`) -> poll until `ACTIVE` -> ask Gemini for first spoken timestamp
- Output: strict `HH:MM:SS` timestamp with echoed `video_url` and `topic`

## Environment Variables

Create a `.env` file:

```env
AIPIPE_TOKEN=your_aipipe_token_here
# Optional:
# GEMINI_MODEL=gemini-2.0-flash
```

The code uses your AI Pipe token as `x-goog-api-key` against:
- `https://aipipe.org/upload/geminiv1beta/files`
- `https://aipipe.org/geminiv1beta/...`

## Install

```bash
pip install -r requirements.txt
```

## Run Locally

```bash
uvicorn main:app --host 0.0.0.0 --port 8001
```

Health check:

```bash
curl http://localhost:8001/
```

## Test `/ask`

```bash
curl -X POST "http://localhost:8001/ask" \
  -H "Content-Type: application/json" \
  -d "{\"video_url\":\"https://youtu.be/dQw4w9WgXcQ\",\"topic\":\"never gonna give you up\"}"
```

Expected response shape:

```json
{
  "timestamp": "00:05:47",
  "video_url": "https://youtu.be/dQw4w9WgXcQ",
  "topic": "never gonna give you up"
}
```

## Render Deploy

Start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set env vars in Render dashboard:
- `AIPIPE_TOKEN` (required)
- `GEMINI_MODEL` (optional)

Submit only your base URL to validator, for example:
- `https://your-service.onrender.com`

The validator appends `/ask` automatically.

## Notes

- The endpoint returns `500` if:
  - `yt-dlp` cannot download audio
  - Gemini file upload/processing fails
  - model output is not valid `HH:MM:SS`
- Local temporary audio files are always deleted after request processing.
- Uploaded Gemini file is deleted with best-effort cleanup.
