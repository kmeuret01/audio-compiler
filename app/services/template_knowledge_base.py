"""
Knowledge base export templates — Notion and Confluence formatted markdown.

No LLM calls, no external libraries. Pure formatting of existing structured data
into platform-specific markup that pastes cleanly into each knowledge base.
"""

import json
import logging
from pathlib import Path
from typing import List

log = logging.getLogger("audio-compiler.output")


# ── Notion Export ────────────────────────────────────────────────────────────


def generate_notion_export(
    output_path: str,
    title: str,
    date: str,
    attendees: List[str],
    duration: str,
    bluf: str,
    decisions: List[str],
    execution_steps: List[dict],
    topics: List[dict],
    action_items_raw: str = "",
) -> None:
    """
    Generate Notion-formatted markdown with callout blocks, toggle lists,
    database properties, checkbox tasks, and dividers.

    Designed to paste into Notion and render correctly with native blocks.
    """
    lines = []

    # Title as H1
    lines.append(f"# {title}")
    lines.append("")

    # Metadata as database properties (Notion inline table style)
    lines.append("| Property | Value |")
    lines.append("|---|---|")
    lines.append(f"| Date | {date} |")
    lines.append(f"| Duration | {duration} |")
    lines.append(f"| Attendees | {', '.join(attendees)} |")
    lines.append(f"| Status | Complete |")
    lines.append("")

    # BLUF as callout block (Notion recognizes > with emoji prefix)
    lines.append("> **Bottom Line**")
    lines.append(f"> {bluf}")
    lines.append("")

    lines.append("---")
    lines.append("")

    # Key Decisions
    if decisions:
        lines.append("## Key Decisions")
        lines.append("")
        for decision in decisions:
            lines.append(f"- {decision}")
        lines.append("")

    # Action Items as checkboxes (Notion converts - [ ] to checkboxes)
    if execution_steps:
        lines.append("## Action Items")
        lines.append("")
        for step in execution_steps:
            lines.append(f"### {step.get('title', 'Tasks')}")
            for item in step.get("items", []):
                lines.append(f"- [ ] {item}")
            lines.append("")

    lines.append("---")
    lines.append("")

    # Topics as toggle blocks (Notion converts details/summary to toggles)
    if topics:
        lines.append("## Discussion Topics")
        lines.append("")
        for topic in topics:
            topic_title = topic.get("title", "Untitled")
            discussed = topic.get("discussed", "")
            decided = topic.get("decided", "")
            next_steps = topic.get("next_steps", "")

            # Toggle header
            lines.append(f"<details>")
            lines.append(f"<summary><strong>{topic_title}</strong></summary>")
            lines.append("")

            if discussed:
                lines.append(f"**Discussed:** {discussed}")
                lines.append("")
            if decided:
                lines.append(f"**Decided:** {decided}")
                lines.append("")
            if next_steps:
                lines.append(f"**Next Steps:** {next_steps}")
                lines.append("")

            lines.append("</details>")
            lines.append("")

    # Raw action items JSON for Notion database import
    if action_items_raw:
        try:
            items = json.loads(action_items_raw)
            if isinstance(items, list) and items:
                lines.append("---")
                lines.append("")
                lines.append("## Action Items Database")
                lines.append("")
                lines.append("| Task | Assignee | Priority | Deadline |")
                lines.append("|---|---|---|---|")
                for item in items:
                    task = item.get("task", "")
                    assignee = item.get("assignee", "TBD")
                    priority = item.get("priority", "medium")
                    deadline = item.get("deadline", "TBD")
                    lines.append(f"| {task} | {assignee} | {priority} | {deadline} |")
                lines.append("")
        except (json.JSONDecodeError, TypeError):
            pass

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    log.info("Generated Notion export: %s", output_path)


# ── Confluence Export ────────────────────────────────────────────────────────


def generate_confluence_export(
    output_path: str,
    title: str,
    date: str,
    attendees: List[str],
    duration: str,
    bluf: str,
    decisions: List[str],
    execution_steps: List[dict],
    topics: List[dict],
    action_items_raw: str = "",
) -> None:
    """
    Generate Confluence wiki markup with panels, status macros,
    task lists, and expand macros.

    Uses Confluence storage format (XHTML-based) for clean import.
    """
    lines = []

    # Title
    lines.append(f"h1. {title}")
    lines.append("")

    # Info panel with metadata
    lines.append("{panel:title=Meeting Details|borderStyle=solid|borderColor=#ccc|bgColor=#f5f5f5}")
    lines.append(f"*Date:* {date}")
    lines.append(f"*Duration:* {duration}")
    lines.append(f"*Attendees:* {', '.join(attendees)}")
    lines.append("{panel}")
    lines.append("")

    # BLUF as info macro
    lines.append("{info:title=Bottom Line}")
    lines.append(bluf)
    lines.append("{info}")
    lines.append("")

    # Key Decisions with status macros
    if decisions:
        lines.append("h2. Key Decisions")
        lines.append("")
        for decision in decisions:
            lines.append(f"* {{status:colour=Green|title=DECIDED}} {decision}")
        lines.append("")

    # Action Items as Confluence task list
    if execution_steps:
        lines.append("h2. Action Items")
        lines.append("")
        for step in execution_steps:
            step_title = step.get("title", "Tasks")
            tag = step.get("tag", "")
            lines.append(f"h3. {step_title}")
            if tag:
                lines.append(f"{{status:colour=Blue|title={tag}}}")
            lines.append("")

            for item in step.get("items", []):
                # Parse "task text -> assignee" format
                if " → " in item:
                    task_part, assignee = item.rsplit(" → ", 1)
                    lines.append(f"[] {task_part} -- [~{assignee.strip().lower().replace(' ', '.')}]")
                else:
                    lines.append(f"[] {item}")
            lines.append("")

    # Topics as expand macros
    if topics:
        lines.append("h2. Discussion Topics")
        lines.append("")
        for topic in topics:
            topic_title = topic.get("title", "Untitled")
            discussed = topic.get("discussed", "")
            decided = topic.get("decided", "")

            lines.append(f"{{expand:title={topic_title}}}")

            if discussed:
                lines.append(f"*Discussed:* {discussed}")
                lines.append("")
            if decided:
                lines.append(f"*Decided:* {{status:colour=Green|title=DECIDED}} {decided}")
                lines.append("")

            lines.append("{expand}")
            lines.append("")

    # Action items table for Confluence
    if action_items_raw:
        try:
            items = json.loads(action_items_raw)
            if isinstance(items, list) and items:
                lines.append("h2. Action Items Table")
                lines.append("")
                lines.append("||Task||Assignee||Priority||Deadline||")
                for item in items:
                    task = item.get("task", "")
                    assignee = item.get("assignee", "TBD")
                    priority = item.get("priority", "medium")
                    deadline = item.get("deadline", "TBD")

                    # Color code priority
                    if priority == "high":
                        priority_display = "{status:colour=Red|title=HIGH}"
                    elif priority == "low":
                        priority_display = "{status:colour=Grey|title=LOW}"
                    else:
                        priority_display = "{status:colour=Yellow|title=MEDIUM}"

                    lines.append(f"|{task}|{assignee}|{priority_display}|{deadline}|")
                lines.append("")
        except (json.JSONDecodeError, TypeError):
            pass

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    log.info("Generated Confluence export: %s", output_path)
