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
    "with", "as", "at", "be", "can", "use", "whatever"
}


# ----------------------------
# Helpers
# ----------------------------

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


def jaccard_similarity(a, b):
    set_a = set(a)
    set_b = set(b)
    if not set_a and not set_b:
        return 0
    return len(set_a & set_b) / len(set_a | set_b)


# ----------------------------
# Main Endpoint
# ----------------------------

@app.post("/ask")
def ask(request: AskRequest):

    try:
        video_id = extract_video_id(request.video_url)
        api = YouTubeTranscriptApi()

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

    # Build full word stream with timestamps
    full_words = []
    word_timestamps = []

    for entry in transcript:
        words = normalize(entry.text)
        for w in words:
            full_words.append(w)
            word_timestamps.append(entry.start)

    topic_words = normalize(request.topic)

    if not topic_words or not full_words:
        return {
            "timestamp": "00:00:00",
            "video_url": request.video_url,
            "topic": request.topic
        }

    window_size = len(topic_words)
    best_score = 0
    best_time = 0

    # Sliding window search
    for i in range(len(full_words) - window_size + 1):
        window = full_words[i:i + window_size]
        score = jaccard_similarity(topic_words, window)

        if score > best_score:
            best_score = score
            best_time = word_timestamps[i]

    return {
        "timestamp": seconds_to_hhmmss(best_time),
        "video_url": request.video_url,
        "topic": request.topic
    }