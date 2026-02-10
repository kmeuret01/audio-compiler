"""AI Labs Brand System — shared across all output templates."""

from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch

# Brand Colors as reportlab HexColor objects
BLACK = HexColor("#0A0A0A")
WHITE = HexColor("#FAFAF9")
WARM_GRAY = HexColor("#E8E5E0")
MID_GRAY = HexColor("#9B9590")
DARK_GRAY = HexColor("#2D2926")
ACCENT = HexColor("#C85A2A")
ACCENT_LIGHT = HexColor("#E8704A")
ACCENT_SUBTLE = HexColor("#FFF3EE")
LIGHT_BG = HexColor("#F5F3F0")

# Brand color hex values for non-reportlab use
COLORS_HEX = {
    "black": "#0A0A0A",
    "white": "#FAFAF9",
    "warm_gray": "#E8E5E0",
    "mid_gray": "#9B9590",
    "dark_gray": "#2D2926",
    "accent": "#C85A2A",
    "accent_light": "#E8704A",
    "accent_subtle": "#FFF3EE",
    "light_bg": "#F5F3F0",
}

# Fonts (reportlab built-ins)
FONT_HEADING = "Helvetica-Bold"
FONT_BODY = "Helvetica"
FONT_MONO = "Courier"
FONT_MONO_BOLD = "Courier-Bold"


def draw_logo(canvas_obj, x, y):
    """Draw the [ ] AI LABS logo mark at the given position."""
    c = canvas_obj
    c.setFont(FONT_MONO_BOLD, 14)
    c.setFillColor(ACCENT)
    c.drawString(x, y, "[ ]")

    c.setFont(FONT_MONO_BOLD, 12)
    c.setFillColor(BLACK)
    c.drawString(x + 28, y + 1, "AI")

    c.setFont(FONT_BODY, 8)
    c.setFillColor(MID_GRAY)
    c.drawString(x + 48, y + 1, "LABS")


def draw_header_footer(canvas_obj, doc, doc_type="DOCUMENT"):
    """Standard header/footer for all AI Labs PDFs."""
    from reportlab.lib.pagesizes import letter
    PAGE_W, PAGE_H = letter
    LEFT_MARGIN = 0.75 * inch
    RIGHT_MARGIN = 0.75 * inch

    c = canvas_obj
    c.saveState()

    # Header
    y_header = PAGE_H - 0.55 * inch
    draw_logo(c, LEFT_MARGIN, y_header)

    c.setFont(FONT_MONO, 7.5)
    c.setFillColor(MID_GRAY)
    c.drawRightString(PAGE_W - RIGHT_MARGIN, y_header + 1, doc_type)

    c.setStrokeColor(WARM_GRAY)
    c.setLineWidth(0.5)
    c.line(LEFT_MARGIN, y_header - 8, PAGE_W - RIGHT_MARGIN, y_header - 8)

    # Footer
    y_footer = 0.45 * inch
    c.setStrokeColor(WARM_GRAY)
    c.setLineWidth(0.5)
    c.line(LEFT_MARGIN, y_footer + 10, PAGE_W - RIGHT_MARGIN, y_footer + 10)

    c.setFont(FONT_MONO, 7)
    c.setFillColor(MID_GRAY)
    c.drawString(LEFT_MARGIN, y_footer, "goailabs.ai")
    c.drawCentredString(PAGE_W / 2, y_footer, "CONFIDENTIAL")
    c.drawRightString(PAGE_W - RIGHT_MARGIN, y_footer, f"Page {doc.page}")

    c.restoreState()
