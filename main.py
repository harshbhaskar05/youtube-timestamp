import os
import httpx
import json
import re
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi

# Load your token from .env
load_dotenv()
AIPIPE_TOKEN = os.getenv("AIPIPE_TOKEN")

app = FastAPI()

# Enable CORS (Required for browser-based testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request format
class AskRequest(BaseModel):
    video_url: str
    topic: str

# Response format
class AskResponse(BaseModel):
    timestamp: str
    video_url: str
    topic: str

def get_video_id(url: str) -> str:
    """Extracts the YouTube ID from a URL (e.g., https://youtu.be/dQw4w9WgXcQ -> dQw4w9WgXcQ)"""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"youtu\.be\/([0-9A-Za-z_-]{11})"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""

def format_seconds_to_hhmmss(seconds: float) -> str:
    """Converts 347 seconds to '00:05:47'"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

async def get_timestamp_with_ai(transcript: str, topic: str) -> str:
    """Sends the transcript and topic to Gemini to find the exact timestamp."""
    if not AIPIPE_TOKEN:
        return "00:00:00"

    prompt = f"""
I will give you a YouTube transcript with timestamps.
Find the moment where the following topic is first discussed: "{topic}"

TRANSCRIPT:
{transcript}

IMPORTANT: Your response must be a JSON object with a single key "timestamp" in "HH:MM:SS" format.
Example: {{"timestamp": "00:05:47"}}
"""

    url = "https://aipipe.org/geminiv1beta/models/gemini-2.0-flash-exp:generateContent"
    headers = {
        "x-goog-api-key": AIPIPE_TOKEN,
        "Content-Type": "application/json"
    }
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json"
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            
            data = response.json()
            ai_text = data["candidates"][0]["content"]["parts"][0]["text"]
            
            # Clean up the AI text
            ai_text = ai_text.strip().replace("```json", "").replace("```", "")
            result = json.loads(ai_text)
            return result.get("timestamp", "00:00:00")
    except Exception as e:
        print(f"AI Analysis failed: {e}")
        return "00:00:00"

@app.post("/ask", response_model=AskResponse)
async def ask_topic(request: AskRequest):
    # 1. Extract Video ID
    video_id = get_video_id(request.video_url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    # 2. Get Transcript
    try:
        raw_transcript = YouTubeTranscriptApi.get_transcript(video_id)
        # Format transcript: [00:01:23] This is the speech text...
        formatted_transcript = ""
        for entry in raw_transcript:
            time_str = format_seconds_to_hhmmss(entry['start'])
            formatted_transcript += f"[{time_str}] {entry['text']}\n"
    except Exception as e:
        print(f"Transcript Error: {e}")
        raise HTTPException(status_code=500, detail="Could not get transcript for this video.")

    # 3. Ask AI to find the topic in the transcript
    # (We only send the first 10,000 characters to avoid huge context limits)
    timestamp = await get_timestamp_with_ai(formatted_transcript[:10000], request.topic)
    
    return AskResponse(
        timestamp=timestamp,
        video_url=request.video_url,
        topic=request.topic
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
