# Audio Compiler Module

## Overview
Standalone FastAPI microservice that compiles audio recordings into structured meeting documentation.
Extracted from the Rob 2.0 platform as the first Universal Module Blueprint implementation.

## Architecture
- FastAPI on port 8150 (behind Nginx at compiler.roilogistics.ai)
- SQLite database for job tracking and execution tracing
- 7-step pipeline: transcribe → metadata → notes → actions → summary → review → PDFs
- Bearer token authentication on all endpoints except /health

## Key Files
- `app/main.py` — FastAPI app with lifespan
- `app/services/compiler.py` — The 7-step pipeline
- `app/services/transcription.py` — Whisper API client
- `app/services/pdf_generator.py` — Branded PDF generation
- `app/database.py` — SQLite with jobs, stages, feedback tables
- `app/tracing.py` — Stage execution wrapper with timing/tokens

## LLM Prompts
All 5 LLM prompts are preserved verbatim from the Rob platform's audio_processor.py.
Do NOT modify them without explicit approval.

## Environment
- Python 3.12+, venv at /home/clawdbot/audio-compiler/venv
- Dependencies in requirements.txt
- Config via .env (see .env.example)
- Uses `python3` everywhere
