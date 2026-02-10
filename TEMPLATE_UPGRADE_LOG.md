# Template Upgrade Log

## Phase 0: Reconnaissance Findings

**Date:** 2026-02-10

### Current PDF Generator (`app/services/pdf_generator.py`)
- Uses `fpdf2` library (installed: v2.8.5)
- ROI Logistics branding with blue color scheme
- DejaVu fonts (system fonts on server)
- Three outputs:
  - `meeting_notes.pdf` — parsed from markdown
  - `action_items.pdf` — parsed from JSON
  - `transcript.pdf` — raw text dump

### Compiler Integration (`app/services/compiler.py`)
- Stage 7 calls `_stage_7_pdfs()` at line 219
- Function receives: `output_dir, filename, notes, action_items, transcript, metadata`
- Returns dict with paths to 3 PDFs
- Called via `run_stage()` for tracing

### Data Available from Pipeline
1. **transcript** (str) — raw transcript from Whisper
2. **metadata** (dict) — `{date, time, attendees[], meeting_type, ...}`
3. **notes** (str) — markdown meeting notes from LLM
4. **action_items** (str) — JSON array of `{task, assignee, deadline, priority}`
5. **summary** (str) — executive summary markdown from LLM
6. **review** (str) — quality review text

### Packages Installed on Server
- `fpdf2` 2.8.5 — current PDF generator
- Need to install: `reportlab`, `python-docx`

### Migration Strategy
1. Keep same function signature for `_stage_7_pdfs()`
2. Replace internals to call new template generators
3. Rename old `pdf_generator.py` to `pdf_generator_legacy.py`
4. Create new `output_generator.py` as orchestrator

---

## Implementation Progress

### Phase 1: Brand System
- [x] Create `app/services/brand.py`
- [x] Create `app/services/template_executive_brief.py`
- [x] Create `app/services/template_debrief.py`
- [x] Create `app/services/template_transcript.py`
- [x] Create `app/services/template_email.py`

### Phase 2: Integration
- [x] Create `app/services/output_generator.py`
- [x] Update `compiler.py` to use new generator
- [x] Rename old pdf_generator.py to legacy

### Phase 3: Data Transformation
- [x] BLUF extraction
- [x] Decision extraction
- [x] Execution step structuring
- [x] Topic block structuring
- [x] Transcript chaptering (basic paragraph-based)

### Phase 4: Testing
- [ ] Run test compilation
- [ ] Verify all 4 outputs generated
- [ ] Check trace for errors

### Phase 5: Deploy
- [ ] Commit all changes
- [ ] Push to origin
- [ ] Pull on rob3
- [ ] Restart service
- [ ] Verify health

---

## Files Created

1. `app/services/brand.py` — AI Labs brand system (colors, fonts, logo, header/footer)
2. `app/services/template_executive_brief.py` — Executive Brief PDF (reportlab)
3. `app/services/template_debrief.py` — Full Debrief DOCX (python-docx)
4. `app/services/template_transcript.py` — Transcript PDF with chapters (reportlab)
5. `app/services/template_email.py` — HTML email body (inline CSS)
6. `app/services/output_generator.py` — Orchestrator with data transformation

## Files Modified

1. `app/services/compiler.py` — Updated Stage 7 to use new output generator
2. `requirements.txt` — Added reportlab, python-docx

## Files Preserved

1. `app/services/pdf_generator_legacy.py` — Original ROI Logistics PDF generator (renamed)

## Known Limitations

1. Transcript chaptering is heuristic-based (paragraph breaks), no speaker diarization
2. Topic extraction from meeting notes depends on markdown headers
3. Decision extraction uses keyword patterns, may miss implicit decisions
