"""BUG-AUDIO-DELIVERY-CORRELATION-001 — per-job deliverables manifest.

The compiler persists the three customer deliverable paths on the job row so a
consumer (rob-platform email-commander) attaches exactly this job's files,
correlated by job_id, instead of guessing from directory contents.
"""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Database
from app.routes import jobs as jobs_route
from app.services import compiler

MANIFEST = {
    "meeting_notes_pdf": "/out/j1/T - 2026-10-14 Meeting Notes.pdf",
    "transcript_pdf": "/out/j1/T - 2026-10-14 Transcript.pdf",
    "agent_ready_markdown": "/out/j1/T - 2026-10-14 Agent Ready Markdown.md",
}


def _columns(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [row[1] for row in conn.execute("PRAGMA table_info(jobs)")]
    finally:
        conn.close()


def test_migration_adds_deliverables_column_and_is_idempotent(tmp_path):
    db_path = tmp_path / "c.db"
    Database(str(db_path))
    Database(str(db_path))  # run twice: must not raise or duplicate
    cols = _columns(db_path)
    assert cols.count("deliverables") == 1


def test_migration_on_legacy_table_without_column(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE jobs (job_id TEXT PRIMARY KEY, request_id TEXT, company_id TEXT, "
        "task TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'received', audio_path TEXT, "
        "audio_duration_seconds REAL, audio_format TEXT, output_dir TEXT, error TEXT, "
        "created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT, total_duration_ms INTEGER)"
    )
    conn.execute("INSERT INTO jobs (job_id, task, status, created_at) VALUES ('old', 'compile_audio', 'completed', 'x')")
    conn.commit()
    conn.close()
    db = Database(str(db_path))
    assert "deliverables" in _columns(db_path)
    assert db.get_job("old")["deliverables"] is None


def test_complete_job_persists_manifest_as_json(tmp_path):
    db = Database(str(tmp_path / "c.db"))
    job_id = db.create_job("compile_audio")
    db.complete_job(job_id, total_duration_ms=5, output_dir="/out/j1", deliverables=MANIFEST)
    row = db.get_job(job_id)
    assert json.loads(row["deliverables"]) == MANIFEST
    assert row["output_dir"] == "/out/j1"


def test_complete_job_without_manifest_stays_null(tmp_path):
    db = Database(str(tmp_path / "c.db"))
    job_id = db.create_job("transcribe")
    db.complete_job(job_id, total_duration_ms=0, output_dir="/out/j2")
    assert db.get_job(job_id)["deliverables"] is None


def _get(db: Database, job_id: str) -> dict:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db)))
    return asyncio.run(jobs_route.get_job(job_id, request, _token="t"))


def test_job_route_returns_manifest_dict(tmp_path):
    db = Database(str(tmp_path / "c.db"))
    job_id = db.create_job("compile_audio")
    db.complete_job(job_id, total_duration_ms=5, output_dir="/out/j1", deliverables=MANIFEST)
    resp = _get(db, job_id)
    assert resp["success"] is True
    assert resp["job"]["deliverables"] == MANIFEST


def test_job_route_null_and_malformed_manifest_are_none(tmp_path):
    db = Database(str(tmp_path / "c.db"))
    legacy = db.create_job("compile_audio")
    db.complete_job(legacy, total_duration_ms=5, output_dir="/out/j3")
    assert _get(db, legacy)["job"]["deliverables"] is None

    bad = db.create_job("compile_audio")
    db._conn().execute("UPDATE jobs SET deliverables='{not json' WHERE job_id=?", (bad,))
    db._conn().commit()
    assert _get(db, bad)["job"]["deliverables"] is None


def test_manifest_keeps_only_the_three_deliverables():
    output_result = {**MANIFEST, "usage": {"x": 1}, "report_json": "/out/j1/report.json"}
    assert compiler._deliverables_manifest(output_result) == MANIFEST
    partial = {"meeting_notes_pdf": "/a.pdf", "transcript_pdf": None}
    assert compiler._deliverables_manifest(partial) == {"meeting_notes_pdf": "/a.pdf"}
    assert compiler._deliverables_manifest({}) == {}


def test_compile_audio_passes_manifest_to_complete_job():
    source = Path(compiler.__file__).read_text(encoding="utf-8")
    start = source.index("db.complete_job(")
    call = source[start:source.index(")\n", start)]
    assert "deliverables=_deliverables_manifest(output_result)" in call
