"""Local LLM speaker attribution for pseudo-diarized transcripts."""
from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI


_SPEAKER_PATTERN = re.compile(r"SPEAKER_(\d+)")


def _speaker_labels(transcript: str) -> set[str]:
    return {f"SPEAKER_{number}" for number in _SPEAKER_PATTERN.findall(transcript)}


def _extract_json(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def attribute_speakers(
    transcript: str, model: str, allow_cloud: bool, timeout: int = 90
) -> dict:
    """Map SPEAKER_NN labels to participant names through the local LLM."""
    labels = _speaker_labels(transcript)
    if not labels:
        return {"ok": True, "mapping": {}, "err": None}

    from . import pipeline

    try:
        pipeline.enforce_cloud_policy(allow_cloud)
        client = OpenAI(base_url=pipeline.LLM_BASE_URL, api_key=pipeline.LLM_API_KEY)
        prompt = (
            "Транскрипт встречи. Каждый фрагмент размечен SPEAKER_NN. Определи реальные "
            "имена участников, которые упоминаются в тексте по обращениям, контексту и "
            "самопредставлениям. Не выдумывай: если имя неопределимо, оставь SPEAKER_NN. "
            "Ответь только JSON-объектом вида {\"SPEAKER_00\": \"Иван\"}.\n\n"
            f"Список спикеров: {', '.join(sorted(labels))}\n\n"
            f"Транскрипт:\n{transcript[:6000]}"
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            timeout=timeout,
        )
        content = response.choices[0].message.content or ""
        payload = _extract_json(content)
        mapping = {
            key: value.strip()
            for key, value in payload.items()
            if key in labels and isinstance(value, str) and value.strip()
        }
        return {"ok": True, "mapping": mapping, "err": None}
    except Exception as exc:
        return {"ok": False, "mapping": {}, "err": str(exc)}
