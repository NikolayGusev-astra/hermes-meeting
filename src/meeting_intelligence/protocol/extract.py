from __future__ import annotations

import json
import logging
import re

log = logging.getLogger("meeting")

def _repair_json(text: str):
    """Try to fix common LLM JSON errors: single quotes, trailing commas."""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    cleaned = re.sub(r"'([^']*)'(\s*:)", r'"\1"\2', cleaned)
    cleaned = re.sub(r":\s*'([^']*)'", r': "\1"', cleaned)
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

def _build_protocol_chunk(transcript: str, model: str, allow_cloud: bool) -> dict:
    from .. import cli

    cli.enforce_cloud_policy(allow_cloud)
    from openai import OpenAI

    client = OpenAI(base_url=cli.LLM_BASE_URL, api_key=cli.LLM_API_KEY)
    # Strip segment IDs and duplicate speaker labels for cleaner LLM input
    import re as _re

    clean_transcript = _re.sub(
        r"^seg_\d+\s+SPEAKER_(\d+)\s+\[\d{2}:\d{2}->\d{2}:\d{2}\]\s+SPEAKER_\d+\s+\|\s+",
        r"[\g<1>] ",
        transcript,
        flags=_re.MULTILINE,
    )
    system = (
        "You are a meeting secretary. Extract protocol from transcript ONLY from explicit statements. "
        "Return VALID JSON ONLY. NO markdown fences. NO trailing commas. Use DOUBLE QUOTES. "
        "Keys exactly: participants, agenda, decisions, assignments, open_questions, unclear. "
        "participants: array of {\"name\": \"SPEAKER_NN\", \"source_quote\": \"first line spoken by this speaker\"}. "
        "decisions: array of {\"text\": \"decision\", \"source_quote\": \"exact words from transcript\", \"approved_by\": [\"SPEAKER_NN\"]}. "
        "assignments: array of {\"task\": \"task\", \"assignee\": \"SPEAKER_NN\", \"deadline\": \"date or not_set\", \"source_quote\": \"exact words\"}. "
        "CRITICAL: name and assignee fields MUST contain ONLY SPEAKER_NN (SPEAKER_00, SPEAKER_01, etc). Never use real names. "
        "source_quote MUST be exact text from transcript — copy VERBATIM, do not paraphrase."
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": clean_transcript},
            ],
            temperature=0.1,
        )
    except Exception as exc:
        cli._handle_exception(exc)
    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        content = "\n".join(content.splitlines()[1:])
    if content.endswith("```"):
        content = "\n".join(content.splitlines()[:-1])
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        repaired = _repair_json(content)
        if repaired is not None:
            log.warning("LLM JSON repaired: %s", exc)
            return repaired
        cli.fail(f"LLM returned invalid JSON for protocol: {exc}\nRaw: {content[:500]}")
