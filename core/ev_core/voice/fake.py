"""Fake voice engines and devices for tests and Linux development without audio."""

from collections.abc import Callable
from pathlib import Path

import numpy as np

from ev_core.interfaces.voice import (
    AudioInput,
    AudioOutput,
    LineHeard,
    Samples,
    SttEngine,
    SttSession,
    TtsEngine,
    VoiceError,
)

FAKE_TTS_RATE = 24_000


class FakeMic(AudioInput):
    def __init__(self, error: VoiceError | None = None) -> None:
        self.error = error
        self.on_audio: Callable[[Samples], None] | None = None
        self.starts = 0

    def start(self, on_audio: Callable[[Samples], None]) -> None:
        if self.error is not None:
            raise self.error
        self.starts += 1
        self.on_audio = on_audio

    def stop(self) -> None:
        self.on_audio = None

    @property
    def open(self) -> bool:
        return self.on_audio is not None

    def push(self, samples: Samples) -> None:
        if self.on_audio is not None:
            self.on_audio(samples)


class FakeSession(SttSession):
    def __init__(self, engine: "FakeStt") -> None:
        self._engine = engine
        self.fed = 0
        self.closed = False

    def feed(self, samples: Samples) -> list[LineHeard]:
        self.fed += samples.size
        if self._engine.script:
            return self._engine.script.pop(0)
        return []

    def finish(self) -> list[LineHeard]:
        return [LineHeard(h.line_id, h.text, True) for h in self._engine.on_finish]

    def close(self) -> None:
        self.closed = True


class FakeStt(SttEngine):
    """Each ``feed`` returns the next scripted list of lines (or nothing)."""

    def __init__(self) -> None:
        self.script: list[list[LineHeard]] = []
        self.on_finish: list[LineHeard] = []
        self.sessions: list[FakeSession] = []
        self.loaded = False

    def open(self, model_dir: Path) -> SttSession:
        self.loaded = True
        session = FakeSession(self)
        self.sessions.append(session)
        return session

    def unload(self) -> None:
        self.loaded = False


class FakeTts(TtsEngine):
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.loaded = False

    def synthesize(self, text: str, voice: str, speed: float, assets: Path) -> tuple[Samples, int]:
        self.loaded = True
        self.spoken.append(text)
        return np.full(100 * len(text), 0.1, dtype=np.float32), FAKE_TTS_RATE

    def unload(self) -> None:
        self.loaded = False


class FakeSpeaker(AudioOutput):
    """Plays nothing; audio stays "playing" until ``finish()``."""

    def __init__(self) -> None:
        self.played: list[tuple[Samples, int]] = []
        self.stops = 0
        self.playing = False
        self.output_level = 0.0

    def play(self, samples: Samples, rate: int) -> None:
        self.played.append((samples, rate))
        self.playing = True

    def stop(self) -> None:
        self.stops += 1
        self.playing = False

    def finish(self) -> None:
        self.playing = False

    def busy(self) -> bool:
        return self.playing

    def level(self) -> float:
        return self.output_level if self.playing else 0.0

    def close(self) -> None:
        self.playing = False
