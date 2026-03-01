import os
import re
import time
import tempfile
import subprocess
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 🔑 Your AI Pipe Token
AIPIPE_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjI0ZjMwMDA5MzRAZHMuc3R1ZHkuaWl0bS5hYy5pbiJ9.x4aTFV9s5cV70shhbnLx2c-LX5NMs3El5dPg9ih7QEI"

GEMINI_URL = "https://aipipe.org/geminiv1beta/models/gemini-1.5-pro:generateContent"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    video_url: str
    topic: str


def download_audio(video_url: str):
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, "audio.%(ext)s")

    command = [
        "yt-dlp",
        "-f", "bestaudio",
        "--extract-audio",
        "--audio-format", "mp3",
        "-o", output_template,
        video_url
    ]

    subprocess.run(command, check=True)

    for file in os.listdir(temp_dir):
        if file.endswith(".mp3"):
            return os.path.join(temp_dir, file)

    raise Exception("Audio download failed")


def find_timestamp_with_gemini(audio_path: str, topic: str):

    headers = {
        "Authorization": f"Bearer {AIPIPE_TOKEN}",
        "Content-Type": "application/json"
    }

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "audio/mp3",
                            "data": audio_bytes.decode("latin1")
                        }
                    },
                    {
                        "text": f"""
Listen to this audio carefully.

Find the EXACT time when the following phrase is first spoken:

"{topic}"

Return ONLY one timestamp in HH:MM:SS format.
Do not explain anything.
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

    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]

    match = re.search(r"\b\d{2}:\d{2}:\d{2}\b", text)
    if match:
        return match.group(0)

    return "00:00:00"


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