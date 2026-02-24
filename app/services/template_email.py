"""Email Body HTML Template — branded, brief meeting debrief for email clients."""

import re
from typing import List

# Brand colors for inline CSS
COLORS = {
    "black": "#0A0A0A",
    "white": "#FAFAF9",
    "warm_gray": "#E8E5E0",
    "mid_gray": "#9B9590",
    "dark_gray": "#2D2926",
    "accent": "#C85A2A",
    "accent_subtle": "#FFF3EE",
    "light_bg": "#F5F3F0",
}

FONT_STACK = "'DM Sans', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO_STACK = "'Space Mono', 'Courier New', Consolas, monospace"

# ── Content limits — keep the email scannable in 30 seconds ──────────
_BLUF_MAX_CHARS = 220
_DECISION_MAX_CHARS = 100
_STEP_MAX_CHARS = 100
_MAX_DECISIONS = 4
_MAX_STEPS = 3
_UNKNOWN_VALUES = {"unknown", "n/a", "none", ""}


def _truncate(text: str, limit: int) -> str:
    """Truncate text to *limit* chars, breaking at the last word boundary."""
    text = text.strip()
    if len(text) <= limit:
        return text
    truncated = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return truncated + "..."


def _clean_step(text: str) -> str:
    """Strip '→ None' / '→ TBD' artifacts and tidy whitespace."""
    text = re.sub(r'\s*→\s*(None|TBD|N/A)\s*$', '', text, flags=re.IGNORECASE)
    return text.strip()


def _clean_attendee(name: str) -> str:
    """Strip parenthetical noise like '(discussed, not present)' from names."""
    return re.sub(r'\s*\([^)]*\)', '', name).strip()


def _is_known(value: str) -> bool:
    return value.strip().lower() not in _UNKNOWN_VALUES


def generate_email_body(
    title: str,
    date: str,
    attendees: List[str],
    duration: str,
    bluf: str,
    decisions: List[str],
    execution_steps: List[dict],
) -> str:
    """
    Generate a branded, concise HTML email body.

    Designed to be scannable in 30 seconds — high-points only.
    Full details live in the attached PDF/DOCX.
    """
    # ── Clean attendees ──────────────────────────────────────────────
    clean_attendees = [
        _clean_attendee(a) for a in attendees
        if _is_known(_clean_attendee(a))
    ]
    attendees_str = ", ".join(clean_attendees[:4])
    if len(clean_attendees) > 4:
        attendees_str += f" +{len(clean_attendees) - 4} more"

    # ── Meta line — skip unknown fields ──────────────────────────────
    meta_parts = []
    if _is_known(date):
        meta_parts.append(date)
    if _is_known(duration):
        meta_parts.append(duration)
    if attendees_str:
        meta_parts.append(attendees_str)
    meta_str = " &nbsp;|&nbsp; ".join(meta_parts) if meta_parts else ""

    # ── Truncate BLUF ────────────────────────────────────────────────
    bluf_short = _truncate(bluf, _BLUF_MAX_CHARS)

    # ── Key Decisions (limit to short bullets) ───────────────────────
    decisions_html = ""
    if decisions:
        items = "".join([
            f'<li style="margin-bottom:4px;color:{COLORS["dark_gray"]};font-size:13px;line-height:1.4;">'
            f'{_truncate(d, _DECISION_MAX_CHARS)}</li>'
            for d in decisions[:_MAX_DECISIONS]
        ])
        decisions_html = f"""
                    <tr>
                        <td style="padding:12px 24px 0 24px;">
                            <p style="font-family:{MONO_STACK};font-size:10px;color:{COLORS["accent"]};margin:0 0 6px 0;font-weight:bold;letter-spacing:0.5px;">
                                KEY DECISIONS
                            </p>
                            <ol style="font-family:{FONT_STACK};font-size:13px;line-height:1.4;margin:0;padding-left:18px;color:{COLORS["dark_gray"]};">
                                {items}
                            </ol>
                        </td>
                    </tr>"""

    # ── Next Steps (limit 3, cleaned) ────────────────────────────────
    steps_html = ""
    if execution_steps:
        all_items = []
        for step in execution_steps:
            for item in step.get('items', []):
                cleaned = _clean_step(item)
                if cleaned:
                    all_items.append(cleaned)
        if all_items:
            items = "".join([
                f'<li style="margin-bottom:4px;color:{COLORS["dark_gray"]};font-size:13px;line-height:1.4;">'
                f'{_truncate(item, _STEP_MAX_CHARS)}</li>'
                for item in all_items[:_MAX_STEPS]
            ])
            steps_html = f"""
                    <tr>
                        <td style="padding:12px 24px 0 24px;">
                            <p style="font-family:{MONO_STACK};font-size:10px;color:{COLORS["accent"]};margin:0 0 6px 0;font-weight:bold;letter-spacing:0.5px;">
                                NEXT STEPS
                            </p>
                            <ul style="font-family:{FONT_STACK};font-size:13px;line-height:1.4;margin:0;padding-left:18px;color:{COLORS["dark_gray"]};">
                                {items}
                            </ul>
                        </td>
                    </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background-color:{COLORS["warm_gray"]};font-family:{FONT_STACK};">
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:{COLORS["warm_gray"]};">
        <tr>
            <td align="center" style="padding:20px 16px;">
                <table cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;background-color:{COLORS["white"]};border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,0.06);">

                    <!-- Header -->
                    <tr>
                        <td style="padding:16px 24px;border-bottom:2px solid {COLORS["accent"]};">
                            <table cellpadding="0" cellspacing="0" border="0" width="100%">
                                <tr>
                                    <td>
                                        <img src="https://goailabs.ai/assets/logo.png" alt="Go AI Labs" width="120" style="width:120px;height:auto;display:inline-block;" />
                                    </td>
                                    <td align="right" valign="middle">
                                        <span style="font-family:{MONO_STACK};font-size:10px;color:{COLORS["mid_gray"]};letter-spacing:0.5px;">MEETING DEBRIEF</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Title + Meta -->
                    <tr>
                        <td style="padding:16px 24px 4px 24px;">
                            <h1 style="font-family:{FONT_STACK};font-size:18px;font-weight:bold;color:{COLORS["black"]};margin:0 0 4px 0;">
                                {title}
                            </h1>
                            <p style="font-family:{MONO_STACK};font-size:10px;color:{COLORS["mid_gray"]};margin:0;">
                                {meta_str}
                            </p>
                        </td>
                    </tr>

                    <!-- BLUF -->
                    <tr>
                        <td style="padding:12px 24px;">
                            <div style="border-left:3px solid {COLORS["accent"]};padding:8px 12px;background-color:{COLORS["accent_subtle"]};border-radius:0 3px 3px 0;">
                                <p style="font-family:{FONT_STACK};font-size:13px;line-height:1.5;color:{COLORS["dark_gray"]};margin:0;">
                                    {bluf_short}
                                </p>
                            </div>
                        </td>
                    </tr>
{decisions_html}
{steps_html}

                    <!-- Closing -->
                    <tr>
                        <td style="padding:16px 24px 8px 24px;">
                            <p style="font-family:{FONT_STACK};font-size:12px;color:{COLORS["mid_gray"]};margin:0;">
                                Full notes, action items, and transcript attached.
                            </p>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding:12px 24px;border-top:1px solid {COLORS["warm_gray"]};text-align:center;">
                            <p style="font-family:{MONO_STACK};font-size:9px;color:{COLORS["mid_gray"]};margin:0;">
                                goailabs.ai &nbsp;|&nbsp; CONFIDENTIAL
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    return html
