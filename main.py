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
    intersection = set_a & set_b
    union = set_a | set_b
    if not union:
        return 0
    return len(intersection) / len(union)


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

    topic_words = normalize(request.topic)
    topic_string = " ".join(topic_words)

    best_score = 0
    best_time = 0

    for i in range(len(transcript)):

        # Merge 4 segments (captures split phrases)
        combined_text = transcript[i].text
        for j in range(1, 4):
            if i + j < len(transcript):
                combined_text += " " + transcript[i + j].text

        text_words = normalize(combined_text)
        text_string = " ".join(text_words)

        # 1️⃣ Jaccard similarity
        score = jaccard_similarity(topic_words, text_words)

        # 2️⃣ Boost if phrase substring appears
        if topic_string in text_string:
            score += 0.4

        # 3️⃣ Boost if most words appear
        overlap = sum(1 for w in topic_words if w in text_words)
        if len(topic_words) > 0 and overlap / len(topic_words) > 0.7:
            score += 0.3

        if score > best_score:
            best_score = score
            best_time = transcript[i].start

        # Early confident return
        if score >= 0.75:
            return {
                "timestamp": seconds_to_hhmmss(transcript[i].start),
                "video_url": request.video_url,
                "topic": request.topic
            }

    return {
        "timestamp": seconds_to_hhmmss(best_time),
        "video_url": request.video_url,
        "topic": request.topic
    }