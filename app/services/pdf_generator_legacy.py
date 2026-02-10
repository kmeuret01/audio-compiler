"""PDF generation — ported verbatim from audio_processor.py.

Styled PDFs with ROI Logistics branding.
"""

import json
import re
from pathlib import Path

from fpdf import FPDF

# PDF styling constants (unchanged from audio_processor.py)
COLOR_PRIMARY = (41, 65, 122)
COLOR_HEADING = (41, 65, 122)
COLOR_ACCENT = (79, 129, 189)
COLOR_TEXT = (51, 51, 51)
COLOR_LIGHT_BG = (235, 241, 250)


class StyledPDF(FPDF):
    """PDF with consistent header/footer styling.

    Formatting based on Plaud reference document:
    - Sans-serif (DejaVu Sans) for headers/titles
    - Serif (DejaVu Serif) for body text
    - Blue header only on first page
    - Italic conclusions
    - Blockquote styling for meeting info
    """

    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        self.doc_title = title
        self.doc_subtitle = subtitle
        self.set_auto_page_break(auto=True, margin=20)
        font_dir = "/usr/share/fonts/truetype/dejavu"
        self.add_font("DejaVu", "", f"{font_dir}/DejaVuSans.ttf")
        self.add_font("DejaVu", "B", f"{font_dir}/DejaVuSans-Bold.ttf")
        self.add_font("DejaVu", "I", f"{font_dir}/DejaVuSansMono-Oblique.ttf")
        self.add_font("DejaVuSerif", "", f"{font_dir}/DejaVuSerif.ttf")
        self.add_font("DejaVuSerif", "B", f"{font_dir}/DejaVuSerif-Bold.ttf")
        self.add_font("DejaVuSerif", "I", f"{font_dir}/DejaVuSansMono-Oblique.ttf")

    def header(self):
        if self.page_no() == 1:
            self.set_fill_color(*COLOR_PRIMARY)
            self.rect(0, 0, 210, 18, "F")
            self.set_font("DejaVu", "B", 11)
            self.set_text_color(255, 255, 255)
            self.set_xy(10, 4)
            self.cell(0, 10, self.doc_title)
            if self.doc_subtitle:
                self.set_font("DejaVu", "", 9)
                self.set_xy(10, 11)
                self.cell(0, 5, self.doc_subtitle)
            self.ln(20)
        else:
            self.set_font("DejaVu", "", 9)
            self.set_text_color(128, 128, 128)
            self.set_xy(10, 8)
            self.cell(0, 5, f"{self.doc_title}")
            self.set_draw_color(200, 200, 200)
            self.line(10, 15, 200, 15)
            self.ln(18)

    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", "I", 8)
        self.set_text_color(160, 160, 160)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}   |   ROI Logistics", align="C")

    def add_section_title(self, title: str):
        self.ln(4)
        self.set_font("DejaVu", "B", 16)
        self.set_text_color(*COLOR_HEADING)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def add_topic_title(self, title: str):
        self.ln(3)
        self.set_font("DejaVu", "B", 11)
        self.set_text_color(*COLOR_TEXT)
        self.cell(0, 7, f"\u2022  {title}", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def add_subsection_title(self, title: str):
        self.set_font("DejaVu", "B", 11)
        self.set_text_color(*COLOR_ACCENT)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def add_body_text(self, text: str):
        self.set_font("DejaVuSerif", "", 10)
        self.set_text_color(*COLOR_TEXT)
        self.set_x(14)
        self.multi_cell(0, 5.5, text)
        self.ln(3)

    def add_conclusion_text(self, text: str):
        self.set_font("DejaVuSerif", "I", 10)
        self.set_text_color(80, 80, 80)
        self.set_x(14)
        self.multi_cell(0, 5.5, text)
        self.ln(4)

    def add_bullet(self, text: str):
        self.set_font("DejaVuSerif", "", 10)
        self.set_text_color(*COLOR_TEXT)
        self.set_x(14)
        self.multi_cell(0, 5.5, f"\u2022  {text}")
        self.ln(1)

    def add_sub_bullet(self, text: str):
        self.set_font("DejaVuSerif", "", 10)
        self.set_text_color(*COLOR_TEXT)
        self.set_x(20)
        self.multi_cell(0, 5.5, f"\u25cb  {text}")
        self.ln(1)

    def add_checkbox_item(self, text: str):
        self.set_font("DejaVuSerif", "", 10)
        self.set_text_color(*COLOR_TEXT)
        self.set_x(14)
        self.multi_cell(0, 5.5, f"[ ]  {text}")
        self.ln(1)

    def add_numbered_item(self, number: int, text: str):
        self.set_font("DejaVuSerif", "", 10)
        self.set_text_color(*COLOR_TEXT)
        self.set_x(14)
        self.multi_cell(0, 5.5, f"{number}. {text}")
        self.ln(1)

    def add_key_value(self, key: str, value: str):
        self.set_font("DejaVu", "B", 10)
        self.set_text_color(*COLOR_HEADING)
        self.set_x(10)
        key_w = self.get_string_width(f"{key}: ") + 4
        self.cell(key_w, 6, f"{key}: ")
        self.set_font("DejaVuSerif", "", 10)
        self.set_text_color(*COLOR_TEXT)
        self.multi_cell(0, 6, value)

    def add_highlight_box(self, text: str):
        self.set_fill_color(*COLOR_LIGHT_BG)
        self.set_font("DejaVuSerif", "", 10)
        self.set_text_color(*COLOR_TEXT)
        self.multi_cell(190, 6, text, fill=True)
        self.ln(3)

    def add_blockquote(self, text: str):
        start_y = self.get_y()
        self.set_x(18)
        self.set_font("DejaVuSerif", "", 10)
        self.set_text_color(100, 100, 100)
        self.multi_cell(170, 6, text)
        end_y = self.get_y()
        self.set_draw_color(180, 180, 180)
        self.set_line_width(1.5)
        self.line(12, start_y, 12, end_y)
        self.ln(4)


def _parse_markdown_to_pdf(pdf: StyledPDF, markdown_text: str):
    """Render Plaud-style meeting notes into the styled PDF."""
    lines = markdown_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            pdf.ln(2)
            i += 1
            continue

        if stripped in ["Meeting Notes", "Next Arrangements", "Recommendations", "AI Suggestions"]:
            pdf.add_section_title(stripped)
            i += 1
            continue

        if stripped.startswith("Topic Title:"):
            title = stripped[12:].strip()
            pdf.add_topic_title(title)
            i += 1
            continue

        if stripped.lower().startswith("conclusion:"):
            text = stripped[11:].strip()
            pdf.add_conclusion_text(f"Conclusion: {text}")
            i += 1
            continue

        if stripped.startswith("[ ]") or stripped.startswith("[x]") or stripped.startswith("[X]"):
            text = stripped[3:].strip()
            pdf.add_checkbox_item(text)
            i += 1
            continue

        numbered_match = re.match(r'^(\d+)[.\)]\s+(.+)$', stripped)
        if numbered_match:
            num = int(numbered_match.group(1))
            text = numbered_match.group(2)
            pdf.add_numbered_item(num, text)
            i += 1
            continue

        if stripped.startswith("# "):
            pdf.add_section_title(stripped[2:].strip("*# "))
            i += 1
            continue
        elif stripped.startswith("## "):
            pdf.add_topic_title(stripped[3:].strip("*# "))
            i += 1
            continue
        elif stripped.startswith("### "):
            pdf.add_subsection_title(stripped[4:].strip("*# "))
            i += 1
            continue

        if stripped.startswith("\u25cb ") or stripped.startswith("o "):
            text = stripped[2:].strip().replace("**", "")
            pdf.add_sub_bullet(text)
            i += 1
            continue

        if stripped.startswith("- ") or stripped.startswith("\u2022 "):
            text = stripped[2:].strip().replace("**", "")
            pdf.add_bullet(text)
            i += 1
            continue

        if line.startswith("  - ") or line.startswith("    - "):
            text = stripped[2:].strip().replace("**", "")
            pdf.add_sub_bullet(text)
            i += 1
            continue

        if stripped.startswith("**") and ":**" in stripped:
            parts = stripped.split(":**", 1)
            key = parts[0].strip("* ")
            val = parts[1].strip(" *") if len(parts) > 1 else ""
            pdf.add_key_value(key, val)
            i += 1
            continue

        pdf.add_body_text(stripped.replace("**", ""))
        i += 1


def _add_metadata_block(pdf: StyledPDF, metadata: dict):
    """Add meeting info block with date, time, attendees."""
    date_str = metadata.get("date", "Unknown")
    time_str = metadata.get("time", "Unknown")
    attendees = metadata.get("attendees", [])
    attendees_str = ", ".join(attendees) if attendees else "Not identified"
    info_text = f"Date: {date_str}  |  Time: {time_str}\nAttendees: {attendees_str}"
    pdf.add_blockquote(info_text)
    pdf.ln(4)


def generate_meeting_notes_pdf(notes: str, filename: str, output_path: Path, metadata: dict | None = None):
    """Create a styled PDF from meeting notes markdown."""
    pdf = StyledPDF("Meeting Notes", filename)
    pdf.alias_nb_pages()
    pdf.add_page()
    if metadata:
        _add_metadata_block(pdf, metadata)
    _parse_markdown_to_pdf(pdf, notes)
    pdf.output(str(output_path))


def generate_action_items_pdf(items_json: str, filename: str, output_path: Path, metadata: dict | None = None):
    """Create a styled PDF from action items JSON."""
    pdf = StyledPDF("Action Items", filename)
    pdf.alias_nb_pages()
    pdf.add_page()
    if metadata:
        _add_metadata_block(pdf, metadata)

    try:
        items = json.loads(items_json)
    except json.JSONDecodeError:
        pdf.add_body_text(items_json)
        pdf.output(str(output_path))
        return

    if not items:
        pdf.add_highlight_box("No specific action items were identified in this recording.")
        pdf.output(str(output_path))
        return

    for i, item in enumerate(items, 1):
        pdf.add_subsection_title(f"Action Item #{i}")
        pdf.add_key_value("Task", item.get("task", "N/A"))
        pdf.add_key_value("Assignee", item.get("assignee") or "Unassigned")
        pdf.add_key_value("Deadline", item.get("deadline") or "Not specified")
        priority = item.get("priority", "medium").capitalize()
        pdf.add_key_value("Priority", priority)
        pdf.ln(4)

    pdf.output(str(output_path))


def generate_transcript_pdf(transcript: str, filename: str, output_path: Path, metadata: dict | None = None):
    """Create a styled PDF from the raw transcript."""
    pdf = StyledPDF("Full Transcript", filename)
    pdf.alias_nb_pages()
    pdf.add_page()
    if metadata:
        _add_metadata_block(pdf, metadata)
    pdf.add_section_title("Transcript")
    pdf.set_font("DejaVuSerif", "", 10)
    pdf.set_text_color(*COLOR_TEXT)
    pdf.multi_cell(0, 5.5, transcript)
    pdf.output(str(output_path))
