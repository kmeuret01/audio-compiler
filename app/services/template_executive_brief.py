"""Executive Brief PDF Template — 1-2 page BLUF + execution board."""

from pathlib import Path
from typing import List, Tuple

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

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
    """Create paragraph styles for the executive brief."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='BriefTitle',
        fontName=FONT_HEADING,
        fontSize=16,
        leading=20,
        textColor=BLACK,
        spaceAfter=4,
    ))

    styles.add(ParagraphStyle(
        name='BriefMeta',
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
        spaceAfter=4,
    ))

    styles.add(ParagraphStyle(
        name='BriefBody',
        fontName=FONT_BODY,
        fontSize=9.5,
        leading=13,
        textColor=DARK_GRAY,
        spaceAfter=6,
    ))

    styles.add(ParagraphStyle(
        name='BulletItem',
        fontName=FONT_BODY,
        fontSize=9,
        leading=12,
        textColor=DARK_GRAY,
        leftIndent=12,
        spaceAfter=3,
    ))

    styles.add(ParagraphStyle(
        name='StepTitle',
        fontName=FONT_HEADING,
        fontSize=9,
        leading=11,
        textColor=WHITE,
    ))

    styles.add(ParagraphStyle(
        name='StepItem',
        fontName=FONT_BODY,
        fontSize=8.5,
        leading=11,
        textColor=DARK_GRAY,
        leftIndent=8,
    ))

    styles.add(ParagraphStyle(
        name='ContextLabel',
        fontName=FONT_HEADING,
        fontSize=8.5,
        leading=11,
        textColor=DARK_GRAY,
    ))

    styles.add(ParagraphStyle(
        name='ContextText',
        fontName=FONT_BODY,
        fontSize=8.5,
        leading=11,
        textColor=DARK_GRAY,
    ))

    return styles


def generate_executive_brief(
    output_path: str,
    title: str,
    date: str,
    attendees: List[str],
    duration: str,
    bluf: str,
    decisions: List[str],
    execution_steps: List[dict],
    context_items: List[Tuple[str, str]],
) -> str:
    """
    Generate the Executive Brief PDF.

    Args:
        output_path: Where to save the PDF
        title: Meeting title
        date: Meeting date
        attendees: List of attendee names
        duration: Estimated duration string
        bluf: Bottom Line Up Front text (2-4 sentences)
        decisions: List of key decision strings
        execution_steps: List of dicts: {num, title, tag, items: [str]}
        context_items: List of (bold_label, text) tuples

    Returns:
        Path to generated PDF
    """
    styles = _create_styles()

    def header_footer(canvas, doc):
        draw_header_footer(canvas, doc, "EXECUTIVE BRIEF")

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

    template = PageTemplate(id='brief', frames=[frame], onPage=header_footer)
    doc.addPageTemplates([template])

    story = []

    # Title
    story.append(Paragraph(title, styles['BriefTitle']))

    # Meta line
    attendees_str = ", ".join(attendees[:4])
    if len(attendees) > 4:
        attendees_str += f" +{len(attendees) - 4} more"
    meta_text = f"{date}  |  {duration}  |  {attendees_str}"
    story.append(Paragraph(meta_text, styles['BriefMeta']))

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

    # BOTTOM LINE UP FRONT
    story.append(Paragraph("BOTTOM LINE UP FRONT", styles['SectionHead']))
    story.append(Paragraph(bluf, styles['BriefBody']))

    # KEY DECISIONS
    if decisions:
        story.append(Paragraph("KEY DECISIONS", styles['SectionHead']))
        for decision in decisions:
            story.append(Paragraph(f"• {decision}", styles['BulletItem']))

    # EXECUTION BOARD
    if execution_steps:
        story.append(Paragraph("EXECUTION BOARD", styles['SectionHead']))
        story.append(Spacer(1, 4))

        for step in execution_steps:
            step_num = step.get('num', '0')
            step_title = step.get('title', '')
            step_tag = step.get('tag', '')
            step_items = step.get('items', [])

            # Header bar color: Step 0 = accent, others = dark gray
            header_bg = ACCENT if str(step_num) == '0' else DARK_GRAY

            # Step header
            header_text = f"STEP {step_num}: {step_title}"
            if step_tag:
                header_text += f"  [{step_tag}]"

            header_table = Table(
                [[Paragraph(header_text, styles['StepTitle'])]],
                colWidths=[CONTENT_WIDTH],
                rowHeights=[18]
            )
            header_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), header_bg),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(header_table)

            # Step items in light gray box
            if step_items:
                item_rows = []
                for item in step_items:
                    item_rows.append([Paragraph(f"• {item}", styles['StepItem'])])

                items_table = Table(item_rows, colWidths=[CONTENT_WIDTH])
                items_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
                    ('LEFTPADDING', (0, 0), (-1, -1), 12),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                story.append(items_table)

            story.append(Spacer(1, 6))

    # CONTEXT
    if context_items:
        story.append(Paragraph("CONTEXT", styles['SectionHead']))
        for label, text in context_items:
            context_para = Paragraph(
                f"<b>{label}:</b> {text}",
                styles['ContextText']
            )
            story.append(context_para)
            story.append(Spacer(1, 2))

    doc.build(story)
    return output_path
