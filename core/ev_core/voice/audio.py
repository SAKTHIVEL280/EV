"""Microphone and speaker through sounddevice (PortAudio).

Devices run at their own default rate (WASAPI shared mode and PipeWire
refuse 16 kHz on many PCs); audio is resampled here: the mic down to 16 kHz,
speech up to the device rate. The output stream opens on demand and closes
after a few idle seconds, so the audio device isn't held while EV is quiet.
"""

import collections
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Final

import numpy as np

from ev_core.interfaces.voice import MIC_RATE, AudioInput, AudioOutput, Samples, VoiceError
from ev_core.voice.barge import rms

logger = logging.getLogger(__name__)

BLOCK_S: Final = 0.05
OUTPUT_IDLE_CLOSE_S: Final = 4.0
LEVEL_HOLD_S: Final = 0.15

NO_MIC: Final = "No microphone found."
MIC_BLOCKED: Final = "EV can't use the microphone. Check Windows Settings → Privacy → Microphone."
NO_SPEAKER: Final = "No speaker or headphones found."


def resample(samples: Samples, src: int, dst: int) -> Samples:
    """Linear resampling; for downsampling a moving average first stops aliasing."""
    if src == dst or samples.size == 0:
        return samples.astype(np.float32, copy=False)
    if src > dst:
        width = round(src / dst)
        if width > 1:
            kernel = np.full(width, 1.0 / width, dtype=np.float32)
            samples = np.convolve(samples, kernel, mode="same").astype(np.float32)
    count = round(samples.size * dst / src)
    positions = np.linspace(0, samples.size - 1, count, dtype=np.float64)
    return np.interp(positions, np.arange(samples.size), samples).astype(np.float32)


def _sd() -> Any:
    try:
        import sounddevice
    except OSError as exc:  # PortAudio library missing (Linux without libportaudio)
        raise VoiceError("Couldn't start voice. Details are in the log.", repr(exc)) from exc
    return sounddevice


class SoundDeviceInput(AudioInput):
    def __init__(self) -> None:
        self._stream: Any = None

    def start(self, on_audio: Callable[[Samples], None]) -> None:
        sd = _sd()
        try:
            device = sd.query_devices(kind="input")
        except (sd.PortAudioError, ValueError) as exc:
            raise VoiceError(NO_MIC, repr(exc)) from exc
        rate = int(device["default_samplerate"])

        def callback(indata: Any, _frames: int, _time: Any, status: Any) -> None:
            if status:
                logger.debug("mic status", extra={"fields": {"status": str(status)}})
            on_audio(resample(np.asarray(indata[:, 0], dtype=np.float32), rate, MIC_RATE))

        try:
            self._stream = sd.InputStream(
                samplerate=rate,
                channels=1,
                dtype="float32",
                blocksize=int(rate * BLOCK_S),
                callback=callback,
            )
            self._stream.start()
        except sd.PortAudioError as exc:
            self._stream = None
            raise VoiceError(MIC_BLOCKED, repr(exc)) from exc
        logger.info("microphone open", extra={"fields": {"device": device["name"], "rate": rate}})

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
            logger.info("microphone closed")


class SoundDeviceOutput(AudioOutput):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: collections.deque[Samples] = collections.deque()
        self._current: Samples = np.zeros(0, dtype=np.float32)
        self._stream: Any = None
        self._rate = 0
        self._level = 0.0
        self._level_at = 0.0
        self._idle_since = time.monotonic()
        self._closer: threading.Timer | None = None

    def _ensure_stream(self) -> int:
        if self._stream is not None:
            return self._rate
        sd = _sd()
        try:
            device = sd.query_devices(kind="output")
            rate = int(device["default_samplerate"])
            stream = sd.OutputStream(
                samplerate=rate,
                channels=1,
                dtype="float32",
                blocksize=int(rate * 0.02),
                latency="low",
                callback=self._callback,
            )
            stream.start()
        except (sd.PortAudioError, ValueError) as exc:
            raise VoiceError(NO_SPEAKER, repr(exc)) from exc
        self._stream, self._rate = stream, rate
        return rate

    def _callback(self, outdata: Any, frames: int, _time: Any, _status: Any) -> None:
        out = np.zeros(frames, dtype=np.float32)
        filled = 0
        with self._lock:
            while filled < frames:
                if self._current.size == 0:
                    if not self._queue:
                        break
                    self._current = self._queue.popleft()
                take = min(frames - filled, self._current.size)
                out[filled : filled + take] = self._current[:take]
                self._current = self._current[take:]
                filled += take
            if filled:
                self._level = rms(out[:filled])
                self._level_at = time.monotonic()
                self._idle_since = self._level_at
        outdata[:, 0] = out

    def play(self, samples: Samples, rate: int) -> None:
        with self._lock:
            device_rate = self._ensure_stream()
            self._queue.append(resample(samples, rate, device_rate))
            self._idle_since = time.monotonic()
        self._schedule_close()

    def stop(self) -> None:
        with self._lock:
            self._queue.clear()
            self._current = np.zeros(0, dtype=np.float32)
            self._level = 0.0

    def busy(self) -> bool:
        with self._lock:
            return bool(self._queue) or self._current.size > 0

    def level(self) -> float:
        with self._lock:
            if time.monotonic() - self._level_at > LEVEL_HOLD_S:
                return 0.0
            return self._level

    def _schedule_close(self) -> None:
        if self._closer is not None:
            self._closer.cancel()
        self._closer = threading.Timer(OUTPUT_IDLE_CLOSE_S, self._close_if_idle)
        self._closer.daemon = True
        self._closer.start()

    def _close_if_idle(self) -> None:
        with self._lock:
            idle = (
                not self._queue
                and self._current.size == 0
                and time.monotonic() - self._idle_since >= OUTPUT_IDLE_CLOSE_S
            )
        if not idle:
            self._schedule_close()
            return
        self.close()

    def close(self) -> None:
        if self._closer is not None:
            self._closer.cancel()
            self._closer = None
        with self._lock:
            stream, self._stream = self._stream, None
            self._queue.clear()
            self._current = np.zeros(0, dtype=np.float32)
        if stream is not None:
            stream.stop()
            stream.close()
