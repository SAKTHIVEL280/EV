"""Barge-in with an echo guard (F-006).

EV has no echo cancellation, so while it speaks its own voice reaches the mic
through laptop speakers. Speech counts as the user's only when the mic level is
clearly above what the echo alone would give. The echo ratio (mic level /
output level) is learned while EV speaks and nobody else is talking; with
headphones it stays near zero, so any speech counts.
"""

from dataclasses import dataclass, field
from typing import Final

import numpy as np

from ev_core.interfaces.voice import Samples

FRAME: Final = 800
"""50 ms at 16 kHz."""
VOICE_FRAMES: Final = 3
"""Consecutive loud frames (150 ms) that make speech."""
MIN_LEVEL: Final = 0.01
"""Below this RMS nothing is speech, however quiet the room."""
NOISE_FACTOR: Final = 3.0
ECHO_FACTOR: Final = 2.5
START_RATIO: Final = 1.0
"""Assumed echo ratio before any is measured: laptop speakers next to the mic."""
LEARN: Final = 0.05


def rms(samples: Samples) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float32))))


@dataclass
class BargeDetector:
    """Feed mic audio with the output level at that moment; ``True`` = user speaks."""

    echo_factor: float = ECHO_FACTOR
    noise: float = MIN_LEVEL / NOISE_FACTOR
    ratio: float = START_RATIO
    _loud: int = 0
    _pending: Samples = field(default_factory=lambda: np.zeros(0, dtype=np.float32))

    def feed(self, samples: Samples, output_level: float) -> bool:
        self._pending = np.concatenate([self._pending, samples])
        speech = False
        while self._pending.size >= FRAME:
            frame, self._pending = self._pending[:FRAME], self._pending[FRAME:]
            speech = self._frame(rms(frame), output_level) or speech
        return speech

    def reset(self) -> None:
        self._loud = 0
        self._pending = np.zeros(0, dtype=np.float32)

    def _frame(self, level: float, output_level: float) -> bool:
        threshold = max(MIN_LEVEL, self.noise * NOISE_FACTOR)
        if output_level > 0:
            threshold = max(threshold, self.echo_factor * self.ratio * output_level)
        if level > threshold:
            self._loud += 1
            return self._loud >= VOICE_FRAMES
        self._loud = 0
        if output_level > 0:
            # Quiet enough to be echo only: learn how loud the echo is.
            self.ratio += LEARN * (level / output_level - self.ratio)
        else:
            self.noise += LEARN * (level - self.noise)
        return False
