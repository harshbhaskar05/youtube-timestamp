import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

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


STOPWORDS = {
    "the", "is", "are", "a", "an", "and", "or", "of", "to", "in",
    "on", "for", "if", "you", "your", "we", "it", "this", "that",
    "with", "as", "at", "be", "can", "use"
}


def extract_video_id(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/)([^&?/]+)", url)
    if not match:
        raise ValueError("Invalid YouTube URL")
    return match.group(1)


def normalize(text: str):
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    words = [w for w in text.split() if w not in STOPWORDS]
    return words


def seconds_to_hhmmss(seconds: float):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"


def similarity_score(topic_words, text_words):
    if not topic_words:
        return 0
    overlap = sum(1 for word in topic_words if word in text_words)
    return overlap / len(topic_words)


@app.post("/ask")
def ask(request: AskRequest):

    try:
        video_id = extract_video_id(request.video_url)
        api = YouTubeTranscriptApi()

        # Try English first, fallback to auto
        try:
            transcript = api.fetch(video_id, languages=["en"])
        except:
            transcript = api.fetch(video_id)

    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
        return {
            "timestamp": "00:00:00",
            "video_url": request.video_url,
            "topic": request.topic
        }
    except Exception:
        return {
            "timestamp": "00:00:00",
            "video_url": request.video_url,
            "topic": request.topic
        }

    topic_words = normalize(request.topic)

    best_time = 0
    best_score = 0

    for i in range(len(transcript)):
        combined_text = transcript[i].text

        if i + 1 < len(transcript):
            combined_text += " " + transcript[i + 1].text
        if i + 2 < len(transcript):
            combined_text += " " + transcript[i + 2].text

        text_words = normalize(combined_text)
        score = similarity_score(topic_words, text_words)

        if score >= 0.6:
            return {
                "timestamp": seconds_to_hhmmss(transcript[i].start),
                "video_url": request.video_url,
                "topic": request.topic
            }

        if score > best_score:
            best_score = score
            best_time = transcript[i].start

    return {
        "timestamp": seconds_to_hhmmss(best_time),
        "video_url": request.video_url,
        "topic": request.topic
    }