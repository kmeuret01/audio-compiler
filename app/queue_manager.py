"""
Audio Compiler Queue Manager
============================
Drop-in queue management layer for the ROI Logistics audio compiler.

Architecture:
- Single async worker loop processes one job at a time (no concurrency)
- SQLite-backed queue for crash resilience
- Jobs are enqueued instantly and acknowledged immediately
- Worker picks up oldest queued job, processes it, then picks up the next
- /queue endpoint provides real-time visibility into queue state
- Stale job detection and recovery on startup
"""

import asyncio
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable
from enum import Enum

logger = logging.getLogger("queue_manager")


class JobStatus(str, Enum):
    """Job lifecycle statuses."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def _wal_connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode to match the Database class.

    All connections to compiler.db MUST use WAL mode. Mixing journal modes
    (WAL vs default/delete) causes 'database disk image is malformed' errors.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def migrate_database(db_path: str):
    """Add queue management columns to the existing jobs table."""
    conn = _wal_connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(jobs)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    new_columns = {
        "priority": "INTEGER DEFAULT 0",
        "queued_at": "TEXT",
        "retry_count": "INTEGER DEFAULT 0",
        "max_retries": "INTEGER DEFAULT 2",
        "estimated_duration_seconds": "INTEGER",
        "submitter_email": "TEXT",
        "submitter_name": "TEXT",
        "file_size_bytes": "INTEGER",
        # Notification tracking columns
        "notification_status": "TEXT DEFAULT 'pending'",
        "notification_attempts": "INTEGER DEFAULT 0",
        "notification_error": "TEXT",
        "thread_id": "TEXT",
        "overrides_json": "TEXT DEFAULT ''",
    }

    for col_name, col_def in new_columns.items():
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_def}")
                logger.info(f"Added column: {col_name}")
            except sqlite3.OperationalError as e:
                logger.warning(f"Column {col_name} may already exist: {e}")

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_queue_order
        ON jobs(status, priority DESC, queued_at ASC)
    """)

    conn.commit()
    conn.close()
    logger.info("Database migration complete.")


class QueueManager:
    """Manages the job queue for the audio compiler."""

    def __init__(
        self,
        db_path: str,
        process_job_func: Optional[Callable[[str, str], Awaitable[bool]]] = None
    ):
        self.db_path = db_path
        self.process_job_func = process_job_func
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._job_available = asyncio.Event()

        # Duration estimation constants
        self.BYTES_PER_SECOND_ESTIMATE = 16000
        self.TRANSCRIPTION_SPEED_RATIO = 0.1
        self.OVERHEAD_SECONDS = 60

        # Rate limiting: minimum gap between jobs to respect OpenAI rate limits
        self.JOB_SPACING_SECONDS = 30
        self._last_job_end = 0

    async def startup(self):
        """Call this on FastAPI startup event."""
        migrate_database(self.db_path)
        self._recover_stale_jobs()
        self._shutdown_event.clear()
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Queue manager started. Worker loop running.")

        if self._count_queued_jobs() > 0:
            self._job_available.set()

    async def shutdown(self):
        """Call this on FastAPI shutdown event."""
        logger.info("Queue manager shutting down...")
        self._shutdown_event.set()
        self._job_available.set()

        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=1800)
            except asyncio.TimeoutError:
                logger.warning("Worker did not finish within 30 minutes. Cancelling.")
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass

        logger.info("Queue manager stopped.")

    async def enqueue_job(
        self,
        job_id: str,
        audio_path: str,
        submitter_email: str = "",
        submitter_name: str = "",
        file_size_bytes: int = 0,
        priority: int = 0,
        thread_id: str = "",
        overrides_json: str = "",
    ) -> dict:
        """Add a job to the queue. Returns immediately with queue position."""
        now = datetime.now(timezone.utc).isoformat()
        estimated_duration = self._estimate_duration(file_size_bytes)

        conn = _wal_connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE jobs SET
                status = ?,
                priority = ?,
                queued_at = ?,
                estimated_duration_seconds = ?,
                submitter_email = ?,
                submitter_name = ?,
                file_size_bytes = ?,
                thread_id = ?,
                overrides_json = ?
            WHERE job_id = ?
        """, (
            JobStatus.QUEUED.value,
            priority,
            now,
            estimated_duration,
            submitter_email,
            submitter_name,
            file_size_bytes,
            thread_id,
            overrides_json,
            job_id,
        ))

        queue_position = self._get_queue_position(cursor, job_id)
        estimated_wait = self._estimate_wait_time(cursor)

        conn.commit()
        conn.close()

        self._job_available.set()

        result = {
            "job_id": job_id,
            "status": JobStatus.QUEUED.value,
            "queue_position": queue_position,
            "estimated_wait_seconds": estimated_wait,
            "estimated_duration_seconds": estimated_duration,
            "message": self._build_queue_message(queue_position, estimated_wait),
        }

        logger.info(
            f"Job {job_id} enqueued. Position: {queue_position}, "
            f"Est. wait: {estimated_wait}s, Submitter: {submitter_name or submitter_email}"
        )

        return result

    async def _worker_loop(self):
        """Single worker that processes one job at a time."""
        logger.info("Worker loop started.")
        import time

        while not self._shutdown_event.is_set():
            # Enforce minimum spacing between jobs to respect rate limits
            if self._last_job_end > 0:
                elapsed = time.time() - self._last_job_end
                if elapsed < self.JOB_SPACING_SECONDS:
                    wait_time = self.JOB_SPACING_SECONDS - elapsed
                    logger.info(f"Rate limit spacing: waiting {wait_time:.1f}s before next job")
                    await asyncio.sleep(wait_time)

            job = self._get_next_job()

            if job is None:
                self._job_available.clear()
                try:
                    await asyncio.wait_for(self._job_available.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    pass
                continue

            job_id, audio_path, overrides_json = job
            logger.info(f"Worker picked up job {job_id}: {audio_path}")

            self._update_job_status(job_id, JobStatus.PROCESSING.value)

            try:
                if self.process_job_func:
                    success = await self.process_job_func(job_id, audio_path, overrides_json)
                else:
                    logger.error(f"No process_job_func set! Job {job_id} cannot be processed.")
                    success = False

                if success:
                    self._update_job_status(job_id, JobStatus.COMPLETED.value)
                    logger.info(f"Job {job_id} completed successfully.")
                else:
                    self._handle_job_failure(job_id, "Processing returned failure")

            except Exception as e:
                logger.exception(f"Job {job_id} failed with exception: {e}")
                self._handle_job_failure(job_id, str(e))

            # Record job end time for rate limiting
            self._last_job_end = time.time()
            await asyncio.sleep(1)

        logger.info("Worker loop exiting (shutdown signal received).")

    def _handle_job_failure(self, job_id: str, error_message: str):
        """Handle a failed job — retry if under max_retries, otherwise mark failed."""
        conn = _wal_connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT retry_count, max_retries FROM jobs WHERE job_id = ?",
            (job_id,)
        )
        row = cursor.fetchone()

        if row is None:
            conn.close()
            return

        retry_count, max_retries = row
        retry_count = retry_count or 0
        max_retries = max_retries or 2

        if retry_count < max_retries:
            new_retry_count = retry_count + 1
            cursor.execute("""
                UPDATE jobs SET
                    status = ?,
                    retry_count = ?,
                    error = ?,
                    started_at = NULL
                WHERE job_id = ?
            """, (JobStatus.QUEUED.value, new_retry_count, error_message, job_id))

            logger.warning(
                f"Job {job_id} failed (attempt {new_retry_count}/{max_retries}). "
                f"Re-queued. Error: {error_message}"
            )
        else:
            cursor.execute("""
                UPDATE jobs SET
                    status = ?,
                    error = ?,
                    completed_at = ?
                WHERE job_id = ?
            """, (
                JobStatus.FAILED.value,
                error_message,
                datetime.now(timezone.utc).isoformat(),
                job_id,
            ))

            logger.error(
                f"Job {job_id} permanently failed after {max_retries} attempts. "
                f"Error: {error_message}"
            )

        conn.commit()
        conn.close()

    def _recover_stale_jobs(self):
        """On startup, find and re-queue jobs that were mid-processing when service died."""
        conn = _wal_connect(self.db_path)
        cursor = conn.cursor()

        # Find jobs stuck in processing state
        cursor.execute(
            "SELECT job_id, status, audio_path FROM jobs WHERE status = ?",
            (JobStatus.PROCESSING.value,)
        )
        stale_jobs = cursor.fetchall()

        if not stale_jobs:
            logger.info("No stale jobs found on startup.")
            conn.close()
            return

        logger.warning(f"Found {len(stale_jobs)} stale jobs from previous run. Re-queuing...")

        now = datetime.now(timezone.utc).isoformat()
        for job_id, old_status, audio_path in stale_jobs:
            cursor.execute("""
                UPDATE jobs SET
                    status = ?,
                    queued_at = ?,
                    started_at = NULL,
                    retry_count = COALESCE(retry_count, 0) + 1,
                    error = ?
                WHERE job_id = ?
            """, (
                JobStatus.QUEUED.value,
                now,
                f"Recovered from stale state '{old_status}' after service restart",
                job_id,
            ))
            logger.info(f"Re-queued stale job {job_id} (was: {old_status})")

        conn.commit()
        conn.close()

    def get_queue_status(self) -> dict:
        """Returns full queue state for the /queue endpoint."""
        conn = _wal_connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Currently processing job
        cursor.execute("""
            SELECT job_id, status, audio_path, started_at,
                   estimated_duration_seconds, submitter_email, submitter_name,
                   file_size_bytes
            FROM jobs
            WHERE status = ?
            ORDER BY started_at DESC LIMIT 1
        """, (JobStatus.PROCESSING.value,))
        processing_row = cursor.fetchone()
        currently_processing = dict(processing_row) if processing_row else None

        if currently_processing and currently_processing.get("started_at"):
            started = datetime.fromisoformat(currently_processing["started_at"])
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            currently_processing["elapsed_seconds"] = int(elapsed)

        # Queued jobs
        cursor.execute("""
            SELECT job_id, audio_path, queued_at, priority,
                   estimated_duration_seconds, submitter_email, submitter_name,
                   file_size_bytes, retry_count
            FROM jobs
            WHERE status = ?
            ORDER BY priority DESC, queued_at ASC
        """, (JobStatus.QUEUED.value,))
        queued_jobs = [dict(row) for row in cursor.fetchall()]

        for i, job in enumerate(queued_jobs):
            job["position"] = i + 1

        estimated_total_wait = self._estimate_wait_time(cursor)

        # Recent completed
        cursor.execute("""
            SELECT job_id, audio_path, completed_at, started_at,
                   submitter_email, submitter_name
            FROM jobs
            WHERE status = ?
            ORDER BY completed_at DESC LIMIT 5
        """, (JobStatus.COMPLETED.value,))
        recent_completed = [dict(row) for row in cursor.fetchall()]

        for job in recent_completed:
            if job.get("started_at") and job.get("completed_at"):
                started = datetime.fromisoformat(job["started_at"])
                completed = datetime.fromisoformat(job["completed_at"])
                job["actual_duration_seconds"] = int((completed - started).total_seconds())

        # Recent failed
        cursor.execute("""
            SELECT job_id, audio_path, error, retry_count,
                   submitter_email, submitter_name
            FROM jobs
            WHERE status = ?
            ORDER BY completed_at DESC LIMIT 5
        """, (JobStatus.FAILED.value,))
        recent_failed = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return {
            "queue_length": len(queued_jobs),
            "currently_processing": currently_processing,
            "queued_jobs": queued_jobs,
            "estimated_total_wait_seconds": estimated_total_wait,
            "estimated_total_wait_human": self._seconds_to_human(estimated_total_wait),
            "recent_completed": recent_completed,
            "recent_failed": recent_failed,
        }

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get detailed status of a specific job."""
        conn = _wal_connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()

        if row is None:
            conn.close()
            return None

        result = dict(row)

        if result.get("status") == JobStatus.QUEUED.value:
            result["queue_position"] = self._get_queue_position(cursor, job_id)
            result["estimated_wait_seconds"] = self._estimate_wait_for_job(cursor, job_id)

        if result.get("started_at") and result.get("status") not in (
            JobStatus.COMPLETED.value, JobStatus.FAILED.value
        ):
            started = datetime.fromisoformat(result["started_at"])
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            result["elapsed_seconds"] = int(elapsed)

        conn.close()
        return result

    def set_priority(self, job_id: str, priority: int) -> bool:
        """Change a queued job's priority."""
        conn = _wal_connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE jobs SET priority = ? WHERE job_id = ? AND status = ?",
            (priority, job_id, JobStatus.QUEUED.value)
        )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if updated:
            logger.info(f"Job {job_id} priority set to {priority}")
        return updated

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a QUEUED job."""
        conn = _wal_connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE jobs SET status = ?, error = 'Cancelled by user' "
            "WHERE job_id = ? AND status = ?",
            (JobStatus.FAILED.value, job_id, JobStatus.QUEUED.value)
        )
        cancelled = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if cancelled:
            logger.info(f"Job {job_id} cancelled.")
        return cancelled

    def _get_next_job(self) -> Optional[tuple]:
        """Get the next job to process. Returns (job_id, audio_path, overrides_json)."""
        conn = _wal_connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT job_id, audio_path, COALESCE(overrides_json, '') FROM jobs
            WHERE status = ?
            ORDER BY priority DESC, queued_at ASC
            LIMIT 1
        """, (JobStatus.QUEUED.value,))

        row = cursor.fetchone()
        conn.close()
        return row

    def _update_job_status(self, job_id: str, status: str):
        """Update job status."""
        conn = _wal_connect(self.db_path)
        cursor = conn.cursor()

        if status == JobStatus.PROCESSING.value:
            cursor.execute(
                "UPDATE jobs SET status = ?, started_at = ? WHERE job_id = ?",
                (status, datetime.now(timezone.utc).isoformat(), job_id)
            )
        else:
            cursor.execute(
                "UPDATE jobs SET status = ? WHERE job_id = ?",
                (status, job_id)
            )

        conn.commit()
        conn.close()

    def _count_queued_jobs(self) -> int:
        conn = _wal_connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = ?", (JobStatus.QUEUED.value,))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def _get_queue_position(self, cursor, job_id: str) -> int:
        """Get 1-based position of a job in the queue."""
        cursor.execute("""
            SELECT job_id FROM jobs
            WHERE status = ?
            ORDER BY priority DESC, queued_at ASC
        """, (JobStatus.QUEUED.value,))

        for i, row in enumerate(cursor.fetchall()):
            if row[0] == job_id:
                return i + 1
        return 0

    def _estimate_duration(self, file_size_bytes: int) -> int:
        """Estimate processing duration based on file size."""
        if file_size_bytes <= 0:
            return 300

        audio_seconds = file_size_bytes / self.BYTES_PER_SECOND_ESTIMATE
        transcription_time = audio_seconds * self.TRANSCRIPTION_SPEED_RATIO
        total = transcription_time + self.OVERHEAD_SECONDS

        return max(int(total), 60)

    def _estimate_wait_time(self, cursor) -> int:
        """Estimate total wait time for someone joining the queue now."""
        total_wait = 0

        # Time remaining on current processing job
        cursor.execute("""
            SELECT started_at, estimated_duration_seconds
            FROM jobs WHERE status = ?
            ORDER BY started_at DESC LIMIT 1
        """, (JobStatus.PROCESSING.value,))

        row = cursor.fetchone()
        if row:
            started_at, est_duration = row
            if started_at and est_duration:
                started = datetime.fromisoformat(started_at)
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                remaining = max(0, est_duration - elapsed)
                total_wait += remaining

        # Sum of all queued job durations
        cursor.execute("""
            SELECT COALESCE(SUM(estimated_duration_seconds), 0)
            FROM jobs WHERE status = ?
        """, (JobStatus.QUEUED.value,))

        queued_sum = cursor.fetchone()[0]
        total_wait += queued_sum

        return int(total_wait)

    def _estimate_wait_for_job(self, cursor, job_id: str) -> int:
        """Estimate wait time for a specific queued job."""
        total_wait = 0

        # Time remaining on current processing job
        cursor.execute("""
            SELECT started_at, estimated_duration_seconds
            FROM jobs WHERE status = ?
            ORDER BY started_at DESC LIMIT 1
        """, (JobStatus.PROCESSING.value,))

        row = cursor.fetchone()
        if row:
            started_at, est_duration = row
            if started_at and est_duration:
                started = datetime.fromisoformat(started_at)
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                remaining = max(0, est_duration - elapsed)
                total_wait += remaining

        # Sum durations of jobs ahead of this one
        cursor.execute("""
            SELECT job_id, estimated_duration_seconds, priority, queued_at
            FROM jobs WHERE status = ?
            ORDER BY priority DESC, queued_at ASC
        """, (JobStatus.QUEUED.value,))

        for row in cursor.fetchall():
            if row[0] == job_id:
                break
            total_wait += (row[1] or 300)

        return int(total_wait)

    def _build_queue_message(self, position: int, wait_seconds: int) -> str:
        """Build human-friendly queue message."""
        if position == 1:
            return "Your file is next in line. Processing will begin shortly."

        wait_human = self._seconds_to_human(wait_seconds)
        return (
            f"Got it — your file is #{position} in the queue. "
            f"Estimated wait: {wait_human}. "
            f"You'll receive your transcript via email when it's ready."
        )

    @staticmethod
    def _seconds_to_human(seconds: int) -> str:
        """Convert seconds to human-readable duration."""
        if seconds < 60:
            return "less than a minute"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"~{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"~{hours} hour{'s' if hours != 1 else ''} {minutes} min"
            return f"~{hours} hour{'s' if hours != 1 else ''}"
