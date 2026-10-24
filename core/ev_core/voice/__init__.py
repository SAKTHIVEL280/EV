"""The `voice` module: listening, spoken replies, barge-in and earcons
(docs/FEATURES.md F-005, F-006, F-008, F-009).

Flow: the app asks to listen (hotkey, mic button, push-to-talk). Mic audio is
fed to the recognizer; live words go to the app (VoiceHeard). When the user
stops talking (a completed line plus a short grace period) the final words go
to the app, which sends them as a chat message marked spoken. Replies to
spoken turns are spoken sentence by sentence.

While a spoken reply is on its way the mic stays open but only *watches*: an
energy detector with an echo guard (voice/barge.py). Speech stops EV at once
(barge-in) and opens a new listening session, fed the last moments of audio
so the first words aren't lost. When the reply ends, EV listens for a
follow-up for a few seconds.

Engines are blocking: the recognizer and the synthesizer each run on their own
single worker thread, so calls stay ordered and never block the event loop.
"""

import asyncio
import contextlib
import logging
import math
import re
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Final

import numpy as np

from ev_core.bus import EventBus
from ev_core.config import ConfigChanged, SpeakReplies, VoiceSection
from ev_core.interfaces.events import (
    ChatDelta,
    ChatDone,
    ChatFailed,
    ChatRequested,
    ChatToolChanged,
    FocusModeChanged,
    VoiceHeard,
    VoiceLevel,
    VoiceStartRequested,
    VoiceStateChanged,
    VoiceStopRequested,
)
from ev_core.interfaces.voice import (
    MIC_RATE,
    NOT_INSTALLED,
    AudioInput,
    AudioOutput,
    LineHeard,
    Samples,
    SttEngine,
    SttSession,
    TtsEngine,
    VoiceError,
)
from ev_core.modules import Module, ModuleContext
from ev_core.voice.audio import MIC_BLOCKED, NO_MIC, NO_SPEAKER
from ev_core.voice.barge import BargeDetector, rms
from ev_core.voice.earcons import RATE as EARCON_RATE
from ev_core.voice.earcons import Earcon, render
from ev_core.voice.text import SentenceSplitter

logger = logging.getLogger(__name__)

ACKNOWLEDGEMENT: Final = "Okay, on it."
NO_SPEECH: Final = "Didn't hear anything."
FAILED: Final = "Voice stopped working. Details are in the log."
VOICE_OFF: Final = "Voice is off. Turn it on in Settings → Voice."

RECOGNIZER_FOLDERS: Final = {
    "small": "moonshine-small-streaming-en",
    "tiny": "moonshine-tiny-streaming-en",
}
SPEECH_FOLDER: Final = "kokoro"
"""Holds ``en_us/`` (G2P) and ``kokoro/`` (model and voices), as moonshine-voice expects."""

# Recognizers sometimes "hear" these in noise; alone they are never a request.
_FILLERS: Final = frozenset({"you", "uh", "um", "hmm", "mm", "the", "a", "so", "oh", "ah", "huh"})
_WORDS: Final = re.compile(r"[a-z']+")


def voice_folder(models: Path) -> Path:
    return models / "voice"


def level_of(samples: Samples) -> float:
    """Mic level for the island: -60..-10 dBFS mapped to 0..1."""
    value = rms(samples)
    if value <= 0:
        return 0.0
    return max(0.0, min(1.0, (20 * math.log10(value) + 60) / 50))


def worth_sending(text: str) -> bool:
    words = _WORDS.findall(text.lower())
    return bool(words) and not all(w in _FILLERS for w in words)


@dataclass(frozen=True, slots=True)
class Timings:
    end_grace_s: float = 0.7
    """After a line completes, wait this long for another before sending (natural pauses)."""
    no_speech_s: float = 8.0
    follow_up_s: float = 5.0
    tick_s: float = 0.05
    level_every_s: float = 1 / 15
    barge_buffer_s: float = 0.6
    """Mic audio kept while watching, so a barge-in's first words reach the recognizer."""
    idle_check_s: float = 30.0


class MicMode(StrEnum):
    CLOSED = "closed"
    LISTENING = "listening"
    WATCHING = "watching"


@dataclass
class _Listening:
    session: SttSession
    follow_up: bool
    opened_at: float
    lines: dict[int, LineHeard] = field(default_factory=dict)
    last_complete_at: float | None = None
    shown: str = ""

    def text(self) -> str:
        return " ".join(line.text for line in self.lines.values() if line.text).strip()

    def heard_words(self) -> bool:
        return any(line.text for line in self.lines.values())

    def all_complete(self) -> bool:
        return bool(self.lines) and all(line.complete for line in self.lines.values())


@dataclass
class _Reply:
    turn_id: str
    received_at: float
    splitter: SentenceSplitter = field(default_factory=SentenceSplitter)
    said_anything: bool = False
    finished: bool = False
    """The chat turn ended; nothing more will be queued."""
    first_audio_ms: int | None = None


class VoiceModule(Module):
    name = "voice"

    def __init__(
        self,
        settings: VoiceSection,
        models_dir: Callable[[], Path],
        idle_unload_minutes: Callable[[], int],
        *,
        stt: SttEngine,
        tts: TtsEngine,
        mic: AudioInput,
        speaker: AudioOutput,
        quiet: Callable[[], bool] = lambda: False,
        timings: Timings | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._models_dir = models_dir
        self._idle_minutes = idle_unload_minutes
        self._stt = stt
        self._tts = tts
        self._mic = mic
        self._speaker = speaker
        self._quiet = quiet
        self._t = timings or Timings()
        self._clock = clock
        self._bus: EventBus | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stt_pool = ThreadPoolExecutor(1, thread_name_prefix="ev-stt")
        self._tts_pool = ThreadPoolExecutor(1, thread_name_prefix="ev-tts")

        self._mode = MicMode.CLOSED
        self._audio: asyncio.Queue[Samples] = asyncio.Queue()
        self._listening: _Listening | None = None
        self._barge = BargeDetector()
        self._buffer: deque[Samples] = deque()
        self._level_at = 0.0
        self._follow_up_allowed = True
        self._watch_since = 0.0

        self._reply: _Reply | None = None
        self._sentences: asyncio.Queue[tuple[_Reply, str]] = asyncio.Queue()
        self._synthesizing = False
        self._focus_on = False
        self._last_state: tuple[bool, bool] = (False, False)
        self._used_at = clock()
        self._loaded = {"stt": False, "tts": False}

        self._ticker: asyncio.Task[None] | None = None
        self._speaker_task: asyncio.Task[None] | None = None
        self._idle_task: asyncio.Task[None] | None = None
        self._prepare_task: asyncio.Task[None] | None = None

    # --- module lifecycle
    async def start(self, ctx: ModuleContext) -> None:
        self._bus = ctx.bus
        self._loop = asyncio.get_running_loop()
        ctx.bus.subscribe(VoiceStartRequested, self._on_start)
        ctx.bus.subscribe(VoiceStopRequested, self._on_stop)
        ctx.bus.subscribe(ChatRequested, self._on_chat)
        ctx.bus.subscribe(ChatDelta, self._on_delta)
        ctx.bus.subscribe(ChatToolChanged, self._on_tool)
        ctx.bus.subscribe(ChatDone, self._on_done)
        ctx.bus.subscribe(ChatFailed, self._on_failed)
        ctx.bus.subscribe(FocusModeChanged, self._on_focus)
        ctx.bus.subscribe(ConfigChanged, self._on_config)
        self._speaker_task = asyncio.create_task(self._speak_loop())
        self._idle_task = asyncio.create_task(self._idle_loop())
        self._prepare_task = asyncio.create_task(self._prepare())

    async def stop(self) -> None:
        await self._close_mic()
        self._stop_speech()
        for task in (self._ticker, self._speaker_task, self._idle_task, self._prepare_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._speaker.close()
        await self._unload()
        self._stt_pool.shutdown(wait=False)
        self._tts_pool.shutdown(wait=False)

    async def _prepare(self) -> None:
        if not self._settings.enabled:
            return
        started = self._clock()
        try:
            await asyncio.to_thread(self._mic.prepare)
        except VoiceError as exc:
            # Reported when the user tries to listen; nothing to show now.
            logger.warning("audio not ready", extra={"fields": {"detail": exc.detail}})
            return
        logger.info(
            "audio ready", extra={"fields": {"ms": round((self._clock() - started) * 1000)}}
        )

    # --- paths
    def _recognizer_dir(self) -> Path:
        folder = RECOGNIZER_FOLDERS[self._settings.recognizer.value]
        return voice_folder(self._models_dir()) / folder

    def _speech_dir(self) -> Path:
        return voice_folder(self._models_dir()) / SPEECH_FOLDER

    # --- publishing
    def _publish_state(self, message: str | None = None, code: str | None = None) -> None:
        state = (self._mode is not MicMode.CLOSED, self._is_speaking())
        if message is None and state == self._last_state:
            return
        self._last_state = state
        if self._bus is not None:
            self._bus.publish(VoiceStateChanged(state[0], state[1], message, code))

    def _is_speaking(self) -> bool:
        return self._reply is not None and (
            self._speaker.busy() or self._synthesizing or not self._sentences.empty()
        )

    def _earcon(self, earcon: Earcon) -> None:
        volume = self._settings.earcons_volume
        if volume <= 0 or self._focus_on or self._quiet():
            return
        try:
            self._speaker.play(render(earcon, volume / 100), EARCON_RATE)
        except VoiceError as exc:
            logger.warning("earcon not played", extra={"fields": {"detail": exc.detail}})

    # --- worker threads
    async def _in_stt[T](self, fn: Callable[[], T]) -> T:
        self._used_at = self._clock()
        return await asyncio.get_running_loop().run_in_executor(self._stt_pool, fn)

    async def _in_tts[T](self, fn: Callable[[], T]) -> T:
        self._used_at = self._clock()
        return await asyncio.get_running_loop().run_in_executor(self._tts_pool, fn)

    # --- requests from the app
    async def _on_start(self, event: VoiceStartRequested) -> None:
        if not self._settings.enabled:
            self._publish_state(VOICE_OFF, "off")
            return
        self._follow_up_allowed = True
        if self._is_speaking():
            # The hotkey while EV speaks: stop and listen (barge-in by key, F-006).
            self._stop_speech()
        if self._mode is MicMode.LISTENING:
            return
        asked = self._clock()
        await self._listen(follow_up=False)
        if self._listening is not None:
            logger.info(
                "voice listening",
                extra={
                    "fields": {
                        "source": event.source,
                        "ms": round((self._clock() - asked) * 1000),
                    }
                },
            )

    async def _on_stop(self, event: VoiceStopRequested) -> None:
        match event.reason:
            case "typing":
                await self._close_mic()
                self._stop_speech()
            case "closed":
                self._follow_up_allowed = False
                await self._close_mic()
            case "send":
                await self._send_now()
            case "silence":
                self._stop_speech()
                await self._close_mic()
            case _:
                await self._close_mic()
        self._publish_state()

    # --- listening
    async def _listen(self, *, follow_up: bool, prime: list[Samples] | None = None) -> None:
        folder = self._recognizer_dir()
        if not folder.is_dir():
            await self._close_mic()
            self._earcon(Earcon.ERROR)
            self._publish_state(NOT_INSTALLED, "not_installed")
            return
        try:
            if self._prepare_task is not None:
                await self._prepare_task  # the first listen right after startup
            session = await self._in_stt(lambda: self._stt.open(folder))
            self._loaded["stt"] = True
            if self._mode is MicMode.CLOSED:
                await asyncio.to_thread(self._mic.start, self._on_audio)
        except VoiceError as exc:
            logger.warning("voice failed", extra={"fields": {"detail": exc.detail}})
            await self._close_mic()
            self._earcon(Earcon.ERROR)
            self._publish_state(exc.user_message, _code_for(exc.user_message))
            return
        self._close_session()
        self._listening = _Listening(session, follow_up, self._clock())
        self._mode = MicMode.LISTENING
        if not follow_up:
            self._earcon(Earcon.WAKE)
        self._publish_state()
        self._ensure_ticker()
        for chunk in prime or []:
            await self._feed(chunk)

    def _on_audio(self, samples: Samples) -> None:
        # Audio thread: hand the chunk to the event loop.
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._audio.put_nowait, samples)

    async def _feed(self, samples: Samples) -> None:
        listening = self._listening
        if listening is None:
            return
        heard = await self._in_stt(lambda: listening.session.feed(samples))
        self._take(listening, heard)

    def _take(self, listening: _Listening, heard: list[LineHeard]) -> None:
        now = self._clock()
        for line in heard:
            listening.lines[line.line_id] = line
            if line.complete:
                listening.last_complete_at = now
        text = listening.text()
        if text != listening.shown and self._bus is not None:
            listening.shown = text
            self._bus.publish(VoiceHeard(text, final=False))

    async def _on_chunk(self, samples: Samples) -> None:
        now = self._clock()
        if self._bus is not None and now - self._level_at >= self._t.level_every_s:
            self._level_at = now
            self._bus.publish(VoiceLevel(round(level_of(samples), 3)))
        if self._mode is MicMode.WATCHING:
            self._buffer.append(samples)
            while sum(c.size for c in self._buffer) > self._t.barge_buffer_s * MIC_RATE:
                self._buffer.popleft()
            if self._barge.feed(samples, self._speaker.level()):
                await self._barge_in()
            return
        await self._feed(samples)

    async def _barge_in(self) -> None:
        detected = self._clock()
        was_speaking = self._reply is not None and self._speaker.busy()
        if was_speaking:
            # Talking over EV stops it at once (F-006). Before EV speaks, the
            # reply is kept unless real words follow (see _speak_loop).
            self._stop_speech()
        logger.info(
            "voice barge-in",
            extra={
                "fields": {
                    "speaking": was_speaking,
                    "stop_ms": round((self._clock() - detected) * 1000),
                }
            },
        )
        prime = list(self._buffer)
        self._buffer.clear()
        self._barge.reset()
        await self._listen(follow_up=True, prime=prime)

    async def _send_now(self) -> None:
        listening = self._listening
        if listening is None:
            return
        try:
            heard = await self._in_stt(listening.session.finish)
        except VoiceError as exc:
            logger.warning("voice failed", extra={"fields": {"detail": exc.detail}})
            heard = []
        if self._listening is not listening:
            return  # the ticker already sent it
        self._take(listening, heard)
        await self._finish_utterance(listening)

    async def _finish_utterance(self, listening: _Listening) -> None:
        text = listening.text()
        self._close_session()
        if not worth_sending(text):
            await self._close_mic()
            self._publish_state()
            return
        self._earcon(Earcon.DONE)
        if self._bus is not None:
            self._bus.publish(VoiceHeard(text, final=True))
        if self._settings.speak_replies is SpeakReplies.NEVER:
            await self._close_mic()
        else:
            self._watch()
        self._publish_state()

    def _watch(self) -> None:
        self._mode = MicMode.WATCHING
        self._watch_since = self._clock()
        self._buffer.clear()
        self._barge.reset()
        self._ensure_ticker()

    def _close_session(self) -> None:
        listening, self._listening = self._listening, None
        if listening is not None:
            # On the recognizer's thread, after any feed still in flight.
            self._stt_pool.submit(listening.session.close)

    async def _close_mic(self) -> None:
        self._close_session()
        if self._mode is not MicMode.CLOSED:
            self._mode = MicMode.CLOSED
            await asyncio.to_thread(self._mic.stop)
        while not self._audio.empty():
            self._audio.get_nowait()
        self._buffer.clear()

    # --- the ticker: endpoints, timeouts and the end of speech
    def _ensure_ticker(self) -> None:
        if self._ticker is None or self._ticker.done():
            self._ticker = asyncio.create_task(self._tick_loop())

    def _active(self) -> bool:
        return self._mode is not MicMode.CLOSED or self._reply is not None

    async def _tick_loop(self) -> None:
        while self._active():
            try:
                samples = await asyncio.wait_for(self._audio.get(), self._t.tick_s)
            except TimeoutError:
                samples = None
            try:
                if samples is not None and self._mode is not MicMode.CLOSED:
                    await self._on_chunk(samples)
                await self._check()
            except VoiceError as exc:
                logger.warning("voice failed", extra={"fields": {"detail": exc.detail}})
                await self._close_mic()
                self._earcon(Earcon.ERROR)
                self._publish_state(exc.user_message, "failed")
            except Exception:
                # One bad step must not stop voice for the rest of the session.
                logger.exception("voice step failed")
                await self._close_mic()
                self._publish_state(FAILED, "failed")
        self._publish_state()

    async def _check(self) -> None:
        now = self._clock()
        listening = self._listening
        if self._mode is MicMode.LISTENING and listening is not None:
            done_at = listening.last_complete_at
            if (
                done_at is not None
                and listening.all_complete()
                and now - done_at >= self._t.end_grace_s
            ):
                await self._finish_utterance(listening)
            elif not listening.heard_words():
                limit = self._t.follow_up_s if listening.follow_up else self._t.no_speech_s
                if now - listening.opened_at >= limit:
                    await self._close_mic()
                    self._publish_state(None if listening.follow_up else NO_SPEECH, "no_speech")
        if (
            self._mode is MicMode.WATCHING
            and self._reply is None
            and now - self._watch_since >= self._t.no_speech_s
        ):
            # The request never became a spoken turn: stop watching.
            await self._close_mic()
        reply = self._reply
        if (
            reply is not None
            and reply.finished
            and self._sentences.empty()
            and not self._synthesizing
            and not self._speaker.busy()
        ):
            await self._reply_spoken(reply)
        self._publish_state()

    async def _reply_spoken(self, reply: _Reply) -> None:
        self._reply = None
        logger.info(
            "voice reply spoken",
            extra={"fields": {"first_audio_ms": reply.first_audio_ms, "turn": reply.turn_id}},
        )
        if self._mode is MicMode.WATCHING:
            if self._settings.follow_up and self._follow_up_allowed:
                await self._listen(follow_up=True)
            else:
                await self._close_mic()

    # --- spoken replies
    def _speaks(self, spoken: bool) -> bool:
        match self._settings.speak_replies:
            case SpeakReplies.ALWAYS:
                return self._settings.enabled
            case SpeakReplies.NEVER:
                return False
            case SpeakReplies.WHEN_SPOKEN:
                return self._settings.enabled and spoken

    async def _on_chat(self, event: ChatRequested) -> None:
        self._stop_speech()
        if not self._speaks(event.spoken):
            if self._mode is MicMode.WATCHING:
                await self._close_mic()
            self._publish_state()
            return
        if not self._speech_dir().is_dir():
            await self._close_mic()
            self._publish_state(NOT_INSTALLED, "not_installed")
            return
        self._reply = _Reply(event.turn_id, self._clock())
        self._ensure_ticker()

    def _current(self, turn_id: str) -> _Reply | None:
        reply = self._reply
        return reply if reply is not None and reply.turn_id == turn_id else None

    def _say(self, reply: _Reply, text: str) -> None:
        reply.said_anything = True
        self._sentences.put_nowait((reply, text))

    async def _on_delta(self, event: ChatDelta) -> None:
        if (reply := self._current(event.turn_id)) is not None:
            for sentence in reply.splitter.add(event.text):
                self._say(reply, sentence)

    async def _on_tool(self, event: ChatToolChanged) -> None:
        reply = self._current(event.turn_id)
        if reply is not None and event.state == "running" and not reply.said_anything:
            # Let the user know EV heard before longer work (decisions.md "Voice mode").
            self._say(reply, ACKNOWLEDGEMENT)

    async def _on_done(self, event: ChatDone) -> None:
        if (reply := self._current(event.turn_id)) is not None:
            for sentence in reply.splitter.flush():
                self._say(reply, sentence)
            reply.finished = True

    async def _on_failed(self, event: ChatFailed) -> None:
        if (reply := self._current(event.turn_id)) is not None:
            self._earcon(Earcon.ERROR)
            self._say(reply, event.message)
            reply.finished = True

    async def _speak_loop(self) -> None:
        while True:
            reply, text = await self._sentences.get()
            if reply is not self._reply:
                continue
            settings = self._settings
            folder = self._speech_dir()
            self._synthesizing = True
            try:
                samples, rate = await self._in_tts(
                    partial(
                        self._tts.synthesize,
                        text,
                        settings.voice.value,
                        settings.speed / 100,
                        folder,
                    )
                )
                self._loaded["tts"] = True
                if reply is not self._reply:
                    continue
                listening = self._listening
                if self._mode is MicMode.LISTENING and listening is not None:
                    if listening.heard_words():
                        # The user is talking: their words become the next request.
                        self._stop_speech()
                        continue
                    # Nothing said yet: back to watching, so EV doesn't hear itself.
                    self._close_session()
                    self._watch()
                self._speaker.play((samples * (settings.volume / 100)).astype(np.float32), rate)
            except VoiceError as exc:
                logger.warning("speech failed", extra={"fields": {"detail": exc.detail}})
                self._reply = None
                self._publish_state(exc.user_message, _code_for(exc.user_message))
                continue
            except Exception:
                # A bad sentence must not stop speech for the rest of the session.
                logger.exception("speech step failed")
                self._reply = None
                self._publish_state(FAILED, "failed")
                continue
            finally:
                self._synthesizing = False
            if reply.first_audio_ms is None:
                reply.first_audio_ms = round((self._clock() - reply.received_at) * 1000)
            self._publish_state()

    def _stop_speech(self) -> None:
        # Only a reply is cut; an earcon that is playing finishes.
        had_reply, self._reply = self._reply is not None, None
        while not self._sentences.empty():
            self._sentences.get_nowait()
        if had_reply and self._speaker.busy():
            self._speaker.stop()
        self._publish_state()

    # --- other events
    async def _on_focus(self, event: FocusModeChanged) -> None:
        self._focus_on = event.on

    async def _on_config(self, event: ConfigChanged) -> None:
        if "voice" not in event.sections:
            return
        old, self._settings = self._settings, event.config.voice
        if not self._settings.enabled:
            await self._close_mic()
            self._stop_speech()
        if old.recognizer != self._settings.recognizer and self._loaded["stt"]:
            await self._in_stt(self._stt.unload)
            self._loaded["stt"] = False

    # --- idle unload (with the language model's timer, F-008)
    async def _idle_loop(self) -> None:
        while True:
            await asyncio.sleep(self._t.idle_check_s)
            minutes = self._idle_minutes()
            idle = self._clock() - self._used_at
            if minutes > 0 and not self._active() and idle >= minutes * 60:
                await self._unload()

    async def _unload(self) -> None:
        if self._loaded["stt"]:
            await self._in_stt(self._stt.unload)
            self._loaded["stt"] = False
        if self._loaded["tts"]:
            await self._in_tts(self._tts.unload)
            self._loaded["tts"] = False


def _code_for(message: str) -> str:
    return {
        NO_MIC: "no_mic",
        MIC_BLOCKED: "mic_blocked",
        NO_SPEAKER: "no_speaker",
        NOT_INSTALLED: "not_installed",
    }.get(message, "failed")
