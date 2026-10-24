import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

from ev_core.bus import Event, EventBus
from ev_core.config import EffortLevel, EvConfig, SpeakReplies, VoiceSection
from ev_core.config.watcher import ConfigChanged
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
from ev_core.interfaces.voice import NOT_INSTALLED, LineHeard, VoiceError
from ev_core.modules import ModuleContext
from ev_core.voice import (
    ACKNOWLEDGEMENT,
    NO_SPEECH,
    RECOGNIZER_FOLDERS,
    SPEECH_FOLDER,
    VOICE_OFF,
    Timings,
    VoiceModule,
    voice_folder,
)
from ev_core.voice.audio import NO_MIC
from ev_core.voice.fake import FakeMic, FakeSpeaker, FakeStt, FakeTts

TURN = "36c14c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d"
FAST = Timings(
    end_grace_s=0.05,
    no_speech_s=0.3,
    follow_up_s=0.2,
    tick_s=0.005,
    level_every_s=0.0,
    barge_buffer_s=0.2,
    idle_check_s=0.02,
)
QUIET = np.zeros(800, dtype=np.float32)
LOUD = (np.random.default_rng(1).standard_normal(800) * 0.3).astype(np.float32)


@dataclass
class Rig:
    module: VoiceModule
    bus: EventBus
    mic: FakeMic
    stt: FakeStt
    tts: FakeTts
    speaker: FakeSpeaker
    events: list[Event] = field(default_factory=list)

    def of[E: Event](self, kind: type[E]) -> list[E]:
        return [e for e in self.events if isinstance(e, kind)]

    def last_state(self) -> VoiceStateChanged:
        return self.of(VoiceStateChanged)[-1]

    async def until(self, condition: Callable[[], bool], limit_s: float = 2.0) -> None:
        # Polling on purpose: the fakes have no events to wait for.
        async with asyncio.timeout(limit_s):
            while not condition():  # noqa: ASYNC110
                await asyncio.sleep(0.005)

    async def publish(self, event: Event) -> None:
        self.bus.publish(event)
        await self.bus.drain()

    async def say(self, *lines: LineHeard) -> None:
        """The recognizer returns ``lines`` for the next chunk of audio."""
        self.stt.script.append(list(lines))
        self.mic.push(QUIET)
        await self.until(lambda: not self.stt.script)

    async def utterance(self, text: str = "open notepad") -> None:
        await self.publish(VoiceStartRequested("hotkey"))
        await self.say(LineHeard(1, text, complete=False))
        await self.say(LineHeard(1, text, complete=True))
        await self.until(lambda: any(h.final for h in self.of(VoiceHeard)))


def make_models(root: Path, *, recognizer: bool = True, speech: bool = True) -> Path:
    models = root / "models"
    if recognizer:
        (voice_folder(models) / RECOGNIZER_FOLDERS["small"]).mkdir(parents=True)
    if speech:
        (voice_folder(models) / SPEECH_FOLDER).mkdir(parents=True)
    return models


async def start_rig(
    tmp_path: Path,
    settings: VoiceSection | None = None,
    *,
    models: Path | None = None,
    mic: FakeMic | None = None,
    idle_minutes: int = 10,
    clock: Callable[[], float] | None = None,
) -> Rig:
    folder = models if models is not None else make_models(tmp_path)
    bus = EventBus()
    rig_mic = mic or FakeMic()
    stt, tts, speaker = FakeStt(), FakeTts(), FakeSpeaker()
    kwargs = {"clock": clock} if clock is not None else {}
    module = VoiceModule(
        settings or VoiceSection(),
        lambda: folder,
        lambda: idle_minutes,
        stt=stt,
        tts=tts,
        mic=rig_mic,
        speaker=speaker,
        timings=FAST,
        **kwargs,  # type: ignore[arg-type]
    )
    rig = Rig(module, bus, rig_mic, stt, tts, speaker)
    for kind in (VoiceStateChanged, VoiceHeard, VoiceLevel):

        async def record(event: Event) -> None:
            rig.events.append(event)

        bus.subscribe(kind, record)
    await module.start(ModuleContext(bus, logging.getLogger("test")))
    return rig


@pytest.fixture
async def rig(tmp_path: Path) -> AsyncIterator[Rig]:
    started = await start_rig(tmp_path)
    yield started
    await started.module.stop()


async def test_listening_sends_what_was_said_after_a_pause(rig: Rig) -> None:
    await rig.publish(VoiceStartRequested("hotkey"))
    assert rig.mic.open
    assert rig.last_state().mic
    assert len(rig.speaker.played) == 1  # the wake earcon
    await rig.say(LineHeard(1, "open", complete=False))
    await rig.say(LineHeard(1, "open notepad", complete=True))
    # A second line within the grace period joins the request.
    await rig.say(LineHeard(2, "please", complete=True))
    await rig.until(lambda: any(h.final for h in rig.of(VoiceHeard)))
    heard = rig.of(VoiceHeard)
    assert [h.text for h in heard if not h.final][:2] == ["open", "open notepad"]
    assert [h.text for h in heard if h.final] == ["open notepad please"]
    assert len(rig.speaker.played) == 2  # plus the done earcon
    # Waiting for the spoken reply: the mic only watches now.
    assert rig.mic.open
    assert rig.stt.sessions[0].closed


async def test_spoken_turn_is_spoken_then_a_follow_up_is_heard(rig: Rig) -> None:
    await rig.utterance()
    rig.speaker.finish()  # earcons done
    await rig.publish(ChatRequested(TURN, "open notepad", EffortLevel.NORMAL, spoken=True))
    await rig.publish(ChatDelta(TURN, "Opening Notepad. It"))
    await rig.publish(ChatDelta(TURN, " is open now."))
    await rig.until(lambda: len(rig.speaker.played) == 3)  # 2 earcons, 1 sentence
    assert rig.last_state().speaking
    # The last sentence has nothing after it yet: it goes when the reply ends.
    await rig.publish(ChatDone(TURN, "x", EffortLevel.NORMAL, None, 1, cancelled=False))
    await rig.until(lambda: len(rig.speaker.played) == 4)
    assert rig.tts.spoken == ["Opening Notepad.", "It is open now."]
    rig.speaker.finish()
    # Follow-up: a new listening session, without the wake earcon.
    await rig.until(lambda: len(rig.stt.sessions) == 2 and not rig.last_state().speaking)
    played = len(rig.speaker.played)
    # Nobody speaks: the mic closes quietly.
    await rig.until(lambda: not rig.mic.open)
    assert len(rig.speaker.played) == played
    assert rig.last_state().message is None


async def test_typed_turns_get_text_only_and_stop_the_watch(rig: Rig) -> None:
    await rig.utterance()
    await rig.publish(ChatRequested(TURN, "typed instead", EffortLevel.NORMAL, spoken=False))
    await rig.publish(ChatDelta(TURN, "Hello there. "))
    await asyncio.sleep(0.05)
    assert rig.tts.spoken == []
    assert not rig.mic.open


async def test_always_speaks_typed_turns_too(tmp_path: Path) -> None:
    rig = await start_rig(tmp_path, VoiceSection(speak_replies=SpeakReplies.ALWAYS))
    await rig.publish(ChatRequested(TURN, "hi", EffortLevel.NORMAL))
    await rig.publish(ChatDelta(TURN, "Hi. "))
    await rig.until(lambda: rig.tts.spoken == ["Hi."])
    await rig.module.stop()


async def test_acknowledgement_before_a_tool_runs(rig: Rig) -> None:
    await rig.publish(ChatRequested(TURN, "close it", EffortLevel.NORMAL, spoken=True))
    await rig.publish(ChatToolChanged(TURN, "apps", "running"))
    await rig.publish(ChatToolChanged(TURN, "apps", "running"))
    await rig.until(lambda: rig.tts.spoken == [ACKNOWLEDGEMENT])
    await rig.publish(ChatDelta(TURN, "Closed it. "))
    await rig.until(lambda: rig.tts.spoken == [ACKNOWLEDGEMENT, "Closed it."])


async def test_no_acknowledgement_when_the_reply_already_started(rig: Rig) -> None:
    await rig.publish(ChatRequested(TURN, "x", EffortLevel.NORMAL, spoken=True))
    await rig.publish(ChatDelta(TURN, "Sure. "))
    await rig.publish(ChatToolChanged(TURN, "apps", "running"))
    await rig.until(lambda: len(rig.tts.spoken) == 1)
    await asyncio.sleep(0.03)
    assert rig.tts.spoken == ["Sure."]


async def test_failure_is_spoken_with_the_error_earcon(rig: Rig) -> None:
    await rig.publish(ChatRequested(TURN, "x", EffortLevel.NORMAL, spoken=True))
    await rig.publish(ChatFailed(TURN, "model_stopped", "The model stopped responding."))
    await rig.until(lambda: len(rig.speaker.played) == 2)  # error earcon, then the message
    assert rig.tts.spoken == ["The model stopped responding."]


async def test_typing_turns_the_mic_off_and_stops_speech(rig: Rig) -> None:
    await rig.publish(ChatRequested(TURN, "x", EffortLevel.NORMAL, spoken=True))
    await rig.publish(ChatDelta(TURN, "A long answer. "))
    await rig.until(lambda: rig.speaker.playing)
    await rig.publish(VoiceStartRequested("button"))
    await rig.publish(VoiceStopRequested("typing"))
    assert not rig.mic.open
    assert rig.speaker.stops == 1
    assert not rig.last_state().speaking


async def test_closing_the_panel_keeps_speaking_without_follow_up(rig: Rig) -> None:
    await rig.utterance()
    rig.speaker.finish()
    await rig.publish(ChatRequested(TURN, "x", EffortLevel.NORMAL, spoken=True))
    await rig.publish(VoiceStopRequested("closed"))
    assert not rig.mic.open
    await rig.publish(ChatDelta(TURN, "Still talking. "))
    await rig.publish(ChatDone(TURN, "x", EffortLevel.NORMAL, None, 1, cancelled=False))
    await rig.until(lambda: len(rig.speaker.played) == 3)
    assert rig.tts.spoken == ["Still talking."]
    assert rig.speaker.stops == 0
    rig.speaker.finish()
    await asyncio.sleep(0.05)
    assert len(rig.stt.sessions) == 1  # no follow-up


async def test_talking_over_evs_reply_stops_it_and_listens(rig: Rig) -> None:
    await rig.utterance()
    rig.speaker.finish()
    await rig.publish(ChatRequested(TURN, "x", EffortLevel.NORMAL, spoken=True))
    await rig.publish(ChatDelta(TURN, "Here is a long reply. "))
    await rig.until(lambda: rig.speaker.playing)
    rig.speaker.output_level = 0.2
    # The echo of EV's own voice is not barge-in.
    for _ in range(10):
        rig.mic.push((QUIET + 0.05).astype(np.float32))
    await asyncio.sleep(0.05)
    assert rig.speaker.stops == 0
    for _ in range(4):
        rig.mic.push(LOUD * 3)
    await rig.until(lambda: rig.speaker.stops == 1)
    await rig.until(lambda: len(rig.stt.sessions) == 2)
    # The new session got the audio from the start of the barge-in.
    await rig.until(lambda: rig.stt.sessions[1].fed > 0)
    assert not rig.last_state().speaking


async def test_hotkey_while_speaking_stops_and_listens(rig: Rig) -> None:
    await rig.publish(ChatRequested(TURN, "x", EffortLevel.NORMAL, spoken=True))
    await rig.publish(ChatDelta(TURN, "Talking. "))
    await rig.until(lambda: rig.speaker.playing)
    await rig.publish(VoiceStartRequested("hotkey"))
    assert rig.speaker.stops == 1
    assert rig.mic.open
    assert len(rig.stt.sessions) == 1


async def test_noise_before_the_reply_starts_keeps_the_reply(rig: Rig) -> None:
    await rig.utterance()
    rig.speaker.finish()
    await rig.publish(ChatRequested(TURN, "x", EffortLevel.NORMAL, spoken=True))
    for _ in range(4):
        rig.mic.push(LOUD)
    await rig.until(lambda: len(rig.stt.sessions) == 2)
    # Nothing recognized: when the reply arrives it is spoken, and the mic watches again.
    await rig.publish(ChatDelta(TURN, "Done. "))
    await rig.until(lambda: rig.tts.spoken == ["Done."])
    await rig.until(lambda: rig.speaker.playing)
    assert rig.stt.sessions[1].closed


async def test_nothing_said_closes_the_mic_with_a_message(rig: Rig) -> None:
    await rig.publish(VoiceStartRequested("hotkey"))
    # The fake mic closes a moment before the state goes out: wait for the state.
    await rig.until(lambda: rig.last_state().message == NO_SPEECH)
    assert not rig.mic.open
    assert rig.last_state().code == "no_speech"
    assert not any(h.final for h in rig.of(VoiceHeard))


async def test_filler_alone_is_not_sent(rig: Rig) -> None:
    await rig.publish(VoiceStartRequested("hotkey"))
    await rig.say(LineHeard(1, "you", complete=True))
    await rig.until(lambda: not rig.mic.open)
    assert not any(h.final for h in rig.of(VoiceHeard))


async def test_push_to_talk_sends_on_release(rig: Rig) -> None:
    await rig.publish(VoiceStartRequested("push_to_talk"))
    await rig.say(LineHeard(1, "what time is it", complete=False))
    rig.stt.on_finish = [LineHeard(1, "what time is it", complete=False)]
    await rig.publish(VoiceStopRequested("send"))
    assert [h.text for h in rig.of(VoiceHeard) if h.final] == ["what time is it"]


async def test_not_installed(tmp_path: Path) -> None:
    rig = await start_rig(tmp_path, models=make_models(tmp_path, recognizer=False))
    await rig.publish(VoiceStartRequested("hotkey"))
    assert not rig.mic.open
    assert rig.last_state().message == NOT_INSTALLED
    assert rig.last_state().code == "not_installed"
    await rig.module.stop()


async def test_spoken_reply_without_the_voice_files(tmp_path: Path) -> None:
    rig = await start_rig(tmp_path, models=make_models(tmp_path, speech=False))
    await rig.utterance()
    await rig.publish(ChatRequested(TURN, "x", EffortLevel.NORMAL, spoken=True))
    assert rig.last_state().code == "not_installed"
    assert not rig.mic.open
    await rig.module.stop()


async def test_no_microphone(tmp_path: Path) -> None:
    rig = await start_rig(tmp_path, mic=FakeMic(VoiceError(NO_MIC, "no device")))
    await rig.publish(VoiceStartRequested("hotkey"))
    assert rig.last_state().message == NO_MIC
    assert rig.last_state().code == "no_mic"
    await rig.module.stop()


async def test_voice_off(tmp_path: Path) -> None:
    rig = await start_rig(tmp_path, VoiceSection(enabled=False))
    await rig.publish(VoiceStartRequested("hotkey"))
    assert not rig.mic.open
    assert rig.last_state().message == VOICE_OFF
    await rig.module.stop()


async def test_earcons_respect_volume_and_focus_mode(tmp_path: Path) -> None:
    rig = await start_rig(tmp_path, VoiceSection(earcons_volume=0))
    await rig.publish(VoiceStartRequested("hotkey"))
    assert rig.speaker.played == []
    await rig.module.stop()
    rig = await start_rig(tmp_path / "b")
    await rig.publish(FocusModeChanged(on=True, minutes=25))
    await rig.publish(VoiceStartRequested("hotkey"))
    assert rig.speaker.played == []
    await rig.module.stop()


async def test_mic_level_is_published(rig: Rig) -> None:
    await rig.publish(VoiceStartRequested("hotkey"))
    rig.mic.push(LOUD)
    await rig.until(lambda: bool(rig.of(VoiceLevel)))
    assert 0 < rig.of(VoiceLevel)[-1].level <= 1


async def test_turning_voice_off_closes_everything(rig: Rig) -> None:
    await rig.publish(VoiceStartRequested("hotkey"))
    config = EvConfig().model_copy(update={"voice": VoiceSection(enabled=False)})
    await rig.publish(ConfigChanged(config, frozenset({"voice"}), ()))
    assert not rig.mic.open


async def test_engines_unload_when_idle(tmp_path: Path) -> None:
    now = [0.0]
    rig = await start_rig(tmp_path, clock=lambda: now[0], idle_minutes=1)
    await rig.publish(ChatRequested(TURN, "x", EffortLevel.NORMAL, spoken=True))
    await rig.publish(ChatDelta(TURN, "Hi. "))
    await rig.publish(ChatDone(TURN, "x", EffortLevel.NORMAL, None, 1, cancelled=False))
    await rig.until(lambda: rig.tts.loaded)
    rig.speaker.finish()
    await rig.until(lambda: not rig.last_state().speaking)
    now[0] = 61.0
    await rig.until(lambda: not rig.tts.loaded)
    await rig.module.stop()
