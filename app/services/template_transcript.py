"""Transcript PDF Template — chaptered with speaker labels and topic TOC."""

from pathlib import Path
from typing import List

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT

from app.services.brand import (
    BLACK, WHITE, WARM_GRAY, MID_GRAY, DARK_GRAY, ACCENT, LIGHT_BG,
    FONT_HEADING, FONT_BODY, FONT_MONO, draw_header_footer
)

PAGE_W, PAGE_H = letter
LEFT_MARGIN = 0.75 * inch
RIGHT_MARGIN = 0.75 * inch
TOP_MARGIN = 0.9 * inch
BOTTOM_MARGIN = 0.7 * inch
CONTENT_WIDTH = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN


def _create_styles():
    """Create paragraph styles for the transcript."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='TranscriptTitle',
        fontName=FONT_HEADING,
        fontSize=16,
        leading=20,
        textColor=BLACK,
        spaceAfter=4,
    ))

    styles.add(ParagraphStyle(
        name='TranscriptMeta',
        fontName=FONT_MONO,
        fontSize=8,
        leading=10,
        textColor=MID_GRAY,
        spaceAfter=8,
    ))

    styles.add(ParagraphStyle(
        name='SectionHead',
        fontName=FONT_MONO,
        fontSize=8,
        leading=10,
        textColor=ACCENT,
        spaceBefore=12,
        spaceAfter=6,
    ))

    styles.add(ParagraphStyle(
        name='ChapterTitle',
        fontName=FONT_HEADING,
        fontSize=11,
        leading=14,
        textColor=DARK_GRAY,
        spaceBefore=16,
        spaceAfter=4,
    ))

    styles.add(ParagraphStyle(
        name='ChapterTimestamp',
        fontName=FONT_MONO,
        fontSize=8,
        leading=10,
        textColor=MID_GRAY,
    ))

    styles.add(ParagraphStyle(
        name='SpeakerName',
        fontName=FONT_HEADING,
        fontSize=9,
        leading=12,
        textColor=DARK_GRAY,
    ))

    styles.add(ParagraphStyle(
        name='Timestamp',
        fontName=FONT_MONO,
        fontSize=7,
        leading=10,
        textColor=MID_GRAY,
        alignment=TA_RIGHT,
    ))

    styles.add(ParagraphStyle(
        name='UtteranceText',
        fontName=FONT_BODY,
        fontSize=9,
        leading=12,
        textColor=DARK_GRAY,
        leftIndent=8,
        spaceAfter=8,
    ))

    styles.add(ParagraphStyle(
        name='TOCEntry',
        fontName=FONT_BODY,
        fontSize=9,
        leading=14,
        textColor=DARK_GRAY,
    ))

    styles.add(ParagraphStyle(
        name='TOCTimestamp',
        fontName=FONT_MONO,
        fontSize=8,
        leading=14,
        textColor=MID_GRAY,
    ))

    return styles


def generate_transcript(
    output_path: str,
    title: str,
    date: str,
    attendees: List[str],
    source_filename: str,
    chapters: List[dict],
) -> str:
    """
    Generate the branded Transcript PDF.

    Args:
        output_path: Where to save the PDF
        title: Meeting title
        date: Meeting date
        attendees: List of attendee names
        source_filename: Original audio filename
        chapters: List of dicts: {number, title, timestamp, utterances: [{speaker, timestamp, text}]}

    Returns:
        Path to generated PDF
    """
    styles = _create_styles()

    def header_footer(canvas, doc):
        draw_header_footer(canvas, doc, "FULL TRANSCRIPT")

    doc = BaseDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
    )

    frame = Frame(
        LEFT_MARGIN, BOTTOM_MARGIN,
        CONTENT_WIDTH, PAGE_H - TOP_MARGIN - BOTTOM_MARGIN,
        id='main'
    )

    template = PageTemplate(id='transcript', frames=[frame], onPage=header_footer)
    doc.addPageTemplates([template])

    story = []

    # Title
    story.append(Paragraph(title, styles['TranscriptTitle']))

    # Meta line
    attendees_str = ", ".join(attendees[:4])
    if len(attendees) > 4:
        attendees_str += f" +{len(attendees) - 4} more"
    meta_text = f"{date}  |  {attendees_str}  |  Source: {source_filename}"
    story.append(Paragraph(meta_text, styles['TranscriptMeta']))

    # Orange divider
    divider_table = Table([['']], colWidths=[CONTENT_WIDTH], rowHeights=[2])
    divider_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ACCENT),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(divider_table)
    story.append(Spacer(1, 12))

    # Table of Contents (Chapters)
    if chapters and len(chapters) > 1:
        story.append(Paragraph("CHAPTERS", styles['SectionHead']))

        toc_data = []
        for ch in chapters:
            ch_num = ch.get('number', 1)
            ch_title = ch.get('title', 'Untitled')
            ch_ts = ch.get('timestamp', '')

            toc_data.append([
                Paragraph(f"{ch_num}. {ch_title}", styles['TOCEntry']),
                Paragraph(ch_ts, styles['TOCTimestamp']),
            ])

        toc_table = Table(toc_data, colWidths=[CONTENT_WIDTH - 1*inch, 1*inch])
        toc_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, WARM_GRAY),
        ]))
        story.append(toc_table)
        story.append(Spacer(1, 16))

    # Chapters content
    for ch in chapters:
        ch_num = ch.get('number', 1)
        ch_title = ch.get('title', 'Untitled')
        ch_ts = ch.get('timestamp', '')
        utterances = ch.get('utterances', [])

        # Chapter header with number and timestamp label
        if ch_ts:
            header_text = f"CHAPTER {ch_num}: {ch_title}"
            story.append(Paragraph(header_text, styles['ChapterTitle']))
            story.append(Paragraph(f"[{ch_ts}]", styles['ChapterTimestamp']))
        else:
            header_text = f"CHAPTER {ch_num}: {ch_title}"
            story.append(Paragraph(header_text, styles['ChapterTitle']))

        story.append(Spacer(1, 6))

        # Utterances
        for utt in utterances:
            speaker = utt.get('speaker', 'Speaker')
            ts = utt.get('timestamp', '')
            text = utt.get('text', '')

            # Speaker line with timestamp
            if ts:
                speaker_row = Table(
                    [[
                        Paragraph(speaker, styles['SpeakerName']),
                        Paragraph(ts, styles['Timestamp']),
                    ]],
                    colWidths=[CONTENT_WIDTH - 1*inch, 1*inch]
                )
                speaker_row.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
                story.append(speaker_row)
            else:
                story.append(Paragraph(speaker, styles['SpeakerName']))

            # Utterance text
            story.append(Paragraph(text, styles['UtteranceText']))

    doc.build(story)
    return output_path


def generate_simple_transcript(
    output_path: str,
    title: str,
    date: str,
    attendees: List[str],
    source_filename: str,
    transcript_text: str,
) -> str:
    """
    Generate a simple transcript PDF when chaptering is not available.

    Args:
        output_path: Where to save the PDF
        title: Meeting title
        date: Meeting date
        attendees: List of attendee names
        source_filename: Original audio filename
        transcript_text: Raw transcript text

    Returns:
        Path to generated PDF
    """
    # Create a single chapter with the full transcript
    chapters = [{
        'number': 1,
        'title': 'Full Transcript',
        'timestamp': '',
        'utterances': [{
            'speaker': '',
            'timestamp': '',
            'text': transcript_text,
        }]
    }]

    return generate_transcript(
        output_path=output_path,
        title=title,
        date=date,
        attendees=attendees,
        source_filename=source_filename,
        chapters=chapters,
    )
