"""The three earcons (F-009, docs/DESIGN.md sound): generated, not recorded.

Soft sine tones with a second partial an octave up at low level, raised-cosine
fades (no clicks), peak well below full scale. Each is under 300 ms.
"""

from enum import StrEnum
from typing import Final

import numpy as np

from ev_core.interfaces.voice import Samples

RATE: Final = 24_000
PEAK: Final = 0.25
FADE_S: Final = 0.012


class Earcon(StrEnum):
    WAKE = "wake"
    DONE = "done"
    ERROR = "error"


def _tone(freq: float, seconds: float) -> Samples:
    t = np.arange(int(RATE * seconds), dtype=np.float32) / RATE
    wave = np.sin(2 * np.pi * freq * t) + 0.18 * np.sin(2 * np.pi * 2 * freq * t)
    # Gentle decay so each tone settles rather than stops.
    wave *= np.exp(-t * 6.0)
    fade = min(int(RATE * FADE_S), len(t) // 2)
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fade, dtype=np.float32))
    wave[:fade] *= ramp
    wave[-fade:] *= ramp[::-1]
    return wave.astype(np.float32)


def _gap(seconds: float) -> Samples:
    return np.zeros(int(RATE * seconds), dtype=np.float32)


def _normalized(parts: list[Samples]) -> Samples:
    wave = np.concatenate(parts)
    return (wave * (PEAK / float(np.max(np.abs(wave))))).astype(np.float32)


def render(earcon: Earcon, volume: float) -> Samples:
    """The earcon at ``volume`` (0..1) and ``RATE``."""
    match earcon:
        case Earcon.WAKE:
            # Two rising tones: "I'm listening".
            parts = [_tone(660.0, 0.055), _gap(0.01), _tone(880.0, 0.055)]
        case Earcon.DONE:
            # One falling tone: "got it".
            sweep = _tone(880.0, 0.07)
            parts = [sweep, _tone(660.0, 0.07)]
        case Earcon.ERROR:
            # Two low pulses.
            parts = [_tone(330.0, 0.08), _gap(0.04), _tone(330.0, 0.08)]
    return (_normalized(parts) * max(0.0, min(1.0, volume))).astype(np.float32)
