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
Audio/Video → meeting_transcribe → transcript.txt → meeting_agent_transcript → AGENT ANALYSIS → human-readable artifacts
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

### Phase 0: Content type detection

After transcription and before extraction, read the full transcript and classify
the content. Do not assume that an audio recording is a meeting.

| Content type | Signals | Default document types |
|---|---|---|
| Meeting | Multiple participants jointly discuss, approve decisions, or assign work. | Protocol, summary, analytical note, register of decisions, assignment list, detailed minutes, action plan, executive brief. |
| Lecture | One or more speakers teach topics and concepts, usually with examples and optional audience Q&A. | Summary, analytical note, detailed minutes, presentation outline, knowledge article, executive brief. Do not create a meeting protocol. |
| Interview | Questions and answers structure the recording. | Q&A log, summary, analytical note, detailed minutes, executive brief. |
| Presentation | A speaker follows slides or a prepared script, with little or no discussion. | Presentation outline, summary, analytical note, executive brief. |

Record the classification and its evidence in every produced artifact. If the
format is mixed, choose the dominant format and preserve the secondary format
in the summary, for example "lecture with Q&A". If it is ambiguous, ask the
user or produce only a summary with a classification warning.

After classifying the content type, perform a language-quality check on the
full transcript. Detect the actual language from its content, not only Whisper's
reported language. If Whisper reports English but the transcript contains a high
density of Russian-specific transliterated names or institutional terms (for
example `AkhmEtov`, `Yakovlev`, `Minjust`, or `Rosstandart`), flag it as
**probably Russian, transcribed as English — quality degraded**. Warn the user
and offer to re-transcribe with `--language ru` before extraction or artifact
generation.

Immediately tell the user the detected content type, duration, and language,
then list the artifacts that will be produced. For example: "Detected: lecture
(44 min, English). Producing: transcript, summary, analytical note. Protocol
not applicable." This is a user-facing status update, not a JSON payload.

When the transcript is ready, the agent MUST follow these rules:

### Phase 1: Read & Understand

1. Read the full transcript file
2. Identify participants: map SPEAKER_NN to real names using `--participants` flag or ask user via clarify if unknown. Sample quotes help: *«SPEAKER_00 says: "Женя появился, но молчит" — who is this?»*
3. Note transcription artifacts (Whisper errors, repeated garbage, off-topic rants)

### Phase 2: Meeting extraction

**Before extraction — choose LLM backend.** Ask the user which model to use for analysis. Auto-detect available backends and present as options:

1. **Codex** — `codex exec` available (best quality, OpenAI API, paid)
2. **Current agent model** — the model running this agent (free, already loaded)
3. **LM Studio** — localhost:1234 (free, local, needs model loaded)
4. **Ollama** — localhost:11434 (free, local)
5. **Cloud API** — OpenAI/Anthropic/etc. (paid, needs API key)

Detection logic:
```bash
curl -s localhost:1234/v1/models && echo "LM Studio available"
curl -s localhost:11434/api/tags && echo "Ollama available"
which codex && echo "Codex available"
```

Default: ask user via clarify. If user says "codex" or "local" — use that. Store choice in memory.

After backend chosen, proceed with extraction:

Apply Phases 2 and 3 only when Phase 0 classifies the source as a meeting.
For a lecture, extract the speaker, topics, key concepts, examples, and any
intelligible Q&A. Do not recast teaching claims as decisions or audience
members as meeting participants.

Extract from transcript ONLY explicit statements. For each item, include `source_quote` — VERBATIM text from transcript.

**Participants:** `{"name": "string", "role": "string", "source_quote": "first line by this speaker"}`

**Agenda:** `{"text": "topic discussed", "source_quote": "exact words"}`

**Decisions:** `{"text": "decision", "source_quote": "exact words", "approved_by": ["name"]}`
- A decision = explicitly agreed or approved outcome
- NOT a decision: suggestion, hypothesis, question, joke, personal opinion

**Assignments:** `{"task": "description", "assignee": "name or unknown", "deadline": "date or not_set", "source_quote": "exact words", "priority": "high|medium|low"}`
- If assignee not stated → `"unknown"` (never guess)
- If deadline not stated → `"not_set"` (never invent)

**Open questions:** `{"text": "question", "owner": "name or unknown", "source_quote": "..."}`
**Risks:** `{"text": "risk", "severity": "high|medium|low", "source_quote": "..."}`
**Next steps:** `{"action": "...", "who": "name or unknown", "when": "date or not_set", "source_quote": "exact words"}`

### Phase 3: HALLUCINATION PREVENTION (mandatory)

Before finalizing, verify EVERY item:

| Check | Rule |
|-------|------|
| Participants exist? | Every name must appear in transcript or be mapped via `--participants`. Never invent. |
| Decisions grounded? | Every decision must have `source_quote` present in transcript (fuzzy 60% word match OK). |
| Assignments grounded? | Every task must trace to an explicit statement. No tasks from general discussion. |
| Other extracted items grounded? | Every agenda item, open question, risk, and next step must have a `source_quote` present in the transcript. |
| Assignees grounded? | If name not in transcript → flag as warning. Transliterated names (Ivan→Иван) = warning, not error. |
| Deadlines real? | If deadline looks fabricated (not in transcript) → flag as warning. |
| Roles invented? | No job titles unless stated in transcript. |
| Off-topic filtered? | Rants, jokes, stories ≠ decisions or tasks. |

If ANY critical check fails → set `quality.status: needs_review`, list failures in `quality.warnings`.

### Phase 4: Artifact generation

Use the route selected in Phase 0. Do not create artifacts that misrepresent
the content type. Generate human-readable files for every route. DOCX is the
primary document format; XLSX is required for registers and lists; PPTX is
preferred for a presentation outline when slide-ready output is requested.
JSON may support internal extraction and validation, but never is a user
deliverable.

Always produce `transcript.txt`. The following document types are the selectable
output menu. Produce the default set for the detected content type on a full
analysis request. When the user names document types, produce only those named
types that apply to the content type. A request for "just summary" still
produces only the summary.

| Document type | Applies to | Format | Required sections or columns | When to produce |
|---|---|---|---|---|
| Summary (Саммари) | Meeting, lecture, interview, presentation | `summary.docx` | Subject, key points, outcomes, unresolved items; for lectures, speaker, duration, timestamped concepts, and Q&A when present. | Default for every content type except when the user requests a narrower set. |
| Protocol (Протокол) | Meeting | `protocol.docx` | Metadata, participants, agenda, decisions, assignments, open questions, risks, next steps, quality warnings. | Default meeting primary deliverable. Never produce for a non-meeting. |
| Analytical note (Аналитическая записка) | Meeting, lecture, interview, presentation | `analytical.docx` | Context, analysis of outcomes or claims, risks or limitations, recommendations, recurring themes. | Default for every content type on full analysis. |
| Register of decisions (Реестр решений) | Meeting | `decision-register.xlsx` | One row per decision: decision, date or `not_set`, approvers, source_quote, timestamp, quality warning. | Default for meetings when at least one explicit decision exists. Do not infer decisions. |
| Assignment list (Список поручений) | Meeting | `assignment-list.xlsx` | One row per assignment: task, executor, deadline, priority, source_quote, timestamp, quality warning. | Default for meetings when at least one explicit assignment exists. Use `unknown` and `not_set` rather than guessing. |
| Detailed minutes (Подробный конспект) | Meeting, lecture, interview | `detailed-minutes.docx` | Chronological timestamped notes, speaker-by-speaker account, topic transitions, quoted decisions or Q&A where applicable. | Default for meetings and lectures; produce for interviews when the user asks for a chronological record. |
| Presentation outline (План презентации) | Presentation, lecture | `presentation-outline.pptx` or `presentation-outline.docx` | Slide-by-slide title, key message, supporting points, suggested evidence or example, speaker notes when grounded. | Default for presentations and lectures. Use DOCX unless the user requests slide-ready PPTX. |
| Q&A log (Журнал вопросов-ответов) | Interview, meeting, lecture | `q-and-a-log.docx` | Timestamped question, answer, questioner or respondent when known, source_quote, unresolved follow-up. | Default for interviews; produce for meetings and lectures only when intelligible Q&A is present. |
| Knowledge article (Статья для базы знаний) | Lecture | `knowledge-article.docx` | Title, purpose, concepts, structured sections, examples, references mentioned in the source, glossary or takeaways when supported. | Default for lectures. Do not add external references unless the user explicitly requests permitted enrichment. |
| Action plan (План действий) | Meeting | `action-plan.docx` or `action-plan.xlsx` | Objective, ordered next steps, owner, target date, dependencies, source_quote, status `not_started`. | Default for meetings when explicit next steps or assignments exist. Use XLSX when the user needs tracking or sorting; otherwise DOCX. |
| Executive brief (Справка для руководства) | Meeting, lecture, interview, presentation | `executive-brief.docx` | One paragraph: subject, material outcome, decision or takeaway, immediate implication, and unresolved issue if any. | Default for every content type on full analysis; omit only when the user asks for a narrower set. |

#### Default document selection by content type

| Content type | Document types produced on full analysis |
|---|---|
| Meeting | `protocol.docx`, `summary.docx`, `analytical.docx`, `decision-register.xlsx` when decisions exist, `assignment-list.xlsx` when assignments exist, `detailed-minutes.docx`, `action-plan.docx` when next steps or assignments exist, `executive-brief.docx`. |
| Lecture | `summary.docx`, `analytical.docx`, `detailed-minutes.docx`, `presentation-outline.docx`, `knowledge-article.docx`, `q-and-a-log.docx` when Q&A is present, `executive-brief.docx`. |
| Interview | `q-and-a-log.docx`, `summary.docx`, `analytical.docx`, `executive-brief.docx`. Produce `detailed-minutes.docx` only when requested. |
| Presentation | `presentation-outline.docx` by default, or `presentation-outline.pptx` when requested, plus `summary.docx`, `analytical.docx`, `executive-brief.docx`. |

`protocol_not_applicable` is an internal routing signal only. Never show it or
any JSON protocol to the user. For non-meetings, skip protocol generation and
say in the chat: "This is a lecture. I've prepared a summary and analysis
instead of a meeting protocol." Adapt the content type in that sentence when
needed. Never fabricate decisions, assignments, participants, or deadlines to
fit the meeting schema.

Produce selected artifacts in this order: `transcript.txt`, the primary
structured document or outline, operational XLSX documents, detailed minutes,
`summary.docx` when applicable, `analytical.docx`, then `executive-brief.docx`.
If the user
asks for “just summary”, produce only the summary. “Full analysis” means the
default document set for the selected content type, subject to the evidence
conditions in the document menu.

#### 1. Summary (саммари)

A quick-scan brief in `summary.docx`. For a meeting, state the topic, key
decisions, and assignments. For other content, state the subject, key concepts,
examples, and any Q&A. Do not introduce facts that are not in the transcript.

Scale summary depth to the recording duration:

- Under 15 minutes: 2–3 paragraphs.
- 15–60 minutes: about one page (5–8 paragraphs), with one paragraph per major topic.
- Over 60 minutes: 1–2 pages (8–15 paragraphs), organized with topic headings.

Each topic section must state what was discussed, the key points, any decisions
or outcomes, and unresolved items. Keep all existing grounding and
non-fabrication guardrails.

For a lecture, `summary.docx` must include the title, speaker, duration, key
topics as a bullet list, key concepts with timestamps, and a Q&A summary when
present.

#### 2. Protocol (протокол)

For meetings, create `protocol.docx` as the primary deliverable. Include the
meeting metadata, participants, agenda, decisions, assignments, open questions,
risks, next steps, and quality warnings. Every extracted item must retain its
`source_quote` grounding; assignments must include assignee and deadline. Use
an internal structured representation if needed to validate the content, but do
not deliver that representation as JSON.

#### 3. Analytical note (аналитическая записка)

Create `analytical.docx` with these sections:

1. **Контекст встречи.** Connection to prior meetings, related tasks, and strategic goals.
2. **Анализ решений.** What was decided, deferred, and left implicit.
3. **Оценка рисков.** What may fail, including schedule risks and resource gaps.
4. **Рекомендации.** The agent's recommendations from the full transcript and, when explicitly requested, permitted corporate context.
5. **Тренды.** Recurring themes, unresolved issues, and decision-making patterns across meetings.

Clearly separate evidence from inference. If prior meetings or corporate context
were not provided or explicitly requested through an allowed MCP system, say
that the corresponding conclusion is limited to this transcript. Never present
an inference, a missing fact, or a recommendation as an explicit decision.

### Phase 5: User-facing output

Return a concise human-readable handoff that names the detected content type
and links or attaches every generated artifact. Do not return raw JSON,
`protocol_not_applicable`, internal routing metadata, or validation payloads.
For a non-meeting, explicitly state that a protocol was not generated because
the source is not a meeting, then name the documents prepared instead.

### Phase 6: Enrich (MCP — OPT-IN ONLY)

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
