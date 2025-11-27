import re
from typing import Any, Dict, List, Optional, Tuple

# Simple, dependency-free chunker used by the SSML builder.
# It keeps cost low by avoiding heavy NLP while still giving predictable splits.

DEFAULT_MAX_CHARS = 240
MIN_FRAGMENT_CHARS = 15

Marker = Dict[str, Any]
Chunk = Dict[str, Any]


def _parse_inline_marker(raw: str) -> Marker:
    """
    Parse an inline marker of the form [[voice=en-US-JennyNeural;emotion=cheerful;intensity=2;pitch=5;speed=95]]
    Returns a dict of overrides; unknown keys are ignored.
    """
    marker: Marker = {}
    pairs = [p.strip() for p in raw.split(";") if p.strip()]
    for pair in pairs:
        if "=" not in pair:
            continue
        key, val = pair.split("=", 1)
        key = key.strip().lower()
        val = val.strip()
        if not val:
            continue
        if key == "voice":
            marker["voice"] = val
        elif key in ("emotion", "style"):
            marker["emotion"] = val
        elif key in ("intensity", "styledegree"):
            try:
                marker["intensity"] = int(val)
            except ValueError:
                pass
        elif key == "pitch":
            try:
                marker["pitch"] = int(val)
            except ValueError:
                pass
        elif key in ("speed", "rate"):
            try:
                marker["speed"] = int(val)
            except ValueError:
                pass
        elif key == "volume":
            try:
                marker["volume"] = float(val)
            except ValueError:
                pass
    return marker


def _extract_markers(text: str) -> Tuple[str, List[Tuple[int, Marker]]]:
    """
    Remove inline markers and return cleaned text + list of (index, marker).
    Markers are positioned by approximate character offsets for later alignment.
    """
    markers: List[Tuple[int, Marker]] = []
    cleaned_parts: List[str] = []
    cursor = 0

    for match in re.finditer(r"\[\[(.*?)\]\]", text):
        start, end = match.span()
        cleaned_parts.append(text[cursor:start])
        marker_text = match.group(1)
        marker = _parse_inline_marker(marker_text)
        markers.append((len("".join(cleaned_parts)), marker))
        cursor = end
    cleaned_parts.append(text[cursor:])
    return "".join(cleaned_parts).strip(), markers


def _split_basic(text: str) -> List[str]:
    """
    Split text on strong punctuation while keeping delimiters attached.
    """
    if not text:
        return []

    parts: List[str] = []
    # Capture sentence enders, commas/semicolons, ellipses, em dashes.
    tokens = re.split(r"(\.{3,}|…|[.!?]|[,;]|—)", text)
    # Re-attach delimiters to preceding text.
    buf = ""
    for tok in tokens:
        if tok is None or tok == "":
            continue
        if re.fullmatch(r"(\.{3,}|…|[.!?]|[,;]|—)", tok):
            buf += tok
            parts.append(buf.strip())
            buf = ""
        else:
            if buf:
                # Previous chunk without terminal punctuation; push and start new
                parts.append(buf.strip())
                buf = ""
            buf += tok
    if buf.strip():
        parts.append(buf.strip())
    return [p for p in parts if p]


def _merge_short_fragments(chunks: List[str], min_len: int = MIN_FRAGMENT_CHARS) -> List[str]:
    merged: List[str] = []
    for chunk in chunks:
        if merged and len(chunk) < min_len:
            merged[-1] = (merged[-1] + " " + chunk).strip()
        else:
            merged.append(chunk)
    return merged


def _split_long_chunks(chunks: List[str], max_len: int = DEFAULT_MAX_CHARS) -> List[str]:
    """
    Further split chunks that exceed max_len on whitespace.
    """
    result: List[str] = []
    for chunk in chunks:
        if len(chunk) <= max_len:
            result.append(chunk)
            continue
        words = chunk.split()
        buf: List[str] = []
        for word in words:
            if sum(len(w) for w in buf) + len(buf) + len(word) > max_len and buf:
                result.append(" ".join(buf))
                buf = [word]
            else:
                buf.append(word)
        if buf:
            result.append(" ".join(buf))
    return result


def _apply_markers_to_chunks(chunks: List[str], markers: List[Tuple[int, Marker]]) -> List[Chunk]:
    """
    Distribute inline markers to the chunk that starts at/after the marker offset.
    """
    result: List[Chunk] = []
    offset = 0
    marker_idx = 0
    for chunk in chunks:
        meta: Chunk = {"content": chunk}
        end = offset + len(chunk)
        while marker_idx < len(markers) and markers[marker_idx][0] <= end:
            meta.update(markers[marker_idx][1])
            marker_idx += 1
        result.append(meta)
        offset = end + 1  # account for removed whitespace
    return result


def process_text(
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    min_fragment_chars: int = MIN_FRAGMENT_CHARS,
) -> List[Chunk]:
    """
    Convert raw text (with optional inline markers) into chunk dicts.

    Inline markers: [[emotion=cheerful;intensity=2;pitch=5;speed=95]]
    """
    cleaned, markers = _extract_markers(text or "")
    splits = _split_basic(cleaned)
    splits = _merge_short_fragments(splits, min_fragment_chars)
    splits = _split_long_chunks(splits, max_chars)
    chunks = _apply_markers_to_chunks(splits, markers)
    # Ensure keys exist
    for chunk in chunks:
        chunk.setdefault("voice", None)
        chunk.setdefault("emotion", None)
        chunk.setdefault("intensity", None)
        chunk.setdefault("pitch", None)
        chunk.setdefault("speed", None)
        chunk.setdefault("volume", None)
    return chunks


__all__ = ["process_text", "Chunk", "Marker"]
