"""SQLite database for job tracking, stage tracing, and feedback."""

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thread-safe SQLite wrapper for the compiler module."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                request_id TEXT,
                company_id TEXT DEFAULT 'roi-logistics',
                task TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'received',
                audio_path TEXT,
                audio_duration_seconds REAL,
                audio_format TEXT,
                output_dir TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                total_duration_ms INTEGER,
                -- Notification tracking columns
                notification_status TEXT DEFAULT 'pending',
                notification_attempts INTEGER DEFAULT 0,
                notification_error TEXT,
                thread_id TEXT
            );

            CREATE TABLE IF NOT EXISTS job_stages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(job_id),
                stage TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'started',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_ms INTEGER,
                input_summary TEXT,
                output_summary TEXT,
                llm_model TEXT,
                llm_prompt_tokens INTEGER,
                llm_completion_tokens INTEGER,
                llm_cost_estimate REAL,
                error TEXT,
                was_bypassed BOOLEAN DEFAULT FALSE,
                bypass_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                company_id TEXT DEFAULT 'roi-logistics',
                feedback_type TEXT NOT NULL,
                issue TEXT NOT NULL,
                details TEXT,
                source TEXT DEFAULT 'slack',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_stages_job ON job_stages(job_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_feedback_job ON feedback(job_id);
        """)
        conn.commit()

    # ── Jobs ──────────────────────────────────────────────────────────

    def create_job(
        self,
        task: str,
        request_id: str = "",
        company_id: str = "roi-logistics",
        audio_path: str = "",
        audio_format: str = "",
        thread_id: str = "",
    ) -> str:
        job_id = str(uuid4())[:12]
        self._conn().execute(
            "INSERT INTO jobs (job_id, request_id, company_id, task, status, audio_path, audio_format, created_at, thread_id) "
            "VALUES (?, ?, ?, ?, 'received', ?, ?, ?, ?)",
            (job_id, request_id, company_id, task, audio_path, audio_format, _now(), thread_id),
        )
        self._conn().commit()
        return job_id

    def update_job_status(self, job_id: str, status: str) -> None:
        updates = {"status": status}
        if status == "processing" and not self._get_field(job_id, "started_at"):
            updates["started_at"] = _now()
        sets = ", ".join(f"{k} = ?" for k in updates)
        self._conn().execute(
            f"UPDATE jobs SET {sets} WHERE job_id = ?",
            (*updates.values(), job_id),
        )
        self._conn().commit()

    def complete_job(self, job_id: str, total_duration_ms: int, output_dir: str = "", audio_duration: float = 0) -> None:
        self._conn().execute(
            "UPDATE jobs SET status='completed', completed_at=?, total_duration_ms=?, output_dir=?, audio_duration_seconds=? WHERE job_id=?",
            (_now(), total_duration_ms, output_dir, audio_duration, job_id),
        )
        self._conn().commit()

    def fail_job(self, job_id: str, error: str) -> None:
        self._conn().execute(
            "UPDATE jobs SET status='failed', completed_at=?, error=? WHERE job_id=?",
            (_now(), error, job_id),
        )
        self._conn().commit()

    # ── Notification Tracking ──────────────────────────────────────────

    def get_pending_notifications(self, limit: int = 10) -> list:
        """Get completed jobs that haven't been notified yet."""
        cursor = self._conn().execute("""
            SELECT job_id, output_dir, submitter_email, submitter_name, thread_id
            FROM jobs
            WHERE status = 'completed'
              AND notification_status = 'pending'
              AND submitter_email IS NOT NULL
              AND submitter_email != ''
            ORDER BY completed_at ASC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def mark_notification_sent(self, job_id: str) -> None:
        """Mark a job's notification as successfully sent."""
        self._conn().execute(
            "UPDATE jobs SET notification_status='sent' WHERE job_id=?",
            (job_id,),
        )
        self._conn().commit()

    def mark_notification_failed(self, job_id: str, error: str) -> None:
        """Record a failed notification attempt."""
        self._conn().execute("""
            UPDATE jobs SET
                notification_attempts = notification_attempts + 1,
                notification_error = ?,
                notification_status = CASE
                    WHEN notification_attempts >= 2 THEN 'failed'
                    ELSE 'pending'
                END
            WHERE job_id = ?
        """, (error, job_id))
        self._conn().commit()

    def get_failed_jobs_for_notification(self, limit: int = 10) -> list:
        """Get failed jobs that haven't been notified yet."""
        cursor = self._conn().execute("""
            SELECT job_id, error, submitter_email, submitter_name, thread_id
            FROM jobs
            WHERE status = 'failed'
              AND notification_status = 'pending'
              AND submitter_email IS NOT NULL
              AND submitter_email != ''
            ORDER BY completed_at ASC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_job(self, job_id: str) -> Optional[dict]:
        row = self._conn().execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def get_job_counts(self, hours: int = 24) -> dict:
        """Get job counts for the last N hours."""
        cutoff = datetime.now(timezone.utc).isoformat()
        total = self._conn().execute(
            "SELECT COUNT(*) FROM jobs WHERE created_at >= datetime('now', ?)",
            (f"-{hours} hours",),
        ).fetchone()[0]
        completed = self._conn().execute(
            "SELECT COUNT(*) FROM jobs WHERE status='completed' AND created_at >= datetime('now', ?)",
            (f"-{hours} hours",),
        ).fetchone()[0]
        failed = self._conn().execute(
            "SELECT COUNT(*) FROM jobs WHERE status='failed' AND created_at >= datetime('now', ?)",
            (f"-{hours} hours",),
        ).fetchone()[0]
        return {"total_24h": total, "completed_24h": completed, "failed_24h": failed}

    # ── Stages ────────────────────────────────────────────────────────

    def start_stage(self, job_id: str, stage: str, input_summary: str = "") -> int:
        cur = self._conn().execute(
            "INSERT INTO job_stages (job_id, stage, status, started_at, input_summary) VALUES (?, ?, 'started', ?, ?)",
            (job_id, stage, _now(), input_summary),
        )
        self._conn().commit()
        return cur.lastrowid

    def complete_stage(
        self,
        stage_id: int,
        output_summary: str = "",
        llm_model: str = "",
        llm_prompt_tokens: int = 0,
        llm_completion_tokens: int = 0,
        llm_cost_estimate: float = 0.0,
        duration_ms: int = 0,
    ) -> None:
        self._conn().execute(
            "UPDATE job_stages SET status='completed', completed_at=?, duration_ms=?, "
            "output_summary=?, llm_model=?, llm_prompt_tokens=?, llm_completion_tokens=?, llm_cost_estimate=? "
            "WHERE id=?",
            (_now(), duration_ms, output_summary, llm_model, llm_prompt_tokens, llm_completion_tokens, llm_cost_estimate, stage_id),
        )
        self._conn().commit()

    def fail_stage(self, stage_id: int, error: str, duration_ms: int = 0) -> None:
        self._conn().execute(
            "UPDATE job_stages SET status='failed', completed_at=?, duration_ms=?, error=? WHERE id=?",
            (_now(), duration_ms, error, stage_id),
        )
        self._conn().commit()

    def skip_stage(self, job_id: str, stage: str, bypass_reason: str = "") -> int:
        cur = self._conn().execute(
            "INSERT INTO job_stages (job_id, stage, status, started_at, completed_at, duration_ms, was_bypassed, bypass_reason) "
            "VALUES (?, ?, 'skipped', ?, ?, 0, TRUE, ?)",
            (job_id, stage, _now(), _now(), bypass_reason),
        )
        self._conn().commit()
        return cur.lastrowid

    def get_trace(self, job_id: str) -> dict:
        job = self.get_job(job_id)
        if not job:
            return {}
        stages = self._conn().execute(
            "SELECT * FROM job_stages WHERE job_id=? ORDER BY id", (job_id,)
        ).fetchall()
        return {
            **job,
            "stages": [dict(s) for s in stages],
        }

    # ── Feedback ──────────────────────────────────────────────────────

    def save_feedback(
        self,
        feedback_type: str,
        issue: str,
        job_id: str = "",
        company_id: str = "roi-logistics",
        details: str = "",
        source: str = "slack",
    ) -> int:
        cur = self._conn().execute(
            "INSERT INTO feedback (job_id, company_id, feedback_type, issue, details, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, company_id, feedback_type, issue, details, source, _now()),
        )
        self._conn().commit()
        return cur.lastrowid

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_field(self, job_id: str, field: str):
        row = self._conn().execute(f"SELECT {field} FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return row[0] if row else None
