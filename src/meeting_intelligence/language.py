from __future__ import annotations

import re

_MISDETECTED_RU_PATTERNS = re.compile(
    r"\b(?:"
    r"akhmetov|yakovlev|ivanovich|petrovich|sergeevich|alexandrovich|"
    r"vladimirovich|ovna|evna|ichna|"
    r"minjust|minfin|minzdrav|minpromtorg|minobrnauki|mincifry|"
    r"rosstandart|rostandart|rospotrebnadzor|rosreestr|roskomnadzor|"
    r"gosduma|sovfed|pravitelstvo|"
    r"russian federation"
    r")\b",
    re.IGNORECASE,
)

def _is_probably_russian_mistranscribed_as_english(
    transcript: str, detected_language: str
) -> bool:
    """Identify English transcripts with a concentrated set of Russian cues."""
    if detected_language.lower() != "en":
        return False

    word_count = len(re.findall(r"\b\w+\b", transcript))
    russian_cue_count = len(_MISDETECTED_RU_PATTERNS.findall(transcript))
    return russian_cue_count >= 2 and russian_cue_count / max(word_count, 1) >= 0.01
