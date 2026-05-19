"""Layer 1 — prompt normalization.

Reduces variation that attackers exploit to slip past pattern matchers:

* Unicode NFKC + categorical stripping of format/control characters
  (zero-width joiner, RTL override, tag characters, ...).
* Whitespace collapsing (multiple spaces → single space; CR/LF/TAB → space).
* Best-effort base64 / hex unwrapping, capped at 3 levels deep — if a
  payload is wrapped more than three deep, the outer decoded form is
  used and a ``NormalizationResult.deep_encoding`` flag is set so layer 2
  can flag it as suspicious. Unwrapping is bounded by max byte length to
  prevent zip-bomb-style decompression attacks.

Normalization is pure: same input → same output. It produces a
``NormalizationResult`` carrying both the normalized text and the
metadata layer 2 needs (decoded depth, removed character counts, byte
deltas) without raw prompt slices.
"""
from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field

_MAX_UNWRAP_DEPTH = 3
_MAX_DECODED_BYTES = 64_000  # absolute cap — never produce a bigger normalized buffer
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/=\s]{16,}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F\s]{16,}$")
_WHITESPACE_COLLAPSE_RE = re.compile(r"\s+")
# Format/control unicode categories we strip outright.
_STRIP_CATEGORIES = frozenset({"Cf", "Cc"})


@dataclass(frozen=True)
class NormalizationResult:
    text: str
    original_length: int
    normalized_length: int
    removed_format_chars: int
    unwrap_depth: int
    deep_encoding: bool = False
    encoding_chain: tuple[str, ...] = field(default_factory=tuple)


def normalize(text: str) -> NormalizationResult:
    """Apply layer-1 normalization. Always returns a result, never raises.

    The unwrap pass attempts base64 and hex decoding for content that
    *looks* like one of those formats. Decode failures are silent — the
    point is to expose hidden payloads, not to validate the encoding.
    """
    original_length = len(text)

    nfkc = unicodedata.normalize("NFKC", text)
    stripped_chars: list[str] = []
    removed = 0
    for ch in nfkc:
        if unicodedata.category(ch) in _STRIP_CATEGORIES:
            removed += 1
            continue
        stripped_chars.append(ch)
    stripped = "".join(stripped_chars)

    collapsed = _WHITESPACE_COLLAPSE_RE.sub(" ", stripped).strip()

    unwrapped, depth, chain = _unwrap(collapsed)
    deep = depth >= _MAX_UNWRAP_DEPTH

    return NormalizationResult(
        text=unwrapped,
        original_length=original_length,
        normalized_length=len(unwrapped),
        removed_format_chars=removed,
        unwrap_depth=depth,
        deep_encoding=deep,
        encoding_chain=tuple(chain),
    )


def _unwrap(text: str) -> tuple[str, int, list[str]]:
    """Try to decode base64/hex layers. Conservative — only operates when
    the text looks plausibly like a single encoded blob."""
    current = text
    depth = 0
    chain: list[str] = []
    for _ in range(_MAX_UNWRAP_DEPTH):
        candidate = current.strip()
        if _looks_like_base64(candidate):
            try:
                decoded_bytes = base64.b64decode(candidate, validate=False)
            except (binascii.Error, ValueError):
                break
            if not decoded_bytes or len(decoded_bytes) > _MAX_DECODED_BYTES:
                break
            try:
                decoded = decoded_bytes.decode("utf-8")
            except UnicodeDecodeError:
                break
            if decoded == candidate:
                break
            current = decoded
            depth += 1
            chain.append("base64")
            continue
        if _looks_like_hex(candidate):
            try:
                decoded_bytes = bytes.fromhex(candidate.replace(" ", ""))
            except ValueError:
                break
            if not decoded_bytes or len(decoded_bytes) > _MAX_DECODED_BYTES:
                break
            try:
                decoded = decoded_bytes.decode("utf-8")
            except UnicodeDecodeError:
                break
            current = decoded
            depth += 1
            chain.append("hex")
            continue
        break
    return current, depth, chain


def _looks_like_base64(s: str) -> bool:
    if not _BASE64_RE.fullmatch(s):
        return False
    compact = re.sub(r"\s", "", s)
    return len(compact) % 4 == 0 and len(compact) >= 16


def _looks_like_hex(s: str) -> bool:
    compact = re.sub(r"\s", "", s)
    if len(compact) < 16 or len(compact) % 2 != 0:
        return False
    return bool(_HEX_RE.fullmatch(s))
