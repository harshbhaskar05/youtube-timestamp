import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "live"}


class AskRequest(BaseModel):
    video_url: str
    topic: str


def extract_video_id(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/)([^&?/]+)", url)
    if not match:
        raise ValueError("Invalid YouTube URL")
    return match.group(1)


def seconds_to_hhmmss(seconds: float):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"


@app.post("/ask")
def ask(request: AskRequest):

    video_id = extract_video_id(request.video_url)

    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id)

    topic_lower = request.topic.lower()

    for entry in transcript:
        text = entry.text.lower()
        if topic_lower in text:
            timestamp = seconds_to_hhmmss(entry.start)
            return {
                "timestamp": timestamp,
                "video_url": request.video_url,
                "topic": request.topic
            }

    return {
        "timestamp": "00:00:00",
        "video_url": request.video_url,
        "topic": request.topic
    }