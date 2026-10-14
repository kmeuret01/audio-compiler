"""Render tests for the three customer deliverables. No network."""

from app.services.deliverables import (
    assemble_report,
    cues_from_segments,
    cues_from_srt,
    is_present_person,
    recording_date,
    render_agent_markdown,
    write_deliverables,
)


SRT = """1
00:00:01,000 --> 00:00:03,000
1-A: Hello there.

2
00:00:03,000 --> 00:00:05,000
1-A: Second line.

3
00:00:06,000 --> 00:00:08,000
2-B: A reply.
"""


def test_recording_date_prefers_filename_when_stated_unknown():
    iso, display, note = recording_date("2026-10-08_15_20_52.mp3", "Unknown")
    assert iso == "2026-10-08"
    assert display == "October 8, 2026"
    assert note == "recording date"


def test_recording_date_uses_a_real_stated_date():
    iso, _, note = recording_date("2026-10-08_15_20_52.mp3", "December 5, 2018")
    assert iso == "2018-12-05"
    assert note == "stated in the meeting"


def test_discussed_names_in_metadata_stay_off_the_attendee_line():
    report = assemble_report(
        {"present": ["Kevin", "Derek", "Matt Mathis", "Greg"], "bluf": "A specific offer."},
        {
            "title": "Planning",
            "date": "Unknown",
            "attendees": [
                "Derek (discussed, not present)",
                "Matt Mathis (discussed, not present)",
            ],
        },
        "2026-10-08_15_20_52.mp3",
        600,
    )
    assert report["present"] == ["Kevin", "Greg"]


def test_present_people_drop_speaker_chunks_and_discussed_names():
    assert is_present_person("Speaker 1-A") is False
    assert is_present_person("1-A") is False
    assert is_present_person("Derek (discussed, not present)") is False
    assert is_present_person("Kevin") is True


def test_srt_merges_consecutive_turns_from_the_same_speaker():
    cues = cues_from_srt(SRT)
    assert len(cues) == 2
    assert cues[0]["speaker"] == "Speaker 1-A"
    assert cues[0]["start"] == "00:00:01"
    assert "Second line" in cues[0]["text"]
    assert cues[1]["speaker"] == "Speaker 2-B"


def test_segments_become_timestamped_cues():
    cues = cues_from_segments([
        {"start": 12.4, "text": "Lock the date.", "speaker": "Kevin"},
        {"start": 18, "text": "Agreed.", "speaker": "Kevin"},
    ])
    assert len(cues) == 1
    assert cues[0]["start"] == "00:00:12"
    assert cues[0]["text"] == "Lock the date. Agreed."


def test_agent_markdown_holds_the_full_transcript_and_frontmatter():
    report = assemble_report(
        {
            "title": "Ignored when metadata has a title",
            "bluf": "The group set a year-end goal.",
            "decisions": [{"text": "Price stays at retail minus ten percent.", "why": "Opti-Port members get the discount."}],
            "actions": [{"owner": "Kevin", "task": "Confirm October 19", "due": "ASAP", "priority": "high"}],
            "open_questions": ["How long does the course stay relevant?"],
            "present": ["Speaker 1-A", "Kevin"],
        },
        {"title": "AI Adoption Strategy and Business Development Meeting", "date": "Unknown", "attendees": ["Speaker 1-A"]},
        "2026-10-08_15_20_52.mp3",
        2532,
    )
    cues = cues_from_srt(SRT)
    text = render_agent_markdown(report, cues, "0bea50ab-7c6")
    assert text.startswith("---\n")
    assert 'title: "AI Adoption Strategy and Business Development Meeting"' in text
    assert "date: 2026-10-08" in text
    assert "producer: goailabs.ai" in text
    assert "- Kevin" in text or '  - "Kevin"' in text
    assert "Speaker 1-A" not in text.split("## Transcript")[0]
    assert "### 00:00:01 — Speaker 1-A" in text
    assert "A reply." in text
    assert "How long does the course stay relevant?" in text


def test_write_deliverables_names(tmp_path):
    report = assemble_report(
        {"bluf": "A short bottom line.", "decisions": [], "actions": [], "open_questions": [], "present": []},
        {"title": "October Planning", "date": "Unknown"},
        "2026-10-08_16_08_49.mp3",
        382,
    )
    cues = [{"start": "00:01:00", "speaker": "Speaker 1-A", "text": "Hello."}]
    paths = write_deliverables(tmp_path, report, cues, "job-1")
    assert paths["meeting_notes_pdf"].endswith("October Planning - 2026-10-08 Meeting Notes.pdf")
    assert paths["transcript_pdf"].endswith("October Planning - 2026-10-08 Transcript.pdf")
    assert paths["agent_ready_markdown"].endswith("October Planning - 2026-10-08 Agent Ready Markdown.md")
    notes = open(paths["meeting_notes_pdf"], "rb").read(8)
    transcript = open(paths["transcript_pdf"], "rb").read(8)
    assert notes.startswith(b"%PDF")
    assert transcript.startswith(b"%PDF")
    markdown = open(paths["agent_ready_markdown"], encoding="utf-8").read()
    assert "Hello." in markdown
    assert "goailabs.ai" in markdown
