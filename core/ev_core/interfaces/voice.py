"""Voice interfaces (CLAUDE.md §5.3, docs/FEATURES.md F-008).

Engines are blocking and run in worker threads; the voice module drives them
from asyncio. Audio is mono float32 in -1..1. The microphone side is always
16 kHz; speech output carries its own sample rate.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt

from ev_core.errors import EvError

Samples = npt.NDArray[np.float32]
MIC_RATE: Final = 16_000
NOT_INSTALLED: Final = "Voice isn't installed. Download it in Settings → Voice."


class VoiceError(EvError):
    """Voice can't run: missing files, no device, or an engine failure."""


@dataclass(frozen=True, slots=True)
class LineHeard:
    """Recognized words of one line (a stretch of speech between pauses)."""

    line_id: int
    text: str
    complete: bool


class SttSession(ABC):
    """One listening session: audio in, lines out."""

    @abstractmethod
    def feed(self, samples: Samples) -> list[LineHeard]:
        """Add 16 kHz audio; returns lines whose text changed or completed."""

    @abstractmethod
    def finish(self) -> list[LineHeard]:
        """No more audio: every line is completed and returned."""

    @abstractmethod
    def close(self) -> None: ...


class SttEngine(ABC):
    @abstractmethod
    def open(self, model_dir: Path) -> SttSession:
        """Start a session, loading the model from ``model_dir`` if needed."""

    @abstractmethod
    def unload(self) -> None: ...


class TtsEngine(ABC):
    @abstractmethod
    def synthesize(self, text: str, voice: str, speed: float, assets: Path) -> tuple[Samples, int]:
        """Speech for ``text``: samples and their sample rate. Loads on first use."""

    @abstractmethod
    def unload(self) -> None: ...


class AudioInput(ABC):
    def prepare(self) -> None:  # noqa: B027 -- optional hook, nothing to do by default
        """Slow one-time setup, run in the background at startup so the first
        listen is quick (PortAudio's first initialisation takes ~1.6 s)."""

    @abstractmethod
    def start(self, on_audio: Callable[[Samples], None]) -> None:
        """Open the microphone; ``on_audio`` gets 16 kHz chunks on an audio thread."""

    @abstractmethod
    def stop(self) -> None: ...


class AudioOutput(ABC):
    @abstractmethod
    def play(self, samples: Samples, rate: int) -> None:
        """Queue audio after anything already queued. Returns at once."""

    @abstractmethod
    def stop(self) -> None:
        """Silence now and drop everything queued."""

    @abstractmethod
    def busy(self) -> bool:
        """Audio is playing or queued."""

    @abstractmethod
    def level(self) -> float:
        """RMS of what played in the last ~100 ms (0 when silent): the echo
        guard compares the microphone against it (F-006)."""

    @abstractmethod
    def close(self) -> None: ...
