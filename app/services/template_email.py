"""Email Body HTML Template — structured HTML for email clients."""

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

FONT_STACK = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO_STACK = "'Courier New', Consolas, monospace"


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
    Generate the HTML email body.

    Args:
        title: Meeting title
        date: Meeting date
        attendees: List of attendee names
        duration: Estimated duration string
        bluf: Bottom Line Up Front text
        decisions: List of key decision strings
        execution_steps: List of dicts: {num, title, summary}

    Returns:
        HTML string for email body
    """
    attendees_str = ", ".join(attendees[:4])
    if len(attendees) > 4:
        attendees_str += f" +{len(attendees) - 4} more"

    # Build decisions list HTML
    decisions_html = ""
    if decisions:
        decisions_items = "".join([
            f'<li style="margin-bottom: 6px; color: {COLORS["dark_gray"]};">{d}</li>'
            for d in decisions
        ])
        decisions_html = f"""
        <tr>
            <td style="padding: 16px 24px;">
                <p style="font-family: {MONO_STACK}; font-size: 11px; color: {COLORS["accent"]}; margin: 0 0 8px 0; font-weight: bold; letter-spacing: 0.5px;">
                    KEY DECISIONS
                </p>
                <ol style="font-family: {FONT_STACK}; font-size: 14px; line-height: 1.5; margin: 0; padding-left: 20px; color: {COLORS["dark_gray"]};">
                    {decisions_items}
                </ol>
            </td>
        </tr>
        """

    # Build execution steps HTML
    steps_html = ""
    if execution_steps:
        steps_rows = ""
        for step in execution_steps:
            step_num = step.get('num', '0')
            step_title = step.get('title', '')
            step_summary = step.get('summary', '')

            num_color = COLORS["accent"] if str(step_num) == "0" else COLORS["dark_gray"]

            steps_rows += f"""
            <tr>
                <td style="padding: 8px 12px; vertical-align: top; width: 40px; font-family: {MONO_STACK}; font-size: 12px; font-weight: bold; color: {num_color};">
                    [{step_num}]
                </td>
                <td style="padding: 8px 12px; vertical-align: top;">
                    <strong style="font-family: {FONT_STACK}; font-size: 14px; color: {COLORS["black"]};">{step_title}</strong>
                    <br>
                    <span style="font-family: {FONT_STACK}; font-size: 13px; color: {COLORS["mid_gray"]};">{step_summary}</span>
                </td>
            </tr>
            """

        steps_html = f"""
        <tr>
            <td style="padding: 16px 24px;">
                <p style="font-family: {MONO_STACK}; font-size: 11px; color: {COLORS["accent"]}; margin: 0 0 8px 0; font-weight: bold; letter-spacing: 0.5px;">
                    EXECUTION STEPS
                </p>
                <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: {COLORS["light_bg"]}; border-radius: 4px;">
                    {steps_rows}
                </table>
            </td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: {COLORS["warm_gray"]}; font-family: {FONT_STACK};">
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: {COLORS["warm_gray"]};">
        <tr>
            <td align="center" style="padding: 24px 16px;">
                <table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width: 600px; background-color: {COLORS["white"]}; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">

                    <!-- Header with Logo -->
                    <tr>
                        <td style="padding: 20px 24px; border-bottom: 1px solid {COLORS["warm_gray"]};">
                            <table cellpadding="0" cellspacing="0" border="0" width="100%">
                                <tr>
                                    <td>
                                        <span style="font-family: {MONO_STACK}; font-size: 16px; font-weight: bold; color: {COLORS["accent"]};">[ ]</span>
                                        <span style="font-family: {MONO_STACK}; font-size: 14px; font-weight: bold; color: {COLORS["black"]};">AI</span>
                                        <span style="font-family: {FONT_STACK}; font-size: 10px; color: {COLORS["mid_gray"]};">LABS</span>
                                    </td>
                                    <td align="right">
                                        <span style="font-family: {MONO_STACK}; font-size: 10px; color: {COLORS["mid_gray"]};">MEETING DEBRIEF</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Title and Meta -->
                    <tr>
                        <td style="padding: 20px 24px 8px 24px;">
                            <h1 style="font-family: {FONT_STACK}; font-size: 20px; font-weight: bold; color: {COLORS["black"]}; margin: 0 0 8px 0;">
                                {title}
                            </h1>
                            <p style="font-family: {MONO_STACK}; font-size: 11px; color: {COLORS["mid_gray"]}; margin: 0;">
                                {date} &nbsp;|&nbsp; {duration} &nbsp;|&nbsp; {attendees_str}
                            </p>
                        </td>
                    </tr>

                    <!-- Orange Divider -->
                    <tr>
                        <td style="padding: 0 24px;">
                            <div style="height: 3px; background-color: {COLORS["accent"]}; border-radius: 2px;"></div>
                        </td>
                    </tr>

                    <!-- BLUF Section -->
                    <tr>
                        <td style="padding: 16px 24px;">
                            <p style="font-family: {MONO_STACK}; font-size: 11px; color: {COLORS["accent"]}; margin: 0 0 8px 0; font-weight: bold; letter-spacing: 0.5px;">
                                BOTTOM LINE UP FRONT
                            </p>
                            <div style="border-left: 4px solid {COLORS["accent"]}; padding-left: 16px; background-color: {COLORS["accent_subtle"]}; padding: 12px 16px; border-radius: 0 4px 4px 0;">
                                <p style="font-family: {FONT_STACK}; font-size: 14px; line-height: 1.6; color: {COLORS["dark_gray"]}; margin: 0;">
                                    {bluf}
                                </p>
                            </div>
                        </td>
                    </tr>

                    {decisions_html}

                    {steps_html}

                    <!-- Attachments Section -->
                    <tr>
                        <td style="padding: 16px 24px;">
                            <p style="font-family: {MONO_STACK}; font-size: 11px; color: {COLORS["accent"]}; margin: 0 0 8px 0; font-weight: bold; letter-spacing: 0.5px;">
                                ATTACHED
                            </p>
                            <table cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td style="padding: 4px 0;">
                                        <span style="font-family: {MONO_STACK}; font-size: 12px; color: {COLORS["mid_gray"]};">📄</span>
                                        <span style="font-family: {FONT_STACK}; font-size: 13px; color: {COLORS["dark_gray"]};">executive_brief.pdf</span>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 4px 0;">
                                        <span style="font-family: {MONO_STACK}; font-size: 12px; color: {COLORS["mid_gray"]};">📝</span>
                                        <span style="font-family: {FONT_STACK}; font-size: 13px; color: {COLORS["dark_gray"]};">full_debrief.docx</span>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 4px 0;">
                                        <span style="font-family: {MONO_STACK}; font-size: 12px; color: {COLORS["mid_gray"]};">📜</span>
                                        <span style="font-family: {FONT_STACK}; font-size: 13px; color: {COLORS["dark_gray"]};">transcript.pdf</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 16px 24px; border-top: 1px solid {COLORS["warm_gray"]}; text-align: center;">
                            <p style="font-family: {MONO_STACK}; font-size: 10px; color: {COLORS["mid_gray"]}; margin: 0;">
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
