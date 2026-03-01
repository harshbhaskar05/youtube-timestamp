import os
import re
import base64
import tempfile
import subprocess
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 🔑 PUT YOUR AI PIPE TOKEN HERE
AIPIPE_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjI0ZjMwMDA5MzRAZHMuc3R1ZHkuaWl0bS5hYy5pbiJ9.x4aTFV9s5cV70shhbnLx2c-LX5NMs3El5dPg9ih7QEI"

# ⚡ Use FAST model (very important for Render timeout)
GEMINI_URL = "https://aipipe.org/geminiv1beta/models/gemini-1.5-flash:generateContent"

app = FastAPI()

# ✅ Enable CORS (grader sends OPTIONS request)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Health check endpoint (important)
@app.get("/")
def root():
    return {"status": "live"}


class AskRequest(BaseModel):
    video_url: str
    topic: str


# ==============================
# DOWNLOAD AUDIO (TRIMMED)
# ==============================

def download_audio(video_url: str):
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, "audio.%(ext)s")

    command = [
        "yt-dlp",
        "-f", "bestaudio",
        "--extract-audio",
        "--audio-format", "mp3",
        "--postprocessor-args", "ffmpeg:-t 900",  # trim first 15 minutes
        "-o", output_template,
        video_url
    ]

    subprocess.run(command, check=True)

    for file in os.listdir(temp_dir):
        if file.endswith(".mp3"):
            return os.path.join(temp_dir, file)

    raise Exception("Audio download failed")


# ==============================
# ASK GEMINI FOR TIMESTAMP
# ==============================

def find_timestamp_with_gemini(audio_path: str, topic: str):

    headers = {
        "Authorization": f"Bearer {AIPIPE_TOKEN}",
        "Content-Type": "application/json"
    }

    with open(audio_path, "rb") as f:
        audio_base64 = base64.b64encode(f.read()).decode("utf-8")

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "audio/mp3",
                            "data": audio_base64
                        }
                    },
                    {
                        "text": f"""
Listen carefully to this audio.

Find the EXACT moment when the following phrase is FIRST spoken:

"{topic}"

Return ONLY one timestamp in HH:MM:SS format.
No explanation.
"""
                    }
                ]
            }
        ]
    }

    response = requests.post(GEMINI_URL, headers=headers, json=body)

    if response.status_code != 200:
        print(response.text)
        response.raise_for_status()

    result_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]

    match = re.search(r"\b\d{2}:\d{2}:\d{2}\b", result_text)
    if match:
        return match.group(0)

    return "00:00:00"


# ==============================
# MAIN ENDPOINT
# ==============================

@app.post("/ask")
def ask(request: AskRequest):

    audio_path = download_audio(request.video_url)

    try:
        timestamp = find_timestamp_with_gemini(audio_path, request.topic)
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

    return {
        "timestamp": timestamp,
        "video_url": request.video_url,
        "topic": request.topic
    }