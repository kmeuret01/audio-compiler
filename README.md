# Audio Compiler Module

ROI Logistics audio compilation pipeline — transcribe, analyze, and generate branded PDFs from audio recordings.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /health | No | Module health and status |
| GET | /capabilities | Bearer | What this module can do |
| POST | /execute | Bearer | Run compile_audio or transcribe_only |
| GET | /jobs/{id} | Bearer | Job status |
| GET | /jobs/{id}/trace | Bearer | Full stage-by-stage execution trace |
| POST | /feedback | Bearer | Submit quality feedback |

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your keys
uvicorn app.main:app --host 127.0.0.1 --port 8150
```

## Pipeline

1. **Transcription** — OpenAI Whisper API
2. **Metadata extraction** — Date, time, attendees (LLM)
3. **Meeting notes** — Topic-by-topic format (LLM)
4. **Action items** — Structured JSON with owners/deadlines (LLM)
5. **Executive summary** — Under 300 words (LLM)
6. **Quality review** — Best practices check (LLM)
7. **PDF generation** — 3 branded PDFs with ROI Logistics styling
