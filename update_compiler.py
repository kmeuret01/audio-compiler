#!/usr/bin/env python3
"""Update compiler.py prompts for stages 3, 4, and 5."""

import re

# Read the compiler file
with open("/home/clawdbot/audio-compiler/app/services/compiler.py", "r") as f:
    content = f.read()

# New Stage 3 system prompt
new_stage3_prompt = '''You are an elite executive meeting analyst. Given a transcript, produce detailed, substantive meeting notes organized by topic.

You must capture SPECIFICS — names, numbers, dollar amounts, tool names, strategies, exact quotes that reveal intent. Generic summaries are unacceptable.

FORMAT REQUIREMENTS:
1. Organize by TOPIC — each major discussion point gets its own section
2. Each topic section must have:
   - A "Topic Title:" line with a specific, descriptive title (NOT generic like "Project Overview")
   - 2-4 paragraphs capturing the SUBSTANCE of what was discussed — specific tools, strategies, numbers, reasoning, disagreements, and decisions
   - A "Conclusion:" line with the specific decision or takeaway (not a restatement of the topic)

3. After all topics, include:
   - "Next Arrangements" section with specific action items as "[ ]" checkbox items, each with WHO is responsible
   - "Recommendations" section with strategic observations the participants should consider

QUALITY STANDARDS:
- If someone mentioned a specific tool, company, dollar amount, or metric — it MUST appear in the notes
- If a decision was made with reasoning — capture BOTH the decision AND the reasoning
- If there was disagreement or a pivot in thinking — capture that dynamic
- Conclusions must be SPECIFIC DECISIONS, not vague restatements like "Continue to explore options"
- Action items must name the responsible person when discussed

BAD EXAMPLE (too generic):
Topic Title: Marketing Strategy
The team discussed various marketing approaches and decided to focus on what's working.
Conclusion: Continue to refine marketing strategies based on data.

GOOD EXAMPLE (specific and substantive):
Topic Title: Forum Seeding Strategy — VA-Driven with Anti-Detection Guardrails
Kevin and Jacob discussed using VAs rather than automation for forum posting on Reddit and Quora. Jacob explained that forums detect and ban automated posting, making human operators essential. The strategy involves creating 10+ accounts — some asking questions, some answering — to control the narrative. Jacob emphasized accounts must be "warmed up" on iOS devices for higher trust scores. Kevin framed the non-automatable nature as a competitive moat: "If people won't invest in putting a human on it, that's our advantage."
Conclusion: Jacob will develop the forum posting framework and hire a VA. Automation limited to account warm-up only; all posting must be human-operated to avoid detection and bans.

IMPORTANT:
- Do NOT use markdown syntax (no #, ##, **, etc.)
- Do NOT use bullet points for topic content — use full paragraphs
- Each topic MUST have a Conclusion line with a SPECIFIC decision
- Typically identify 6-12 distinct topics from a meeting
- Capture the speakers' own language and frameworks when they use distinctive terms'''

# New Stage 4 system prompt
new_stage4_prompt = '''You are a project manager extracting action items from a meeting transcript.

Return ONLY valid JSON: an array of objects with these keys:
- "task" (string) — SPECIFIC description of what needs to be done. Include tool names, targets, and scope. Bad: "Follow up on marketing." Good: "Contact Wix autoblogger developer via Telegram to request custom blog content submission capability."
- "assignee" (string or null) — Person responsible. Use their actual name from the transcript. If unassigned, use null.
- "deadline" (string or null) — Any mentioned timeline. Use exact language from transcript like "within 7 days" or "before next meeting."
- "priority" (string) — "high" for items discussed as immediate/urgent/step-0, "medium" for follow-up items, "low" for backlog/future considerations.

CRITICAL RULES:
- Extract the speakers' OWN execution framework if they defined one (e.g., "Step 0 is personas, Step 1 is blog automation, Step 2 is forum posting")
- Preserve specific details: dollar amounts, tool names, platform names, account counts
- If someone said "I'll do X" — that person is the assignee
- Include spending authorizations and budget decisions as action items
- Do NOT genericize. "Set up forum posting" is bad. "Build forum posting framework: create 10+ warm accounts on Reddit/Quora using iOS devices, hire VA from Fiverr, develop posting playbook with question/answer account pairs" is good.'''

# New Stage 5 system prompt
new_stage5_prompt = '''You are an executive assistant producing a concise but SUBSTANTIVE executive summary.

Do NOT use markdown heading syntax (no # or ## characters).
Format section headers as plain text ending with a colon on their own line.
Leave a blank line between section header and content.
Leave an extra blank line between sections.

Required sections:

Purpose of the Meeting:
[2-3 sentences explaining WHY this meeting happened and what it aimed to accomplish. Be specific — name the project, the business, the challenge.]

Key Outcomes:
[4-6 bullet points using "- " prefix. Each outcome must be SPECIFIC — include names, numbers, tools, and decisions. Not "discussed marketing" but "decided to prioritize Facebook Ads over Google Ads due to unresolved tracking tag issue; Jacob to run targeted campaigns using scraped Instagram audience data."]

Next Steps:
[3-5 bullet points using "- " prefix. Each must name WHO does WHAT by WHEN if discussed.]

Spending & Resources:
[Only include if financial decisions were made. Note specific amounts, authorizations, and constraints.]

QUALITY STANDARD: A reader who was NOT in the meeting should be able to understand exactly what was decided and why. Generic summaries that could apply to any meeting are unacceptable.

Keep it under 400 words.'''


def replace_stage3(content):
    """Replace stage 3 prompt."""
    # Find the function
    start = content.find("async def _stage_3_notes")
    if start == -1:
        raise ValueError("Could not find _stage_3_notes function")

    # Find system = """ after the function start
    system_start = content.find('system = """', start)
    if system_start == -1:
        raise ValueError("Could not find stage 3 system prompt start")
    prompt_start = system_start + len('system = """')

    # Find the closing triple quote
    prompt_end = content.find('"""', prompt_start)
    if prompt_end == -1:
        raise ValueError("Could not find stage 3 system prompt end")

    return content[:prompt_start] + new_stage3_prompt + content[prompt_end:]


def replace_stage4(content):
    """Replace stage 4 prompt."""
    # Stage 4 uses system = (...) format with string concatenation
    start = content.find("async def _stage_4_actions")
    if start == -1:
        raise ValueError("Could not find _stage_4_actions function")

    # Find system = ( after the function start
    system_start = content.find('system = (', start)
    if system_start == -1:
        raise ValueError("Could not find stage 4 system prompt start")

    # Find the closing ) - need to count parens
    paren_start = system_start + len('system = ')
    depth = 0
    i = paren_start
    while i < len(content):
        if content[i] == '(':
            depth += 1
        elif content[i] == ')':
            depth -= 1
            if depth == 0:
                break
        i += 1
    paren_end = i + 1  # Include the closing paren

    # Build new system assignment
    new_system = 'system = (\n        "' + new_stage4_prompt.replace('\n', '\\n"\n        "').replace('"', '\\"') + '"\n    )'

    return content[:system_start] + new_system + content[paren_end:]


def replace_stage5(content):
    """Replace stage 5 prompt."""
    # Stage 5 uses system = (...) format
    start = content.find("async def _stage_5_summary")
    if start == -1:
        raise ValueError("Could not find _stage_5_summary function")

    # Find system = ( after the function start
    system_start = content.find('system = (', start)
    if system_start == -1:
        raise ValueError("Could not find stage 5 system prompt start")

    # Find the closing )
    paren_start = system_start + len('system = ')
    depth = 0
    i = paren_start
    while i < len(content):
        if content[i] == '(':
            depth += 1
        elif content[i] == ')':
            depth -= 1
            if depth == 0:
                break
        i += 1
    paren_end = i + 1

    # Build new system assignment
    new_system = 'system = (\n        "' + new_stage5_prompt.replace('\n', '\\n"\n        "').replace('"', '\\"') + '"\n    )'

    return content[:system_start] + new_system + content[paren_end:]


# Apply replacements
print("Updating stage 3...")
content = replace_stage3(content)
print("Stage 3 done")

print("Updating stage 4...")
content = replace_stage4(content)
print("Stage 4 done")

print("Updating stage 5...")
content = replace_stage5(content)
print("Stage 5 done")

# Write back
with open("/home/clawdbot/audio-compiler/app/services/compiler.py", "w") as f:
    f.write(content)

print("All prompts updated successfully!")
