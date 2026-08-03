"""Configuration — Pydantic settings loaded from .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    module_name: str = "audio-compiler"
    module_version: str = "1.0.0"
    host: str = "127.0.0.1"
    port: int = 8150

    compiler_module_token: str = ""
    openai_api_key: str = ""

    rob_platform_url: str = "http://127.0.0.1:8000"
    upload_dir: str = "/home/clawdbot/audio-compiler/uploads"
    output_dir: str = "/home/clawdbot/audio-compiler/output"
    db_path: str = "/home/clawdbot/audio-compiler/compiler.db"

    max_file_size_mb: int = 100
    whisper_model: str = "whisper-1"
    whisper_timeout: int = 1200
    # FEAT-AUDIO-DIARIZE-001: diarized stage-1 transcription (speaker attribution).
    # Feature-flagged; on any diarize failure the transcriber falls back to whisper_model.
    use_diarization: bool = True
    transcribe_model: str = "gpt-4o-transcribe-diarize"
    transcribe_response_format: str = "diarized_json"
    transcribe_chunking_strategy: str = "auto"
    transcribe_prompt: str = ""  # optional vocabulary/name hint passed to the model
    llm_model: str = "gpt-4o-mini"
    llm_timeout: int = 120

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
