import html
import re
from typing import Any, Dict, List, Optional, Tuple

Chunk = Dict[str, Any]

STYLEDEGREE_MAP = {
    1: 0.7,
    2: 1.0,
    3: 1.3,
}

MAX_RATE = 50  # percent
MIN_RATE = -50
MAX_PITCH = 50  # percent
MIN_PITCH = -50
MAX_VOLUME_DB = 10.0
MIN_VOLUME_DB = -10.0

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "if",
    "then",
    "else",
    "this",
    "that",
    "of",
    "for",
    "to",
    "in",
    "on",
    "with",
    "at",
    "by",
    "from",
}


def _clamp(val: float, low: float, high: float) -> Tuple[float, Optional[str]]:
    if val < low:
        return low, f"clamped {val} -> {low}"
    if val > high:
        return high, f"clamped {val} -> {high}"
    return val, None


def _format_percent(val: float) -> str:
    return f"{val:+.0f}%"


def _format_volume_db(val: float) -> str:
    return f"{val:+.1f}dB"


def _styledegree(intensity: Optional[int]) -> float:
    if intensity is None:
        return 1.0
    return STYLEDEGREE_MAP.get(max(1, min(3, intensity)), 1.0)


def _find_keywords(text: str, max_keywords: int = 3) -> List[str]:
    words = re.findall(r"\b[\w']+\b", text)
    scored = []
    for w in words:
        lw = w.lower()
        if lw in STOPWORDS or len(w) < 5:
            continue
        scored.append((len(w), w))
    scored.sort(reverse=True)
    return [w for _, w in scored[:max_keywords]]


def _apply_emphasis(text: str, keywords: List[str]) -> str:
    result = text
    for kw in keywords:
        pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
        if pattern.search(result):
            result = pattern.sub(lambda m: f"<emphasis level=\"moderate\">{m.group(0)}</emphasis>", result, count=1)
    return result


def _pause_for_chunk(chunk_text: str) -> Optional[str]:
    if not chunk_text:
        return None
    if chunk_text.endswith(("…", "...")):
        return "400ms"
    if chunk_text.endswith("—"):
        return "350ms"
    if chunk_text.endswith((",", ";", ":")):
        return "220ms"
    if chunk_text.endswith((".", "!", "?")):
        return "280ms"
    return None


def _escape_text(text: str) -> str:
    return html.escape(text, quote=True)


def build_ssml(
    voice: str,
    chunks: List[Chunk],
    *,
    auto_pauses: bool = True,
    auto_emphasis: bool = True,
    auto_breaths: bool = False,  # reserved for future use
    global_rate: Optional[int] = None,
    global_pitch: Optional[int] = None,
    global_volume: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build SSML string from chunk map and return ssml + resolved chunk_map + warnings.
    Supports per-chunk voice changes for multi-speaker dialogue.
    """
    warnings: List[str] = []
    resolved_chunks: List[Dict[str, Any]] = []
    ssml_parts: List[str] = []
    current_voice = None  # Track voice changes, start with None

    for idx, raw_chunk in enumerate(chunks):
        text = str(raw_chunk.get("content", "")).strip()
        if not text:
            continue

        chunk_voice = raw_chunk.get("voice") or voice
        emotion = raw_chunk.get("emotion")
        intensity = raw_chunk.get("intensity")

        # Resolve prosody with global fallbacks
        rate_val = raw_chunk.get("speed", raw_chunk.get("rate", global_rate if global_rate is not None else 0))
        pitch_val = raw_chunk.get("pitch", global_pitch if global_pitch is not None else 0)
        volume_val = raw_chunk.get("volume", global_volume if global_volume is not None else 0.0)

        # Clamp values
        rate_val, warn = _clamp(float(rate_val), MIN_RATE, MAX_RATE)
        if warn:
            warnings.append(f"chunk {idx}: rate {warn}")
        pitch_val, warn = _clamp(float(pitch_val), MIN_PITCH, MAX_PITCH)
        if warn:
            warnings.append(f"chunk {idx}: pitch {warn}")
        volume_val, warn = _clamp(float(volume_val), MIN_VOLUME_DB, MAX_VOLUME_DB)
        if warn:
            warnings.append(f"chunk {idx}: volume {warn}")

        rate_str = _format_percent(rate_val)
        pitch_str = _format_percent(pitch_val)
        volume_str = _format_volume_db(volume_val)

        # Escape and optionally emphasize
        escaped_text = _escape_text(text)
        if auto_emphasis:
            keywords = _find_keywords(text)
            escaped_text = _apply_emphasis(escaped_text, keywords)

        # Wrap with express-as if emotion present
        if emotion:
            degree = _styledegree(intensity)
            chunk_ssml = (
                f'<mstts:express-as style="{html.escape(str(emotion))}" styledegree="{degree:.2f}">'
                f"<prosody rate=\"{rate_str}\" pitch=\"{pitch_str}\" volume=\"{volume_str}\">{escaped_text}</prosody>"
                f"</mstts:express-as>"
            )
        else:
            chunk_ssml = f"<prosody rate=\"{rate_str}\" pitch=\"{pitch_str}\" volume=\"{volume_str}\">{escaped_text}</prosody>"

        # Auto pauses
        if auto_pauses:
            pause = _pause_for_chunk(text)
            if pause:
                chunk_ssml += f"<break time=\"{pause}\"/>"

        # Handle voice changes - open voice tag if needed, close previous if changing
        if chunk_voice != current_voice:
            if current_voice is not None:
                # Close previous voice
                ssml_parts.append("</voice>")
            # Open new voice
            ssml_parts.append(f"<voice name=\"{html.escape(chunk_voice)}\">")
            current_voice = chunk_voice

        ssml_parts.append(chunk_ssml)
        resolved_chunks.append(
            {
                "content": text,
                "voice": chunk_voice,
                "emotion": emotion,
                "intensity": intensity,
                "rate": rate_val,
                "pitch": pitch_val,
                "volume": volume_val,
            }
        )

    # Close final voice tag if we opened one
    if current_voice is not None:
        ssml_parts.append("</voice>")
    
    body = "".join(ssml_parts)
    speak = (
        "<speak version=\"1.0\" xmlns=\"http://www.w3.org/2001/10/synthesis\" "
        "xmlns:mstts=\"https://www.w3.org/2001/mstts\" xml:lang=\"en-US\">"
        f"{body}"
        "</speak>"
    )    # Length guard
    if len(speak) > 50000:
        warnings.append(f"SSML length {len(speak)} exceeded 50k; consider chunking input further.")

    return {
        "ssml": speak,
        "chunk_map": resolved_chunks,
        "warnings": warnings,
    }


__all__ = ["build_ssml"]
