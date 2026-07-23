from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("meeting")

def _verify_protocol(
    protocol: dict, transcript: str, model: str, allow_cloud: bool
) -> dict:
    """Second-pass verification. Falls back to original protocol on failure."""
    if not _protocol_verification_enabled():
        return protocol
    enforce_cloud_policy(allow_cloud)
    from openai import OpenAI

    verify_url = os.getenv("MEETING_VERIFY_BASE_URL", LLM_BASE_URL)
    verify_key = os.getenv("MEETING_VERIFY_API_KEY", LLM_API_KEY)
    verify_model = os.getenv("MEETING_VERIFY_MODEL", model)
    # Use first 3000 chars of transcript as summary to avoid context overflow
    transcript_summary = transcript[:3000]
    prompt = (
        "Verify this protocol against the transcript excerpt. "
        "Find: missed decisions, wrong assignees, hallucinated participants. "
        "Output corrected JSON.\n\n"
        f"Protocol:\n{json.dumps(protocol, ensure_ascii=False)}\n\n"
        f"Transcript (first 3000 chars):\n{transcript_summary}"
    )
    client = OpenAI(base_url=verify_url, api_key=verify_key)
    try:
        content = (
            client.chat.completions.create(
                model=verify_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                timeout=60,
            )
            .choices[0]
            .message.content.strip()
        )
    except Exception as exc:
        log.warning("Protocol verification failed, using original: %s", exc)
        return protocol
    verified = _repair_json(content)
    if not isinstance(verified, dict):
        log.warning("Verification returned invalid JSON, using original")
        return protocol
    return verified

def _protocol_verification_enabled() -> bool:
    return os.getenv("MEETING_PROTOCOL_VERIFY", "true").lower() != "false"
