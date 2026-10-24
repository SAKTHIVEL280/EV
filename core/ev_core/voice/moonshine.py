"""Moonshine speech recognition and Kokoro speech through moonshine-voice
(docs/decisions.md 2026-10-24: one MIT runtime, no espeak-ng).

Both load from EV's models folder only; moonshine-voice's own downloader is
never used (EV downloads and verifies the files, F-010).
"""

import logging
import threading
from pathlib import Path
from typing import Any, Final

import numpy as np

from ev_core.interfaces.voice import (
    MIC_RATE,
    NOT_INSTALLED,
    LineHeard,
    Samples,
    SttEngine,
    SttSession,
    TtsEngine,
    VoiceError,
)

logger = logging.getLogger(__name__)

UPDATE_INTERVAL_S: Final = 0.25
"""How often words in progress are re-read (live captions)."""
LANGUAGE: Final = "en-us"

_ARCHES: Final = {
    "tiny": "TINY_STREAMING",
    "small": "SMALL_STREAMING",
    "medium": "MEDIUM_STREAMING",
}


def _arch_for(model_dir: Path) -> Any:
    from moonshine_voice.moonshine_api import ModelArch

    for size, arch in _ARCHES.items():
        if f"-{size}-" in model_dir.name:
            return ModelArch[arch]
    raise VoiceError("Speech recognition files are damaged.", f"unknown model folder {model_dir}")


class _Session(SttSession):
    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self._heard: list[LineHeard] = []
        stream.add_listener(self._on_event)
        stream.start()

    def _on_event(self, event: Any) -> None:
        from moonshine_voice.transcriber import LineCompleted, LineTextChanged

        if isinstance(event, LineTextChanged | LineCompleted) and event.line is not None:
            line = event.line
            self._heard.append(
                LineHeard(
                    int(line.line_id), str(line.text).strip(), isinstance(event, LineCompleted)
                )
            )

    def _take(self) -> list[LineHeard]:
        heard, self._heard = self._heard, []
        return heard

    def feed(self, samples: Samples) -> list[LineHeard]:
        self._stream.add_audio(samples.tolist(), MIC_RATE)
        return self._take()

    def finish(self) -> list[LineHeard]:
        self._stream.stop()
        heard = self._take()
        # Lines still open when audio stopped come back as complete.
        return [LineHeard(h.line_id, h.text, True) for h in heard]

    def close(self) -> None:
        self._stream.close()


class MoonshineStt(SttEngine):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded: tuple[Path, Any] | None = None

    def open(self, model_dir: Path) -> SttSession:
        with self._lock:
            if self._loaded is None or self._loaded[0] != model_dir:
                self._loaded = (model_dir, self._load(model_dir))
            transcriber = self._loaded[1]
        try:
            return _Session(transcriber.create_stream(update_interval=UPDATE_INTERVAL_S))
        except Exception as exc:
            raise VoiceError("Couldn't start voice. Details are in the log.", repr(exc)) from exc

    @staticmethod
    def _load(model_dir: Path) -> Any:
        if not model_dir.is_dir():
            raise VoiceError(NOT_INSTALLED, f"missing {model_dir}")
        from moonshine_voice import Transcriber

        try:
            transcriber = Transcriber(str(model_dir), _arch_for(model_dir), UPDATE_INTERVAL_S)
        except Exception as exc:
            raise VoiceError("Couldn't start voice. Details are in the log.", repr(exc)) from exc
        logger.info("speech recognition loaded", extra={"fields": {"model": model_dir.name}})
        return transcriber

    def unload(self) -> None:
        with self._lock:
            if self._loaded is not None:
                self._loaded[1].close()
                self._loaded = None
                logger.info("speech recognition unloaded")


class MoonshineTts(TtsEngine):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded: tuple[Path, str, Any] | None = None

    def synthesize(self, text: str, voice: str, speed: float, assets: Path) -> tuple[Samples, int]:
        with self._lock:
            if self._loaded is None or self._loaded[:2] != (assets, voice):
                self._unload_locked()
                self._loaded = (assets, voice, self._load(assets, voice))
            engine = self._loaded[2]
            try:
                samples, rate = engine.synthesize(text, speed=speed)
            except Exception as exc:
                raise VoiceError("Couldn't speak that. Details are in the log.", repr(exc)) from exc
        return np.asarray(samples, dtype=np.float32), int(rate)

    @staticmethod
    def _load(assets: Path, voice: str) -> Any:
        if not assets.is_dir():
            raise VoiceError(NOT_INSTALLED, f"missing {assets}")
        from moonshine_voice import TextToSpeech

        try:
            engine = (
                TextToSpeech()
                .language(LANGUAGE)
                .voice(f"kokoro_{voice}")
                .models_from(assets, download=False)
                .load()
            )
        except Exception as exc:
            raise VoiceError("Couldn't start voice. Details are in the log.", repr(exc)) from exc
        logger.info("speech loaded", extra={"fields": {"voice": voice}})
        return engine

    def _unload_locked(self) -> None:
        if self._loaded is not None:
            self._loaded[2].close()
            self._loaded = None
            logger.info("speech unloaded")

    def unload(self) -> None:
        with self._lock:
            self._unload_locked()
