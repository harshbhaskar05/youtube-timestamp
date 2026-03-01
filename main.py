import os
import tempfile
import subprocess
from fastapi import FastAPI
from pydantic import BaseModel
from faster_whisper import WhisperModel

app = FastAPI()

# Use tiny model for Render free tier
model = WhisperModel("tiny", compute_type="int8")

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


def seconds_to_hhmmss(seconds: float):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"


def find_timestamp_from_audio(audio_path: str, topic: str):
    topic_words = topic.lower().split()

    segments, _ = model.transcribe(
        audio_path,
        word_timestamps=True
    )

    words = []

    for segment in segments:
        for word in segment.words:
            words.append({
                "word": word.word.lower().strip(),
                "start": word.start
            })

    for i in range(len(words) - len(topic_words) + 1):
        match = True
        for j in range(len(topic_words)):
            if topic_words[j] not in words[i + j]["word"]:
                match = False
                break

        if match:
            return seconds_to_hhmmss(words[i]["start"])

    return "00:00:00"


@app.post("/ask")
def ask(request: AskRequest):

    audio_path = download_audio(request.video_url)

    try:
        timestamp = find_timestamp_from_audio(audio_path, request.topic)
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

    return {
        "timestamp": timestamp,
        "video_url": request.video_url,
        "topic": request.topic
    }