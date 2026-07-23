---
name: meeting-intelligence
description: >
  Local-first meeting pipeline: Whisper transcription → Hermes agent analysis → verified protocol.
  Agent reads the transcript with its own model, enriches with corporate context (Jira/Confluence/Email),
  and produces a grounded protocol with decisions, assignments, and risks.
version: 0.7.0
when_to_use:
  - "User uploads meeting audio/video and needs a protocol with decisions + assignments."
  - "Transcript exists and needs analysis, enrichment, or corporate cross-reference."
counter_triggers:
  - "Do NOT use for casual chat summarization — only structured meeting protocol."
  - "Do NOT extract items without source_quote grounding."
required_tools:
  - meeting_transcribe
  - meeting_agent_transcript
  - meeting_translate (optional)
optional_mcp:
  - jira         # create tasks from assignments
  - confluence   # save/update protocol pages
  - email        # send protocol to participants
  - calendar     # verify meeting time / find slots
---

# Meeting Intelligence

## Input sources

Use this skill when the user explicitly points to a source, for example
"глянь там-то" or "обработай вот это". Detect the source from the attachment,
message context, or the location the user names, then route it as follows.

| Source | Detect | Route |
|--------|--------|-------|
| Direct audio or video file | The user uploads or names a local audio/video file. | Pass the file path to `meeting_transcribe`. |
| YouTube or other media URL | The user provides a YouTube link or another URL that `yt-dlp` supports. | Download the audio with `yt-dlp`, then pass the downloaded file to `meeting_transcribe`. |
| Telegram voice message | A voice message is forwarded to the Hermes bot. | Use the forwarded audio attachment as the `meeting_transcribe` source. |
| Telegram video | A video is forwarded to the Hermes bot. | Use the forwarded video attachment as the `meeting_transcribe` source. |
| URL shared in Hermes chat | The user shares a link in Hermes chat and asks to process it. | If it is a supported media URL, use the `yt-dlp` route. Otherwise ask for a downloadable media file or transcript. |
| Email attachment or link | The user explicitly refers to an email, for example "глянь письмо от...", and identifies the sender, subject, or other useful detail. | The explicit request authorizes the Email MCP lookup. Retrieve the attachment or linked media, then transcribe it. Do not search email otherwise. |
| Local transcript file | The user uploads or names a `.txt`, `.md`, `.srt`, `.vtt`, or similar transcript. | Skip transcription and pass the file to `meeting_agent_transcript`, then analyze it. |

Do not infer a source from unrelated chat history. Ask for the source when the
user has not pointed to one clearly. Telegram forwarding and an explicitly
requested email lookup identify a source; they do not authorize any other MCP.
Never upload, send, create, modify, or delete external data as part of source
handling. Those actions require the user's separate, explicit request.

## Pipeline

```
Audio/Video → meeting_transcribe → transcript.txt → meeting_agent_transcript → AGENT ANALYSIS → protocol.json
                                                         │
                                          ┌──────────────┼──────────────┐
                                          ▼              ▼              ▼
                                        Jira          Confluence      Email
                                      (tasks)         (page)       (send)
```

## Tool: meeting_transcribe

Transcribe audio/video to timestamped transcript. Local Whisper, no cloud.

Input: `source` (required), `model=small`, `language=en`, `device=cpu`
Output: `<source>.transcript.txt` — lines formatted as `[timestamp] SPEAKER_NN | text`

Post-processing built in:
- Garbage filter: strips Whisper hallucination runs (5+ single-char tokens)
- Segment IDs removed for cleaner LLM input

## Tool: meeting_agent_transcript

Clean a saved transcript for agent analysis. This is local preprocessing only and never calls an LLM.

Input: `transcript` (required)
Output: JSON on stdout with cleaned transcript text and source, hash, line-count, garbage-filter, and segment-ID metadata.

Set `MEETING_AGENT_MODE=true` to have `meeting transcribe` print this same JSON payload after it saves its normal transcript files.

## Tool: meeting_translate (optional)

Translate transcript lines. Requires `--allow-cloud` if using external LLM.

Input: `transcript` (required), `target_lang=ru`, `allow_cloud=false`
Output: `<transcript>.translated.txt`

---

## Agent Protocol Extraction Rules

When the transcript is ready, the agent MUST follow these rules:

### Phase 1: Read & Understand

1. Read the full transcript file
2. Identify participants: map SPEAKER_NN to real names using `--participants` flag or ask user via clarify if unknown. Sample quotes help: *«SPEAKER_00 says: "Женя появился, но молчит" — who is this?»*
3. Note transcription artifacts (Whisper errors, repeated garbage, off-topic rants)

### Phase 2: Extract

Extract from transcript ONLY explicit statements. For each item, include `source_quote` — VERBATIM text from transcript.

**Participants:** `{"name": "string", "role": "string", "source_quote": "first line by this speaker"}`

**Decisions:** `{"text": "decision", "source_quote": "exact words", "approved_by": ["name"]}`
- A decision = explicitly agreed or approved outcome
- NOT a decision: suggestion, hypothesis, question, joke, personal opinion

**Assignments:** `{"task": "description", "assignee": "name or unknown", "deadline": "date or not_set", "source_quote": "exact words", "priority": "high|medium|low"}`
- If assignee not stated → `"unknown"` (never guess)
- If deadline not stated → `"not_set"` (never invent)

**Open questions:** `{"text": "question", "owner": "name or unknown", "source_quote": "..."}`
**Risks:** `{"text": "risk", "severity": "high|medium|low", "source_quote": "..."}`
**Next steps:** `{"action": "...", "who": "name", "when": "date or not_set"}`

### Phase 3: HALLUCINATION PREVENTION (mandatory)

Before finalizing, verify EVERY item:

| Check | Rule |
|-------|------|
| Participants exist? | Every name must appear in transcript or be mapped via `--participants`. Never invent. |
| Decisions grounded? | Every decision must have `source_quote` present in transcript (fuzzy 60% word match OK). |
| Assignments grounded? | Every task must trace to an explicit statement. No tasks from general discussion. |
| Assignees grounded? | If name not in transcript → flag as warning. Transliterated names (Ivan→Иван) = warning, not error. |
| Deadlines real? | If deadline looks fabricated (not in transcript) → flag as warning. |
| Roles invented? | No job titles unless stated in transcript. |
| Off-topic filtered? | Rants, jokes, stories ≠ decisions or tasks. |

If ANY critical check fails → set `quality.status: needs_review`, list failures in `quality.warnings`.

### Phase 4: Enrich (MCP — OPT-IN ONLY)

**CRITICAL: MCP enrichment is OFF by default.** The agent MUST NOT search Jira, Confluence, email, or calendar unless the user explicitly requests it. A random meeting video is NOT a license to rummage through corporate data.

An explicit request authorizes only the named system and action. Confirm the
target before creating Jira issues, updating Confluence, sending email, or
changing calendar data. Do not treat a request to search as permission to write.

When the user explicitly asks (e.g. "создай задачи в Jira", "проверь календарь", "сохрани в Confluence"), the agent MAY:

| MCP Tool | Action |
|----------|--------|
| **Jira** | Search for related issues; create tasks for assignments |
| **Confluence** | Find meeting series page; append protocol |
| **Email** | Send protocol to participants |
| **Calendar** | Verify meeting time; find next available slots |

### Phase 5: Output

```json
{
  "meeting": {
    "title": "...",
    "date": "2026-07-22",
    "duration": "21:58",
    "source_type": "transcript",
    "language": "ru"
  },
  "participants": [...],
  "decisions": [...],
  "assignments": [...],
  "open_questions": [...],
  "risks": [...],
  "next_steps": [...],
  "quality": {
    "status": "valid | needs_review",
    "errors": [],
    "warnings": [],
    "overall_confidence": 0-100,
    "model_used": "deepseek-v4-pro"
  }
}
```

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEETING_LLM_BASE_URL` | `http://localhost:1234/v1` | LLM endpoint (for translate only) |
| `MEETING_AGENT_MODE` | `false` | Print agent transcript JSON after transcription |
| `MEETING_TRANSCRIBE_MODEL` | `small` | Whisper model |
| `MEETING_MAX_FILE_MB` | `2048` | Max input size |
| `MEETING_MAX_DURATION_SEC` | `7200` | Max recording duration |

## Safety

- Cloud disabled by default; `--allow-cloud` required for external endpoints
- `source_quote` grounding enforced for every decision and assignment
- No participant names invented; use `--participants` or ask user
- Whisper garbage filtered before agent analysis
- Audit metadata captured per run (model, duration, confidence)
- MCP access is opt-in; a named request authorizes only the named action
