"""
Output Generator — orchestrates all template generation.
Called by compiler.py after all LLM passes are complete.

Replaces the old pdf_generator.py with AI Labs branded templates.
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Tuple, Optional

log = logging.getLogger("audio-compiler.output")


# ── Data Transformation Functions ────────────────────────────────────────


def extract_bluf(executive_summary: str) -> str:
    """
    Extract 2-4 sentence bottom line from executive summary.
    Takes the first paragraph or first 3 sentences.
    """
    if not executive_summary:
        return "No summary available."

    # Remove markdown headers
    lines = executive_summary.strip().split('\n')
    content_lines = [l for l in lines if not l.strip().startswith('#')]
    text = ' '.join(content_lines).strip()

    # Remove markdown bold/italic
    text = re.sub(r'\*+([^*]+)\*+', r'\1', text)

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)

    # Take first 3 sentences or ~300 chars
    bluf_sentences = []
    char_count = 0
    for s in sentences[:4]:
        if char_count + len(s) > 400 and bluf_sentences:
            break
        bluf_sentences.append(s)
        char_count += len(s)

    return ' '.join(bluf_sentences) if bluf_sentences else text[:400]


def extract_decisions(meeting_notes: str) -> List[str]:
    """
    Extract key decisions from meeting notes markdown.
    Looks for decision language and dedicated sections.
    """
    if not meeting_notes:
        return []

    decisions = []

    # Decision indicator patterns
    decision_patterns = [
        r'(?:decided|agreed|will|going to|confirmed|approved|selected|chose|committed)\s+(?:to\s+)?(.{20,150}?)(?:\.|$)',
        r'(?:decision|conclusion|agreement|commitment):\s*(.{20,150}?)(?:\.|$)',
    ]

    # Look for explicit decision sections
    lines = meeting_notes.split('\n')
    in_decision_section = False

    for line in lines:
        stripped = line.strip()

        # Check for decision section headers
        if re.match(r'^#+\s*(?:decisions?|conclusions?|agreements?|key\s+decisions?)', stripped, re.I):
            in_decision_section = True
            continue

        # Exit section on new header
        if stripped.startswith('#') and in_decision_section:
            in_decision_section = False

        # Capture bullet points in decision sections
        if in_decision_section and (stripped.startswith('-') or stripped.startswith('•')):
            decision_text = stripped.lstrip('-•').strip()
            decision_text = re.sub(r'\*+([^*]+)\*+', r'\1', decision_text)  # Remove markdown
            if len(decision_text) > 15:
                decisions.append(decision_text)

    # Also scan for decision language patterns
    for pattern in decision_patterns:
        matches = re.findall(pattern, meeting_notes, re.I | re.MULTILINE)
        for match in matches:
            clean = re.sub(r'\*+([^*]+)\*+', r'\1', match.strip())
            if clean and len(clean) > 15 and clean not in decisions:
                decisions.append(clean)

    # Dedupe and limit
    seen = set()
    unique = []
    for d in decisions:
        d_lower = d.lower()
        if d_lower not in seen:
            seen.add(d_lower)
            unique.append(d)

    return unique[:8]


def structure_execution_steps(action_items: str) -> List[dict]:
    """
    Group action items into execution steps.
    Each step: {num, title, tag, items, summary}
    """
    steps = []

    try:
        items = json.loads(action_items)
        if not isinstance(items, list):
            items = []
    except (json.JSONDecodeError, TypeError):
        # Try to parse as text
        items = []
        lines = action_items.split('\n') if action_items else []
        for line in lines:
            stripped = line.strip()
            if stripped and (stripped.startswith('-') or stripped.startswith('•') or re.match(r'^\d+\.', stripped)):
                task_text = re.sub(r'^[\d\.\-•\s]+', '', stripped).strip()
                if task_text:
                    items.append({"task": task_text, "priority": "medium"})

    if not items:
        return []

    # Group by priority
    high_priority = []
    medium_priority = []
    low_priority = []

    for item in items:
        priority = item.get('priority', 'medium').lower()
        if priority == 'high':
            high_priority.append(item)
        elif priority == 'low':
            low_priority.append(item)
        else:
            medium_priority.append(item)

    step_num = 0

    # Step 0: Immediate/urgent items (high priority)
    if high_priority:
        steps.append({
            "num": str(step_num),
            "title": "IMMEDIATE ACTIONS",
            "tag": "PRIORITY",
            "items": [f"{i.get('task', '')} → {i.get('assignee', 'TBD')}" for i in high_priority[:4]],
            "summary": f"{len(high_priority)} high-priority items requiring immediate attention",
        })
        step_num += 1

    # Group medium priority into logical steps
    if medium_priority:
        # Split into chunks of 3-4 items
        for i in range(0, len(medium_priority), 3):
            chunk = medium_priority[i:i+3]
            steps.append({
                "num": str(step_num),
                "title": f"FOLLOW-UP BATCH {step_num}" if step_num > 0 else "NEXT STEPS",
                "tag": "STANDARD",
                "items": [f"{item.get('task', '')} → {item.get('assignee', 'TBD')}" for item in chunk],
                "summary": f"{len(chunk)} action items for standard follow-up",
            })
            step_num += 1

    # Low priority as backlog
    if low_priority:
        steps.append({
            "num": "B",
            "title": "BACKLOG",
            "tag": "WHEN AVAILABLE",
            "items": [f"{i.get('task', '')}" for i in low_priority[:5]],
            "summary": f"{len(low_priority)} items for future consideration",
        })

    return steps


def structure_topic_blocks(meeting_notes: str) -> List[dict]:
    """
    Parse meeting notes into DISCUSSED/DECIDED/NEXT blocks per topic.
    Returns: [{title, discussed, decided, next_steps}, ...]
    """
    if not meeting_notes:
        return []

    topics = []
    current_topic = None

    lines = meeting_notes.split('\n')

    for line in lines:
        stripped = line.strip()

        # Check for topic headers (## or ### in markdown)
        header_match = re.match(r'^#{2,3}\s+(.+)$', stripped)
        if header_match:
            # Save previous topic
            if current_topic and current_topic.get('discussed'):
                topics.append(current_topic)

            current_topic = {
                'title': header_match.group(1).strip('*# '),
                'discussed': '',
                'decided': '',
                'next_steps': '',
            }
            continue

        if not current_topic:
            continue

        # Classify content
        clean_line = re.sub(r'\*+([^*]+)\*+', r'\1', stripped)

        # Decision language
        if re.search(r'\b(decided|agreed|confirmed|approved|will|going to)\b', clean_line, re.I):
            if current_topic['decided']:
                current_topic['decided'] += ' '
            current_topic['decided'] += clean_line

        # Future action language
        elif re.search(r'\b(next|follow[- ]?up|action|todo|schedule|plan to|need to)\b', clean_line, re.I):
            if current_topic['next_steps']:
                current_topic['next_steps'] += ' '
            current_topic['next_steps'] += clean_line

        # General discussion
        elif clean_line and not clean_line.startswith('#'):
            if current_topic['discussed']:
                current_topic['discussed'] += ' '
            current_topic['discussed'] += clean_line

    # Don't forget the last topic
    if current_topic and current_topic.get('discussed'):
        topics.append(current_topic)

    return topics[:10]  # Limit to 10 topics


def chapter_transcript(transcript: str, meeting_notes: str = "") -> List[dict]:
    """
    Break transcript into topic chapters.
    Simple heuristic: use paragraph breaks and keyword shifts.

    Returns: [{number, title, timestamp, utterances: [{speaker, timestamp, text}]}]
    """
    if not transcript:
        return [{
            'number': 1,
            'title': 'Full Transcript',
            'timestamp': '',
            'utterances': [{'speaker': '', 'timestamp': '', 'text': 'No transcript available.'}]
        }]

    # For now, use simple paragraph-based chunking
    # Future improvement: use topic headers from meeting_notes to align

    paragraphs = transcript.split('\n\n')

    # If transcript is short, return as single chapter
    if len(paragraphs) <= 3:
        return [{
            'number': 1,
            'title': 'Full Transcript',
            'timestamp': '',
            'utterances': [{'speaker': '', 'timestamp': '', 'text': transcript}]
        }]

    # Group into chapters of ~3-5 paragraphs each
    chapters = []
    chapter_num = 1
    current_utterances = []

    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue

        current_utterances.append({
            'speaker': '',
            'timestamp': '',
            'text': para,
        })

        # Create new chapter every 4 paragraphs or at end
        if len(current_utterances) >= 4 or i == len(paragraphs) - 1:
            # Try to extract a topic from the first paragraph
            first_text = current_utterances[0]['text'][:100]
            title = f"Section {chapter_num}"

            # Look for potential topic indicators
            topic_match = re.search(r'(?:discuss|talk about|regarding|about|topic:?)\s+([^.]{10,50})', first_text, re.I)
            if topic_match:
                title = topic_match.group(1).strip()

            chapters.append({
                'number': chapter_num,
                'title': title,
                'timestamp': '',
                'utterances': current_utterances,
            })
            current_utterances = []
            chapter_num += 1

    return chapters if chapters else [{
        'number': 1,
        'title': 'Full Transcript',
        'timestamp': '',
        'utterances': [{'speaker': '', 'timestamp': '', 'text': transcript}]
    }]


def extract_context_items(metadata: dict, meeting_notes: str) -> List[Tuple[str, str]]:
    """
    Extract context items for the executive brief.
    Returns list of (label, text) tuples.
    """
    context = []

    # Meeting type
    meeting_type = metadata.get('meeting_type', '')
    if meeting_type:
        context.append(("Meeting Type", meeting_type))

    # Key attendees
    attendees = metadata.get('attendees', [])
    if attendees:
        context.append(("Participants", ", ".join(attendees[:5])))

    # Try to extract purpose/background from notes
    if meeting_notes:
        # Look for background/context section
        bg_match = re.search(r'(?:background|context|purpose|overview)[:\s]*([^#\n]{30,200})', meeting_notes, re.I)
        if bg_match:
            context.append(("Background", bg_match.group(1).strip()))

    return context[:5]


# ── Main Generator Function ──────────────────────────────────────────────


def generate_all_outputs(
    job_id: str,
    output_dir: str,
    compilation_data: dict,
) -> dict:
    """
    Generate all output files from compilation data.

    Args:
        job_id: The job identifier
        output_dir: Directory to write output files
        compilation_data: Dict containing:
            - transcript: str (raw transcript text)
            - metadata: dict (title, date, attendees, duration, source_filename)
            - meeting_notes: str (structured notes from LLM)
            - action_items: str (JSON array or text of action items)
            - executive_summary: str (summary from LLM)

    Returns:
        Dict of output file paths and email body HTML
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {}

    # Extract data
    transcript = compilation_data.get('transcript', '')
    metadata = compilation_data.get('metadata', {})
    meeting_notes = compilation_data.get('meeting_notes', '')
    action_items = compilation_data.get('action_items', '')
    executive_summary = compilation_data.get('executive_summary', '')

    # Metadata fields
    title = metadata.get('title', metadata.get('meeting_type', 'Meeting'))
    date = metadata.get('date', 'Unknown Date')
    attendees = metadata.get('attendees', [])
    duration = metadata.get('duration', metadata.get('estimated_duration', 'Unknown'))
    source_filename = metadata.get('source_filename', 'audio.mp3')

    # Transform data
    bluf = extract_bluf(executive_summary)
    decisions = extract_decisions(meeting_notes)
    execution_steps = structure_execution_steps(action_items)
    topics = structure_topic_blocks(meeting_notes)
    context_items = extract_context_items(metadata, meeting_notes)
    chapters = chapter_transcript(transcript, meeting_notes)

    # Generate Executive Brief PDF
    try:
        from app.services.template_executive_brief import generate_executive_brief

        brief_path = str(output_path / "executive_brief.pdf")
        generate_executive_brief(
            output_path=brief_path,
            title=title,
            date=date,
            attendees=attendees,
            duration=duration,
            bluf=bluf,
            decisions=decisions,
            execution_steps=execution_steps,
            context_items=context_items,
        )
        results['executive_brief_pdf'] = brief_path
        log.info(f"Generated executive brief: {brief_path}")
    except Exception as e:
        log.error(f"Failed to generate executive brief: {e}", exc_info=True)
        results['executive_brief_pdf'] = None

    # Generate Full Debrief DOCX
    try:
        from app.services.template_debrief import generate_debrief

        debrief_path = str(output_path / "full_debrief.docx")
        generate_debrief(
            output_path=debrief_path,
            title=title,
            date=date,
            attendees=attendees,
            duration=duration,
            bluf=bluf,
            topics=topics,
            execution_steps=execution_steps,
        )
        results['full_debrief_docx'] = debrief_path
        log.info(f"Generated full debrief: {debrief_path}")
    except Exception as e:
        log.error(f"Failed to generate debrief DOCX: {e}", exc_info=True)
        results['full_debrief_docx'] = None

    # Generate Transcript PDF
    try:
        from app.services.template_transcript import generate_transcript, generate_simple_transcript

        transcript_path = str(output_path / "transcript.pdf")

        if chapters and len(chapters) > 1:
            generate_transcript(
                output_path=transcript_path,
                title=title,
                date=date,
                attendees=attendees,
                source_filename=source_filename,
                chapters=chapters,
            )
        else:
            generate_simple_transcript(
                output_path=transcript_path,
                title=title,
                date=date,
                attendees=attendees,
                source_filename=source_filename,
                transcript_text=transcript,
            )
        results['transcript_pdf'] = transcript_path
        log.info(f"Generated transcript: {transcript_path}")
    except Exception as e:
        log.error(f"Failed to generate transcript PDF: {e}", exc_info=True)
        results['transcript_pdf'] = None

    # Generate Email Body HTML
    try:
        from app.services.template_email import generate_email_body

        email_html = generate_email_body(
            title=title,
            date=date,
            attendees=attendees,
            duration=duration,
            bluf=bluf,
            decisions=decisions,
            execution_steps=execution_steps,
        )
        results['email_body_html'] = email_html

        # Also save to file for debugging
        email_path = output_path / "email_body.html"
        email_path.write_text(email_html, encoding='utf-8')
        log.info(f"Generated email body HTML")
    except Exception as e:
        log.error(f"Failed to generate email HTML: {e}", exc_info=True)
        results['email_body_html'] = None

    return results
