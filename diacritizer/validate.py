"""The validator is the authority, not the model.

Rule: the output may differ from the input only by Arabic diacritics (tashkeel and Quranic marks).
Strip diacritics from both sides and the remaining "skeleton" must be identical, character for character.
"""
from __future__ import annotations

from dataclasses import dataclass

# Unicode ranges treated as diacritics (may be added or changed freely):
#   U+0610..U+061A  Arabic signs (honorifics, small high marks)
#   U+064B..U+065F  tashkeel: fathatan .. wavy hamza below
#   U+0670          superscript alef
#   U+06D6..U+06DC, U+06DF..U+06E4, U+06E7..U+06E8, U+06EA..U+06ED  Quranic annotation marks
_DIACRITIC_RANGES = (
    (0x0610, 0x061A),
    (0x064B, 0x065F),
    (0x0670, 0x0670),
    (0x06D6, 0x06DC),
    (0x06DF, 0x06E4),
    (0x06E7, 0x06E8),
    (0x06EA, 0x06ED),
)


def is_diacritic(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _DIACRITIC_RANGES)


def strip_diacritics(text: str) -> str:
    return "".join(ch for ch in text if not is_diacritic(ch))


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""
    position: int = -1   # index in the stripped skeleton where the first difference appears


def check(source: str, output: str) -> Verdict:
    """True only if `output` equals `source` once diacritics are removed from both."""
    if output is None:
        return Verdict(False, "empty output")
    a = strip_diacritics(source)
    b = strip_diacritics(output)
    if a == b:
        return Verdict(True)
    n = min(len(a), len(b))
    pos = next((i for i in range(n) if a[i] != b[i]), n)
    if len(b) > len(a) and pos >= len(a):
        return Verdict(False, "characters appended", pos)
    if len(b) < len(a) and pos >= len(b):
        return Verdict(False, "characters removed", pos)
    return Verdict(False, f"base text altered at position {pos}", pos)
