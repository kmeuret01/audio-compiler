"""Execution tracing — wraps every pipeline stage with timing and token tracking."""

import time
from typing import Any, Callable

from app.database import Database


# OpenAI pricing approximations (per 1M tokens)
_COST_TABLE = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "whisper-1": {"input": 0.0, "output": 0.0},  # Whisper billed per minute
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost in USD for an LLM call."""
    rates = _COST_TABLE.get(model, {"input": 0.0, "output": 0.0})
    return (prompt_tokens * rates["input"] + completion_tokens * rates["output"]) / 1_000_000


def summarize_output(result: Any, stage: str) -> str:
    """Produce a human-readable one-liner for the output_summary field."""
    if result is None:
        return "No output"

    if isinstance(result, dict):
        if "transcript" in result:
            words = len(result["transcript"].split())
            return f"Transcribed {words} words"
        if "attendees" in result:
            n = len(result.get("attendees", []))
            mt = result.get("meeting_type", "meeting")
            return f"Extracted: {n} attendees, type: {mt}"
        if "task" in result or (isinstance(result, list) and result and "task" in result[0]):
            items = result if isinstance(result, list) else [result]
            return f"Extracted {len(items)} action items"

    if isinstance(result, list):
        return f"Extracted {len(result)} items"

    if isinstance(result, str):
        words = len(result.split())
        if "topic title:" in result.lower():
            topics = result.lower().count("topic title:")
            return f"Generated {topics} topic sections, {words} words"
        return f"Generated {words} words"

    return str(result)[:100]


async def run_stage(
    job_id: str,
    stage_name: str,
    db: Database,
    func: Callable,
    *args: Any,
    input_summary: str = "",
    llm_model: str = "",
    **kwargs: Any,
) -> Any:
    """Execute a pipeline stage with full tracing."""
    stage_id = db.start_stage(job_id, stage_name, input_summary=input_summary)
    db.update_job_status(job_id, stage_name)
    start = time.monotonic()

    try:
        result = await func(*args, **kwargs)
        duration_ms = int((time.monotonic() - start) * 1000)

        # Extract token usage if present
        prompt_tokens = 0
        completion_tokens = 0
        if isinstance(result, dict) and "usage" in result:
            usage = result["usage"]
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

        cost = estimate_cost(llm_model, prompt_tokens, completion_tokens) if llm_model else 0.0

        db.complete_stage(
            stage_id,
            output_summary=summarize_output(result, stage_name),
            llm_model=llm_model,
            llm_prompt_tokens=prompt_tokens,
            llm_completion_tokens=completion_tokens,
            llm_cost_estimate=cost,
            duration_ms=duration_ms,
        )
        return result

    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        db.fail_stage(stage_id, error=str(e), duration_ms=duration_ms)
        db.fail_job(job_id, error=f"Failed at {stage_name}: {str(e)}")
        raise
