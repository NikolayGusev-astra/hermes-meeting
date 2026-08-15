# ALD Pro lectures → meeting-intelligence pipeline: full work plan

> **For Hermes:** Execute via subagent-driven-development, phase-by-phase. Each phase has an acceptance gate; do not advance until it is green. Push to GitHub only on explicit user «ок».

**Goal:** Extract and process the ALD Pro «Записи лекций» video recordings (Confluence ALD2 page 303793144) into DOCX deliverables using the `hermes-meeting` plugin; refine the plugin where the lecture corpus exposes gaps; push the updates to `github.com/NikolayGusev-astra/hermes-meeting`.

**Architecture:** lecture catalog (already built in llm-wiki, see `aldpro-lectures-study` skill) → per-meeting video source → `meeting transcribe --language ru` (faster-whisper `large-v3-turbo`) → content-type detection → DOCX artifacts (summary/analytical, protocol for meetings) → NAMING-compliant Russian folders/files → ingest summaries back into llm-wiki + ZVec.

**Tech Stack:** faster-whisper (CTranslate2), yt-dlp, python-docx, LM Studio (qwen2.5-7b, bge-m3) or Codex for protocol extraction, Hermes terminal (MSYS, drive-letter paths), GitHub CLI/HTTPS.

**Push-gate:** local commits only until user reviews; push to `main` only on explicit «ок».

---

## Phase 0 — Feasibility & inventory (gate: source map confirmed)

**Objective:** Confirm what is actually downloadable before committing the corpus to pipeline runs.

**Files:** `references/lecture-video-sources.md` (new, in repo docs/).

**Step 1: Source-type matrix.** From the llm-wiki catalog, classify each recording URL:
- `dion.vc/video/...` and `video.dion.vc/video/...` — **PROBE REQUIRED** (see step 3)
- `disk.astralinux.ru/s/...` (3.0.0, 3.1.0) — has password, share download
- `video.dion.vc/<bare-id>` (older 2.4.0) — probe
- External (disk.yandex.ru) — 3.0.0 МКЦ/МРД material

**Step 2: N** — number of distinct recordings. Tally the catalog: ~40 rows total, ~35 unique dion.vc/video.dion.vc links, ~5 disk.astralinux.ru shares.

**Step 3: dion.vc feasibility probe (P0 blocker):**
```bash
# Already run 2026-08-12:
"/c/Users/n.gusev/AppData/Local/Programs/Python/Python311/python.exe" -m yt_dlp \
  --skip-download --no-warnings "https://dion.vc/video/<id>"
# RESULT: ERROR: Unsupported URL — dion.vc is a CSP web-app, NOT yt-dlp-downloadable.
```
**Decision gate:** dion.vc is an authenticated/JS player. Three options to resolve (pick via clarify with user):
- (A) Browser-automation capture (`browser_navigate` + page inspect for the real stream URL behind CSP / localdaemon.dion.vc:44951) — feasible but per-video manual.
- (B) Ask the recordings' owner (Удовенко/Кораченцева) for direct .mp4/.mkv copies or a share — cleanest for bulk.
- (C) Process only the subset that IS downloadable (disk.astralinux.ru shares + any direct-hosted files), defer dion.vc.
**Gate:** a confirmed, reproducible download path for at least the priority recordings before Phase 1 bulk runs.

## Phase 1 — Plugin baseline & commit WIP (gate: clean status)

**Objective:** Land the existing uncommitted `_yt_proxy_for_url` platform-routing fix so the tree is clean before new work.

**Files:** `src/meeting_intelligence/sources.py` (already modified, working-copy).

**Step 1:** Review the diff (38 insertions) — it adds `_PROXY_DOMAINS` (YouTube), `_DIRECT_DOMAINS` (VK/Rutube), `_yt_proxy_for_url()`, routes `--proxy`. Matches the meeting-intelligence skill's platform-aware proxy design. No test yet.

**Step 2:** Add unit test `tests/unit/test_sources_proxy.py` asserting: YouTube→`MEETING_YT_PROXY` (or socks5 default), vkvideo.ru→direct (`""`), rutube→direct, unknown→direct. RED first.

**Step 3:** Run test, confirm GREEN. Run full `pytest tests -q` to ensure no regression.

**Step 4:** Commit locally: `git add src/meeting_intelligence/sources.py tests/unit/test_sources_proxy.py && git commit -m "feat: platform-aware proxy routing (YT proxy / RU direct)"`. **Do NOT push.**

**Gate:** `git status` clean (except nothing), pytest green.

## Phase 2 — Batch download of downloadable recordings (gate: N wavs staged)

**Objective:** Pull the recordings that are obtainable (per Phase 0 decision) into a staging dir.

**Files:** `scripts/download_lecture_videos.py` (new, or drive manually per source type).

**Step 1:** For disk.astralinux.ru shares with known passwords — download via yt-dlp or direct HTTP with the password (evaluate share type first; may need cookie/session).

**Step 2:** For direct-hosted files (e.g. attached .mp4 if any exist under the page) — `curl --noproxy '*'` download.

**Step 3:** Name each staged file with the meeting date + topic slug, e.g. `2026-07-08_модуль-синхронизации.mp4`.

**Gate:** all obtainable sources present as local audio/video files with correct names; count matches Phase 0 obtainable set.

## Phase 3 — Transcribe each recording (gate: transcripts exist)

**Objective:** Run Whisper transcription with Russian forced.

**Files:** `C:\Work\hermes\meeting\artifacts\` (output root).

**Step 1:** For each staged file:
```bash
http_proxy='' https_proxy='' HTTP_PROXY='' HTTPS_PROXY='' no_proxy='*' \
  C:/Users/n.gusev/AppData/Local/Programs/Python/Python311/python.exe -m meeting_intelligence \
  transcribe "C:/Work/hermes/meeting/artifacts/2026-07-08_модуль-синхронизации.mp4" --language ru
```
Use `--model large-v3-turbo` (GPU) / `--model medium` (CPU). Run `background=true, notify_on_complete=true` (transcription is silent for minutes; foreground timeout 600s will cut long videos).

**Step 2:** Pre-check VRAM: `nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv` — if <3GB free, free LM Studio/llama-server first.

**Step 3:** For each transcript, run garbage-filter sanity: `grep -cE '^\s*[а-я]\s*$' transcript.txt` (should be ~0 after filter).

**Gate:** one `.transcript.txt` per source; Russian correct (spot-check patronymics/institutional terms), no garbled-English misdetect.

## Phase 4 — Content-type detection + LLM protocol/summary (gate: per-meeting JSON)

**Objective:** Classify each transcript and produce structured JSON.

**Files:** `artifacts/<folder>/analysis.json`, `protocol.json`, etc.

**Step 1:** Run `meeting agent-transcript transcript.txt` to get agent-consumable JSON.

**Step 2:** Classify (meeting vs lecture vs interview vs presentation) from speakers/decisions/assignments. Most ALD Pro tech-demos are **lectures** (single/few speakers, topics, Q&A) → summary + analytical, NO protocol.

**Step 3:** Generate summaries via the selected LLM backend (ask user via `clarify()`: Codex vs current-model vs LM Studio qwen2.5-7b). Ground every decision/assignment in source_quote.

**Step 4:** Scale summary depth by duration (>60 min → 1–2 pages with topic headings).

**Gate:** per-meeting JSON artifacts present, content type correct, no `protocol_not_applicable` returned to user.

## Phase 5 — DOCX generation + NAMING compliance (gate: DOCX-only output)

**Objective:** Produce the user-facing deliverables in Russian-named files/folders.

**Files:** `artifacts/<YYYY-MM-DD>_<тип>_<тема>/` with Russian artifact names.

**Step 1:** Map JSON → DOCX via `meeting generate-docx --type summary|analytical|protocol --input ... --output ...`.

**Step 2:** Enforce NAMING.md:
- Folder: `{YYYY-MM-DD}_{встреча|лекция|интервью|презентация}_{тема}`
- Files: `Протокол.docx`, `Саммари.docx`, `Аналитическая_записка.docx`, `Справка.docx`, `Журнал_вопросов_ответов.docx`, `Подробный_конспект.docx`, `Статья.docx`, `План_презентации.docx`, `Реестр_решений.xlsx`, `Список_поручений.xlsx` (all Russian).

**Gate:** output dir contains NO `.md`/`.json` visible to user; all artifacts `.docx` (or `.xlsx`); folder/file names all Russian; user informed "Detected: lecture (N min, Russian). Producing: Саммари.docx, Аналитическая_записка.docx."

## Phase 6 — Knowledge ingestion (gate: llm-wiki + ZVec hit)

**Objective:** Fold lecture summaries back into the knowledge base.

**Files:** `C:\Work\llm-wiki\aldpro\лекции_обучение\` (add per-lecture summary notes), ZVec index.

**Step 1:** For each processed lecture, write a summary note under `лекции_обучение\материалы\` or a per-lecture note, referencing the recording, pageId, and linked skills (reuse `aldpro-lectures-study` skill).

**Step 2:** Update `aldpro\index.md` + `log.md`.

**Step 3:** Run wiki→ZVec autosync (see `aldpro-lectures-study` skill "Ingesting into auto-rag"):
```bash
cd /c/Users/n.gusev/rag-deploy && NO_PROXY="127.0.0.1,localhost" \
  "/c/Users/n.gusev/AppData/Local/Programs/Python/Python311/python.exe" \
  "C:\Users\n.gusev\AppData\Local\hermes\scripts\wiki-a-autosync.py"
```
Verify via direct ZVec: `$PY rag_search.py "<new slug>" --json` returns the new page.

**Gate:** new summary findable via `rag_search.py` (NOT `mcp__auto_rag__search` — that reports zvec unavailable).

## Phase 7 — Plugin refinement from corpus learnings (gate: pytest green + review)

**Objective:** Apply any gaps the lecture corpus exposes (e.g. NAMING enforcement gaps already flagged in the skill; dion.vc extractor if option A chosen).

**Files:** varies. Candidate: add a `meeting list-sources` command or a dion.vc extractor module if Phase 0 chose option A.

**Step 1:** Run `cursor-team-kit-review-and-ship`-style review of the changed tree.
**Step 2:** For each confirmed gap, `pstack-tdd` a fix (RED→GREEN→commit locally).
**Step 3:** Full `pytest tests -q` green.

**Gate:** clean diff, tests green, each change documented.

## Phase 8 — Push to GitHub (gate: explicit user «ок»)

**Objective:** Publish to `github.com/NikolayGusev-astra/hermes-meeting`.

**Step 1:** `git status`, `git diff --stat` review; confirm no secrets (`.env`, tokens).
**Step 2:** `git push origin main` ONLY after user explicitly approves.

**Gate:** pushed; remote state confirmed via `git status` / `git ls-remote`.

---

## Status log

- 2026-08-12: Phase 0 probe run — dion.vc returns `ERROR: Unsupported URL` via yt-dlp (CSP web-app, likely authenticated). **Blocker to resolve via clarify** (options A/B/C above).
- 2026-08-12: Repo `hermes-meeting` on `main`, one uncommitted `_yt_proxy_for_url` change in `sources.py` (Phase 1 pending).
