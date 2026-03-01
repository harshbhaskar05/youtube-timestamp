# YouTube Topic Timestamp Finder (Question 7)

This project is a FastAPI service that helps you find the exact moment a topic or phrase is spoken in a YouTube video.

## 🚀 ELI15: How it Works (Step-by-Step)

Imagine you have a long video lesson and you only want to find the part where the teacher talks about "Photosynthesis."

1.  **The User sends a request:** You provide a YouTube URL and the topic you're looking for to the `/ask` endpoint.
2.  **The Transcript Scout:** Instead of downloading the whole video (which is slow), we use a "Scout" (the `YouTubeTranscriptApi`) to grab the captions or subtitles. This is much faster!
3.  **The Time-Stamper:** We format these captions so they look like a script with time markers (e.g., `[00:05:10] The plant takes in sunlight...`).
4.  **The AI Brain:** We give this script to **Google Gemini** (via the AI Pipe proxy) and ask: "Where is the topic mentioned?"
5.  **The Final Answer:** The AI identifies the exact time, and we send it back to you in `HH:MM:SS` format.

---

## 🛠️ How to Set it Up (Novice Friendly)

### 1. Install the Libraries
Open your terminal in the `question7` folder and run:
```bash
pip install -r requirements.txt
```

### 2. Configure your Token
Ensure your `AIPIPE_TOKEN` is set in the `.env` file inside this folder.

### 3. Run the Server
Run the following command:
```bash
python main.py
```
The server will start on `http://localhost:8001`.

### 4. Test it!
Use `curl` or Postman:
```bash
curl -X POST "http://localhost:8001/ask" 
     -H "Content-Type: application/json" 
     -d '{"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "topic": "never gonna give you up"}'
```

---

## 📂 File Explanations
*   **`main.py`**: The main FastAPI application.
*   **`.env`**: Stores your secret AI Pipe token.
*   **`.gitignore`**: Tells Git not to upload your secret token.
*   **`requirements.txt`**: The list of tools (libraries) needed.
