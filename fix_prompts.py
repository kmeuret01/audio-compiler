#!/usr/bin/env python3
"""Fix the prompts in compiler.py - simpler approach using triple-quoted strings only."""

# Read the file
with open("/home/clawdbot/audio-compiler/app/services/compiler.py", "r") as f:
    lines = f.readlines()

output_lines = []
i = 0

while i < len(lines):
    line = lines[i]

    # Stage 3: Replace the triple-quoted system string
    if 'async def _stage_3_notes(transcript: str, settings: Settings) -> dict:' in line:
        # Output the function definition line
        output_lines.append(line)
        i += 1
        # Output the docstring line
        output_lines.append(lines[i])
        i += 1
        # Now we should be at 'system = """'
        # Skip until we find the closing """
        while i < len(lines) and '"""' not in lines[i]:
            i += 1
        # Skip the opening system = """ line
        i += 1
        # Now skip content until closing """
        while i < len(lines):
            if lines[i].strip() == '"""':
                i += 1
                break
            if lines[i].strip().endswith('"""'):
                i += 1
                break
            i += 1

        # Now insert our new prompt
        output_lines.append('    system = """You are an elite executive meeting analyst. Given a transcript, produce detailed, substantive meeting notes organized by topic.\n')
        output_lines.append('\n')
        output_lines.append('You must capture SPECIFICS — names, numbers, dollar amounts, tool names, strategies, exact quotes that reveal intent. Generic summaries are unacceptable.\n')
        output_lines.append('\n')
        output_lines.append('FORMAT REQUIREMENTS:\n')
        output_lines.append('1. Organize by TOPIC — each major discussion point gets its own section\n')
        output_lines.append('2. Each topic section must have:\n')
        output_lines.append('   - A "Topic Title:" line with a specific, descriptive title (NOT generic like "Project Overview")\n')
        output_lines.append('   - 2-4 paragraphs capturing the SUBSTANCE of what was discussed — specific tools, strategies, numbers, reasoning, disagreements, and decisions\n')
        output_lines.append('   - A "Conclusion:" line with the specific decision or takeaway (not a restatement of the topic)\n')
        output_lines.append('\n')
        output_lines.append('3. After all topics, include:\n')
        output_lines.append('   - "Next Arrangements" section with specific action items as "[ ]" checkbox items, each with WHO is responsible\n')
        output_lines.append('   - "Recommendations" section with strategic observations the participants should consider\n')
        output_lines.append('\n')
        output_lines.append('QUALITY STANDARDS:\n')
        output_lines.append('- If someone mentioned a specific tool, company, dollar amount, or metric — it MUST appear in the notes\n')
        output_lines.append('- If a decision was made with reasoning — capture BOTH the decision AND the reasoning\n')
        output_lines.append('- If there was disagreement or a pivot in thinking — capture that dynamic\n')
        output_lines.append('- Conclusions must be SPECIFIC DECISIONS, not vague restatements like "Continue to explore options"\n')
        output_lines.append('- Action items must name the responsible person when discussed\n')
        output_lines.append('\n')
        output_lines.append('BAD EXAMPLE (too generic):\n')
        output_lines.append('Topic Title: Marketing Strategy\n')
        output_lines.append("The team discussed various marketing approaches and decided to focus on what's working.\n")
        output_lines.append('Conclusion: Continue to refine marketing strategies based on data.\n')
        output_lines.append('\n')
        output_lines.append('GOOD EXAMPLE (specific and substantive):\n')
        output_lines.append('Topic Title: Forum Seeding Strategy — VA-Driven with Anti-Detection Guardrails\n')
        output_lines.append('Kevin and Jacob discussed using VAs rather than automation for forum posting on Reddit and Quora. Jacob explained that forums detect and ban automated posting, making human operators essential. The strategy involves creating 10+ accounts — some asking questions, some answering — to control the narrative. Jacob emphasized accounts must be "warmed up" on iOS devices for higher trust scores. Kevin framed the non-automatable nature as a competitive moat: "If people won\'t invest in putting a human on it, that\'s our advantage."\n')
        output_lines.append('Conclusion: Jacob will develop the forum posting framework and hire a VA. Automation limited to account warm-up only; all posting must be human-operated to avoid detection and bans.\n')
        output_lines.append('\n')
        output_lines.append('IMPORTANT:\n')
        output_lines.append('- Do NOT use markdown syntax (no #, ##, **, etc.)\n')
        output_lines.append('- Do NOT use bullet points for topic content — use full paragraphs\n')
        output_lines.append('- Each topic MUST have a Conclusion line with a SPECIFIC decision\n')
        output_lines.append('- Typically identify 6-12 distinct topics from a meeting\n')
        output_lines.append("- Capture the speakers' own language and frameworks when they use distinctive terms\"\"\"\n")
        output_lines.append('\n')
        continue

    # Stage 4: Replace the parenthesized system string
    if 'async def _stage_4_actions(transcript: str, settings: Settings) -> dict:' in line:
        output_lines.append(line)
        i += 1
        # Output the docstring
        output_lines.append(lines[i])
        i += 1
        # Now skip the old system = (...) block
        # Skip until we find the closing )
        paren_depth = 0
        while i < len(lines):
            for char in lines[i]:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
            if paren_depth == 0 and 'system' in lines[i-1] if i > 0 else False:
                # Haven't entered yet
                if '(' in lines[i]:
                    paren_depth = lines[i].count('(') - lines[i].count(')')
                    i += 1
                    continue
            if paren_depth <= 0 and i > 0:
                break
            i += 1
        i += 1

        # Write new prompt
        output_lines.append('    system = """You are a project manager extracting action items from a meeting transcript.\n')
        output_lines.append('\n')
        output_lines.append('Return ONLY valid JSON: an array of objects with these keys:\n')
        output_lines.append('- "task" (string) — SPECIFIC description of what needs to be done. Include tool names, targets, and scope. Bad: "Follow up on marketing." Good: "Contact Wix autoblogger developer via Telegram to request custom blog content submission capability."\n')
        output_lines.append('- "assignee" (string or null) — Person responsible. Use their actual name from the transcript. If unassigned, use null.\n')
        output_lines.append('- "deadline" (string or null) — Any mentioned timeline. Use exact language from transcript like "within 7 days" or "before next meeting."\n')
        output_lines.append('- "priority" (string) — "high" for items discussed as immediate/urgent/step-0, "medium" for follow-up items, "low" for backlog/future considerations.\n')
        output_lines.append('\n')
        output_lines.append('CRITICAL RULES:\n')
        output_lines.append("- Extract the speakers' OWN execution framework if they defined one (e.g., \"Step 0 is personas, Step 1 is blog automation, Step 2 is forum posting\")\n")
        output_lines.append('- Preserve specific details: dollar amounts, tool names, platform names, account counts\n')
        output_lines.append("- If someone said \"I'll do X\" — that person is the assignee\n")
        output_lines.append('- Include spending authorizations and budget decisions as action items\n')
        output_lines.append('- Do NOT genericize. "Set up forum posting" is bad. "Build forum posting framework: create 10+ warm accounts on Reddit/Quora using iOS devices, hire VA from Fiverr, develop posting playbook with question/answer account pairs" is good.\"\"\"\n')
        continue

    # Stage 5: Replace the parenthesized system string
    if 'async def _stage_5_summary(transcript: str, settings: Settings) -> dict:' in line:
        output_lines.append(line)
        i += 1
        # Output docstring
        output_lines.append(lines[i])
        i += 1
        # Skip old system = (...) block
        paren_depth = 0
        started = False
        while i < len(lines):
            if 'system = (' in lines[i]:
                started = True
            if started:
                paren_depth += lines[i].count('(') - lines[i].count(')')
                if paren_depth <= 0:
                    i += 1
                    break
            i += 1

        # Write new prompt
        output_lines.append('    system = """You are an executive assistant producing a concise but SUBSTANTIVE executive summary.\n')
        output_lines.append('\n')
        output_lines.append('Do NOT use markdown heading syntax (no # or ## characters).\n')
        output_lines.append('Format section headers as plain text ending with a colon on their own line.\n')
        output_lines.append('Leave a blank line between section header and content.\n')
        output_lines.append('Leave an extra blank line between sections.\n')
        output_lines.append('\n')
        output_lines.append('Required sections:\n')
        output_lines.append('\n')
        output_lines.append('Purpose of the Meeting:\n')
        output_lines.append('[2-3 sentences explaining WHY this meeting happened and what it aimed to accomplish. Be specific — name the project, the business, the challenge.]\n')
        output_lines.append('\n')
        output_lines.append('Key Outcomes:\n')
        output_lines.append('[4-6 bullet points using "- " prefix. Each outcome must be SPECIFIC — include names, numbers, tools, and decisions. Not "discussed marketing" but "decided to prioritize Facebook Ads over Google Ads due to unresolved tracking tag issue; Jacob to run targeted campaigns using scraped Instagram audience data."]\n')
        output_lines.append('\n')
        output_lines.append('Next Steps:\n')
        output_lines.append('[3-5 bullet points using "- " prefix. Each must name WHO does WHAT by WHEN if discussed.]\n')
        output_lines.append('\n')
        output_lines.append('Spending & Resources:\n')
        output_lines.append('[Only include if financial decisions were made. Note specific amounts, authorizations, and constraints.]\n')
        output_lines.append('\n')
        output_lines.append('QUALITY STANDARD: A reader who was NOT in the meeting should be able to understand exactly what was decided and why. Generic summaries that could apply to any meeting are unacceptable.\n')
        output_lines.append('\n')
        output_lines.append('Keep it under 400 words.\"\"\"\n')
        continue

    output_lines.append(line)
    i += 1

# Write output
with open("/home/clawdbot/audio-compiler/app/services/compiler.py", "w") as f:
    f.writelines(output_lines)

print("Done!")
