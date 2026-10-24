"""Turning streamed reply text into sentences to speak (F-008).

The reply arrives in small deltas. ``SentenceSplitter`` hands out each
sentence as soon as it is complete, so speech starts on the first one. Text
meant for the eye (code blocks, markdown marks, links) is cleaned or skipped.
"""

import re
from typing import Final

_ABBREVIATIONS: Final = frozenset(
    {"mr", "mrs", "ms", "dr", "prof", "st", "vs", "etc", "e.g", "i.e", "approx", "jr", "sr"}
)
# A sentence ends at . ! ? (plus closing quotes/brackets) followed by space, or at a newline.
_BOUNDARY: Final = re.compile(r"[.!?]+[\"')\]]*(?=\s)|\n+")
_CODE_BLOCK: Final = re.compile(r"```.*?(```|$)", re.DOTALL)
_LINK: Final = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_URL: Final = re.compile(r"https?://\S+")
_MARKS: Final = re.compile(r"[*_`#>|]+")
_BULLET: Final = re.compile(r"^\s*(?:[-•]|\d+[.)])\s+", re.MULTILINE)
_SPACES: Final = re.compile(r"\s+")

MIN_CHARS: Final = 2
"""Shorter pieces (a lone "1." of a list) are joined to the next sentence."""


def speakable(text: str) -> str:
    """Text as it should be said: no markdown, no code, no raw URLs."""
    text = _CODE_BLOCK.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("the link", text)
    text = _BULLET.sub("", text)
    text = _MARKS.sub("", text)
    return _SPACES.sub(" ", text).strip()


class SentenceSplitter:
    def __init__(self) -> None:
        self._buffer = ""

    def add(self, delta: str) -> list[str]:
        """Add streamed text; returns the sentences it completed."""
        self._buffer += delta
        out: list[str] = []
        start = 0
        for match in _BOUNDARY.finditer(self._buffer):
            end = match.end()
            piece = self._buffer[start:end]
            if (
                self._inside_code(self._buffer[:end])
                or self._abbreviation(piece)
                or self._trailing_off(match.group(), self._buffer[end:])
            ):
                continue
            spoken = speakable(piece)
            # A lone list number ("1.") joins the sentence after it.
            if len(spoken) < MIN_CHARS or not any(c.isalpha() for c in spoken):
                continue
            out.append(spoken)
            start = end
        self._buffer = self._buffer[start:]
        return out

    def flush(self) -> list[str]:
        """The reply ended: whatever is left is the last sentence."""
        rest = speakable(self._buffer)
        self._buffer = ""
        return [rest] if rest else []

    @staticmethod
    def _inside_code(text: str) -> bool:
        return text.count("```") % 2 == 1

    @staticmethod
    def _trailing_off(mark: str, rest: str) -> bool:
        """An ellipsis before a lowercase word ("Wait... what") doesn't end the
        sentence; with nothing after it yet, wait and see."""
        if not mark.startswith(".."):
            return False
        following = rest.lstrip()
        return not following or following[0].islower()

    @staticmethod
    def _abbreviation(piece: str) -> bool:
        words = piece.strip().split()
        if not words or not piece.rstrip().endswith("."):
            return False
        last = words[-1].rstrip(".").lower()
        # "Dr." or a single initial like "J." doesn't end a sentence.
        return last in _ABBREVIATIONS or (len(last) == 1 and last.isalpha())
