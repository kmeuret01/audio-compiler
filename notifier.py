#!/usr/bin/env python3
"""
Audio Compiler Notification Service
====================================

Standalone daemon that watches for completed jobs and sends email notifications.
This decouples the notification from the processing pipeline, providing resilience
against service restarts and allowing immediate acknowledgment to users.

Usage:
    python3 notifier.py              # run daemon
    python3 notifier.py --once       # single check and exit
    python3 notifier.py --dry-run    # check without sending emails
"""

import argparse
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Configuration
POLL_INTERVAL_SECONDS = 30
DB_PATH = os.environ.get("COMPILER_DB", "/home/clawdbot/audio-compiler/compiler.db")
GOG_BIN = os.environ.get("GOG_BIN", "/home/clawdbot/homebrew/bin/gog")
GOG_ACCOUNT = os.environ.get("GOG_ACCOUNT", "rob@roilogistics.ai")
LOG_FILE = os.environ.get("NOTIFIER_LOG", "/var/log/audio-notifier.log")

# Graceful shutdown
_running = True


def _shutdown(signum, frame):
    global _running
    logging.info("Received signal %s, shutting down gracefully...", signum)
    _running = False


def setup_logging(log_file: str) -> logging.Logger:
    """Configure logging to file and stdout."""
    log = logging.getLogger("audio-notifier")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    log.addHandler(stdout_handler)

    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(fmt)
        log.addHandler(file_handler)
    except PermissionError:
        log.warning("Cannot write to %s, logging to stdout only", log_file)

    return log


def gog_env() -> dict:
    """Build environment for gog commands."""
    return {
        **os.environ,
        "HOME": "/home/clawdbot",
        "GOG_KEYRING_PASSWORD": os.environ.get("GOG_KEYRING_PASSWORD", ""),
        "GOG_ACCOUNT": GOG_ACCOUNT,
    }


def _wal_connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode to match the compiler's Database class.

    All connections to compiler.db MUST use WAL mode. Mixing journal modes
    causes 'database disk image is malformed' errors.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_pending_notifications(db_path: str, limit: int = 10) -> list:
    """Get completed jobs that haven't been notified."""
    conn = _wal_connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT job_id, output_dir, submitter_email, submitter_name, thread_id
        FROM jobs
        WHERE status = 'completed'
          AND notification_status = 'pending'
          AND submitter_email IS NOT NULL
          AND submitter_email != ''
        ORDER BY completed_at ASC
        LIMIT ?
    """, (limit,))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_failed_jobs_for_notification(db_path: str, limit: int = 10) -> list:
    """Get failed jobs that haven't been notified."""
    conn = _wal_connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT job_id, error, submitter_email, submitter_name, thread_id
        FROM jobs
        WHERE status = 'failed'
          AND notification_status = 'pending'
          AND submitter_email IS NOT NULL
          AND submitter_email != ''
        ORDER BY completed_at ASC
        LIMIT ?
    """, (limit,))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def mark_notification_sent(db_path: str, job_id: str) -> None:
    """Mark a job's notification as successfully sent."""
    conn = _wal_connect(db_path)
    conn.execute(
        "UPDATE jobs SET notification_status='sent' WHERE job_id=?",
        (job_id,),
    )
    conn.commit()
    conn.close()


def mark_notification_failed(db_path: str, job_id: str, error: str) -> None:
    """Record a failed notification attempt."""
    conn = _wal_connect(db_path)
    conn.execute("""
        UPDATE jobs SET
            notification_attempts = notification_attempts + 1,
            notification_error = ?,
            notification_status = CASE
                WHEN notification_attempts >= 2 THEN 'failed'
                ELSE 'pending'
            END
        WHERE job_id = ?
    """, (error, job_id))
    conn.commit()
    conn.close()


def build_completion_email_body(job: dict, output_dir: Path) -> str:
    """Build the HTML email body for a completed job."""
    name = job.get("submitter_name") or "there"

    # Try to read email_body.html if it exists
    email_body_path = output_dir / "email_body.html"
    if email_body_path.exists():
        return email_body_path.read_text(encoding="utf-8")

    # Fallback: build simple completion message
    return f"""<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333;">
<p>Hi {name},</p>

<p>Your meeting debrief is ready. I've attached the documents:</p>

<ul>
<li><strong>Executive Brief</strong> - One-page summary for quick review</li>
<li><strong>Full Debrief</strong> - Complete notes with all details</li>
<li><strong>Transcript</strong> - Full transcription of the audio</li>
</ul>

<p>Let me know if you need any changes.</p>

<p style="color: #666;">— Rob</p>
</body>
</html>"""


def build_failure_email_body(job: dict) -> str:
    """Build the email body for a failed job notification."""
    name = job.get("submitter_name") or "there"
    error = job.get("error", "Unknown error")

    return f"""<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333;">
<p>Hi {name},</p>

<p>I ran into an issue processing your audio file.</p>

<p><strong>Error:</strong> {error[:500]}</p>

<p>You can try:</p>
<ul>
<li>Sending the file again</li>
<li>Trying a different audio format (MP3, M4A, WAV)</li>
<li>Replying to this email with any questions</li>
</ul>

<p style="color: #666;">— Rob</p>
</body>
</html>"""


def send_completion_email(
    job: dict,
    log: logging.Logger,
    dry_run: bool = False,
) -> bool:
    """Send the completion email with attachments."""
    job_id = job["job_id"]
    output_dir = Path(job["output_dir"]) if job.get("output_dir") else None
    email = job["submitter_email"]
    thread_id = job.get("thread_id")

    if not output_dir or not output_dir.exists():
        log.error("Job %s: output_dir missing or does not exist: %s", job_id, output_dir)
        return False

    # Build email body
    email_body = build_completion_email_body(job, output_dir)

    # Collect attachments (PDFs and DOCX)
    attachments = []
    for pattern in ["*.pdf", "*.docx"]:
        attachments.extend(output_dir.glob(pattern))

    # Filter to expected files
    expected_names = [
        "executive_brief.pdf",
        "full_debrief.docx",
        "transcript.pdf",
    ]
    attachments = [
        a for a in attachments
        if a.name in expected_names
    ]

    log.info("Job %s: sending to %s with %d attachments", job_id, email, len(attachments))

    if dry_run:
        log.info("[DRY RUN] Would send email to %s", email)
        return True

    # Build gog command
    cmd = [
        GOG_BIN, "gmail", "send",
        "--to", email,
        "--subject", "Your Meeting Debrief is Ready",
        "--body-html", email_body,
        "--account", GOG_ACCOUNT,
        "--no-input",
    ]

    # Add thread for reply-in-thread
    if thread_id:
        cmd.extend(["--thread-id", thread_id])

    # Add attachments
    for att in attachments:
        cmd.extend(["--attach", str(att)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=gog_env(),
            timeout=60,
        )

        if result.returncode != 0:
            log.error("Job %s: gog send failed: %s", job_id, result.stderr)
            return False

        log.info("Job %s: email sent successfully", job_id)
        return True

    except subprocess.TimeoutExpired:
        log.error("Job %s: gog send timed out", job_id)
        return False
    except Exception as e:
        log.exception("Job %s: unexpected error sending email: %s", job_id, e)
        return False


def send_failure_email(
    job: dict,
    log: logging.Logger,
    dry_run: bool = False,
) -> bool:
    """Send failure notification email."""
    job_id = job["job_id"]
    email = job["submitter_email"]
    thread_id = job.get("thread_id")

    email_body = build_failure_email_body(job)

    log.info("Job %s (failed): sending notification to %s", job_id, email)

    if dry_run:
        log.info("[DRY RUN] Would send failure notification to %s", email)
        return True

    # Build gog command
    cmd = [
        GOG_BIN, "gmail", "send",
        "--to", email,
        "--subject", "Issue Processing Your Audio File",
        "--body-html", email_body,
        "--account", GOG_ACCOUNT,
        "--no-input",
    ]

    if thread_id:
        cmd.extend(["--thread-id", thread_id])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=gog_env(),
            timeout=60,
        )

        if result.returncode != 0:
            log.error("Job %s: gog send failed: %s", job_id, result.stderr)
            return False

        log.info("Job %s: failure notification sent", job_id)
        return True

    except subprocess.TimeoutExpired:
        log.error("Job %s: gog send timed out", job_id)
        return False
    except Exception as e:
        log.exception("Job %s: unexpected error: %s", job_id, e)
        return False


def poll_once(db_path: str, log: logging.Logger, dry_run: bool = False) -> int:
    """Run a single notification poll cycle. Returns count of notifications sent."""
    sent_count = 0

    # Process completed jobs
    pending = get_pending_notifications(db_path)
    if pending:
        log.info("Found %d completed jobs with pending notifications", len(pending))

    for job in pending:
        job_id = job["job_id"]
        success = send_completion_email(job, log, dry_run=dry_run)

        if not dry_run:
            if success:
                mark_notification_sent(db_path, job_id)
                sent_count += 1
            else:
                mark_notification_failed(db_path, job_id, "Email send failed")

    # Process failed jobs
    failed = get_failed_jobs_for_notification(db_path)
    if failed:
        log.info("Found %d failed jobs with pending notifications", len(failed))

    for job in failed:
        job_id = job["job_id"]
        success = send_failure_email(job, log, dry_run=dry_run)

        if not dry_run:
            if success:
                mark_notification_sent(db_path, job_id)
                sent_count += 1
            else:
                mark_notification_failed(db_path, job_id, "Email send failed")

    return sent_count


def main():
    parser = argparse.ArgumentParser(description="Audio Compiler Notification Service")
    parser.add_argument("--once", action="store_true", help="Run single poll and exit")
    parser.add_argument("--dry-run", action="store_true", help="Poll without sending")
    parser.add_argument("--db", default=DB_PATH, help="Path to SQLite database")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL_SECONDS,
                        help="Poll interval in seconds")
    args = parser.parse_args()

    log = setup_logging(LOG_FILE)
    log.info("Audio Notifier starting up")
    log.info("Database: %s", args.db)
    log.info("Poll interval: %ds", args.interval)
    log.info("gog binary: %s", GOG_BIN)
    log.info("Account: %s", GOG_ACCOUNT)

    if not Path(args.db).exists():
        log.error("Database not found: %s", args.db)
        sys.exit(1)

    if args.once:
        log.info("Running single poll cycle")
        sent = poll_once(args.db, log, dry_run=args.dry_run)
        log.info("Poll complete. Sent %d notification(s)", sent)
        return

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("Entering poll loop...")

    while _running:
        try:
            poll_once(args.db, log, dry_run=args.dry_run)
        except Exception as e:
            log.exception("Unexpected error in poll cycle: %s", e)

        # Sleep in 1-second increments for responsive shutdown
        for _ in range(args.interval):
            if not _running:
                break
            time.sleep(1)

    log.info("Audio Notifier shut down")


if __name__ == "__main__":
    main()
