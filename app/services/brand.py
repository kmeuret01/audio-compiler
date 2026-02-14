"""GoAI Labs Brand System — shared across all output templates.

Custom fonts: DM Sans (body/heading) + Space Mono (monospace/accents).
Installed at /usr/local/share/fonts/goailabs/. Falls back to Helvetica/Courier
if registration fails.
"""

import logging
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

log = logging.getLogger("brand")

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

# ── Font Registration ───────────────────────────────────────────────────────

_FONT_DIR = Path("/usr/local/share/fonts/goailabs")
_CUSTOM_FONTS_OK = False

_FONT_MAP = {
    "DMSans": "DMSans-Regular.ttf",
    "DMSans-Bold": "DMSans-Bold.ttf",
    "DMSans-Italic": "DMSans-Italic.ttf",
    "SpaceMono": "SpaceMono-Regular.ttf",
    "SpaceMono-Bold": "SpaceMono-Bold.ttf",
}

try:
    for name, filename in _FONT_MAP.items():
        path = _FONT_DIR / filename
        if path.exists():
            pdfmetrics.registerFont(TTFont(name, str(path)))
        else:
            raise FileNotFoundError(f"Font file missing: {path}")
    _CUSTOM_FONTS_OK = True
    log.info("Custom GoAI Labs fonts registered (DM Sans + Space Mono)")
except Exception as e:
    log.warning("Custom fonts unavailable, falling back to Helvetica/Courier: %s", e)
    _CUSTOM_FONTS_OK = False

# Font constants — use custom fonts if available, else fallback
if _CUSTOM_FONTS_OK:
    FONT_HEADING = "DMSans-Bold"
    FONT_BODY = "DMSans"
    FONT_BODY_ITALIC = "DMSans-Italic"
    FONT_MONO = "SpaceMono"
    FONT_MONO_BOLD = "SpaceMono-Bold"
else:
    FONT_HEADING = "Helvetica-Bold"
    FONT_BODY = "Helvetica"
    FONT_BODY_ITALIC = "Helvetica-Oblique"
    FONT_MONO = "Courier"
    FONT_MONO_BOLD = "Courier-Bold"


def draw_logo(canvas_obj, x, y):
    """Draw the [AI] LABS logo mark at the given position."""
    c = canvas_obj
    # Bracket: [
    c.setFont(FONT_MONO, 16)
    c.setFillColor(BLACK)
    c.drawString(x, y, "[")
    # AI
    c.setFont(FONT_MONO_BOLD, 14)
    c.setFillColor(BLACK)
    c.drawString(x + 10, y + 1, "AI")
    # Bracket: ]
    c.setFont(FONT_MONO, 16)
    c.setFillColor(BLACK)
    c.drawString(x + 32, y, "]")
    # LABS
    c.setFont(FONT_HEADING, 14)
    c.setFillColor(ACCENT)
    c.drawString(x + 48, y + 1, "LABS")


def draw_header_footer(canvas_obj, doc, doc_type="DOCUMENT"):
    """Standard header/footer for all GoAI Labs PDFs."""
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
