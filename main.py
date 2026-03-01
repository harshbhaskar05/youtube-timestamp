import asyncio
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

AIPIPE_TOKEN = os.getenv("AIPIPE_TOKEN")
if not AIPIPE_TOKEN:
    raise RuntimeError("Missing AIPIPE_TOKEN environment variable")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
AIPIPE_BASE = "https://aipipe.org"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    video_url: str
    topic: str


class AskResponse(BaseModel):
    timestamp: str
    video_url: str
    topic: str


def is_valid_hhmmss(value: str) -> bool:
    return bool(re.fullmatch(r"\d{2}:\d{2}:\d{2}", value))


def download_audio(video_url: str, out_dir: Path) -> Path:
    """Download audio-only from YouTube using yt-dlp."""
    output_template = str(out_dir / "audio.%(ext)s")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "-o",
        output_template,
        video_url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"yt-dlp failed: {stderr}")

    files = list(out_dir.glob("audio.*"))
    if not files:
        raise RuntimeError("yt-dlp did not produce an audio file")

    return files[0]


async def upload_audio_file_to_gemini(audio_path: Path, mime_type: str = "audio/mpeg") -> Dict[str, Any]:
    """
    Upload audio to Gemini Files API via AI Pipe (resumable upload).
    """
    file_bytes = audio_path.read_bytes()

    start_headers = {
        "x-goog-api-key": AIPIPE_TOKEN,
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(len(file_bytes)),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json",
    }
    start_payload = {"file": {"display_name": audio_path.name}}

    async with httpx.AsyncClient(timeout=120.0) as client:
        start_resp = await client.post(
            f"{AIPIPE_BASE}/upload/geminiv1beta/files",
            headers=start_headers,
            json=start_payload,
        )
        start_resp.raise_for_status()

        upload_url = start_resp.headers.get("x-goog-upload-url")
        if not upload_url:
            raise RuntimeError("Gemini upload URL not returned by Files API")

        upload_headers = {
            "x-goog-api-key": AIPIPE_TOKEN,
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "Content-Type": mime_type,
        }
        finalize_resp = await client.post(upload_url, headers=upload_headers, content=file_bytes)
        finalize_resp.raise_for_status()

        data = finalize_resp.json()
        if "file" not in data:
            raise RuntimeError(f"Unexpected Files API upload response: {data}")
        return data["file"]


async def wait_for_file_active(file_name: str, timeout_sec: int = 300) -> Dict[str, Any]:
    """Poll Files API until uploaded file state becomes ACTIVE."""
    deadline = time.time() + timeout_sec

    async with httpx.AsyncClient(timeout=60.0) as client:
        while time.time() < deadline:
            resp = await client.get(
                f"{AIPIPE_BASE}/geminiv1beta/{file_name}",
                headers={"x-goog-api-key": AIPIPE_TOKEN},
            )
            resp.raise_for_status()
            file_obj = resp.json()

            state_name = file_obj.get("state", {}).get("name", "")
            if state_name == "ACTIVE":
                return file_obj
            if state_name == "FAILED":
                raise RuntimeError("Gemini file processing failed")

            await asyncio.sleep(2)

    raise RuntimeError("Timed out waiting for Gemini file to become ACTIVE")


async def delete_remote_file(file_name: str) -> None:
    """Best-effort cleanup for Gemini uploaded files."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.delete(
                f"{AIPIPE_BASE}/geminiv1beta/{file_name}",
                headers={"x-goog-api-key": AIPIPE_TOKEN},
            )
    except Exception:
        pass


async def ask_gemini_for_timestamp(file_uri: str, mime_type: str, topic: str) -> str:
    prompt = (
        "You are given an audio file from a YouTube video. "
        f"Find when this topic is FIRST spoken: '{topic}'. "
        "Return only valid JSON with one field: timestamp in HH:MM:SS format."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "OBJECT",
                "properties": {
                    "timestamp": {
                        "type": "STRING",
                        "pattern": r"^\d{2}:\d{2}:\d{2}$",
                    }
                },
                "required": ["timestamp"],
            },
        },
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{AIPIPE_BASE}/geminiv1beta/models/{GEMINI_MODEL}:generateContent",
            headers={
                "x-goog-api-key": AIPIPE_TOKEN,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:
        raise RuntimeError(f"Unexpected Gemini response: {data}") from exc

    cleaned = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(cleaned)
        timestamp = parsed.get("timestamp", "")
    except Exception:
        match = re.search(r"\b\d{2}:\d{2}:\d{2}\b", cleaned)
        timestamp = match.group(0) if match else ""

    if not is_valid_hhmmss(timestamp):
        raise RuntimeError(f"Gemini returned invalid timestamp: {cleaned}")

    return timestamp


@app.get("/")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask_topic(request: AskRequest) -> AskResponse:
    tmp = tempfile.TemporaryDirectory()
    remote_file_name = ""

    try:
        tmp_path = Path(tmp.name)

        # 1) Download audio only from YouTube.
        audio_path = await asyncio.to_thread(download_audio, request.video_url, tmp_path)

        # 2) Upload to Gemini Files API via AI Pipe.
        uploaded_file = await upload_audio_file_to_gemini(audio_path)
        remote_file_name = uploaded_file.get("name", "")
        if not remote_file_name:
            raise RuntimeError(f"Upload succeeded but no file name found: {uploaded_file}")

        # 3) Wait until Gemini marks the file ACTIVE.
        active_file = await wait_for_file_active(remote_file_name)
        file_uri = active_file.get("uri", "")
        mime_type = active_file.get("mimeType", "audio/mpeg")
        if not file_uri:
            raise RuntimeError(f"ACTIVE file has no URI: {active_file}")

        # 4) Ask Gemini to locate first spoken mention.
        timestamp = await ask_gemini_for_timestamp(file_uri, mime_type, request.topic)

        # 5) Return required assignment format.
        return AskResponse(
            timestamp=timestamp,
            video_url=request.video_url,
            topic=request.topic,
        )

    except httpx.HTTPStatusError as err:
        detail = err.response.text if err.response is not None else str(err)
        raise HTTPException(status_code=500, detail=f"Upstream API error: {detail}")
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))
    finally:
        # Cleanup local temporary files.
        tmp.cleanup()

        # Best-effort remote cleanup.
        if remote_file_name:
            await delete_remote_file(remote_file_name)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
