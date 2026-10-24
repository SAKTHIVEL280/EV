"""The real voice engines (F-008): Kokoro says a sentence, Moonshine hears it back.

Needs the voice packs (F-010). Run with:
    EV_VOICE_MODELS=~/.local/share/EV/models/voice uv run pytest tests/test_voice_real.py
"""

import os
import time
from pathlib import Path

import pytest

from ev_core.interfaces.voice import MIC_RATE, NOT_INSTALLED, VoiceError
from ev_core.platform.quiet import is_quiet_state
from ev_core.voice import RECOGNIZER_FOLDERS, SPEECH_FOLDER
from ev_core.voice.audio import resample

FOLDER = os.environ.get("EV_VOICE_MODELS")
needs_models = pytest.mark.skipif(not FOLDER, reason="needs the voice packs (see docstring)")


def test_quiet_states() -> None:
    assert is_quiet_state(6)  # Focus / Do Not Disturb
    assert is_quiet_state(4)  # presentation mode
    assert not is_quiet_state(5)  # accepts notifications
    assert not is_quiet_state(2)  # busy: the desktop can report this (decisions.md)


@needs_models
@pytest.mark.parametrize("size", ["small", "tiny"])
def test_kokoro_speaks_and_moonshine_hears_it(size: str) -> None:
    from ev_core.voice.moonshine import MoonshineStt, MoonshineTts

    root = Path(str(FOLDER)).expanduser()
    tts, stt = MoonshineTts(), MoonshineStt()
    started = time.perf_counter()
    samples, rate = tts.synthesize(
        "Set a timer for ten minutes.", "af_heart", 1.0, root / SPEECH_FOLDER
    )
    assert rate > 0
    assert 1.0 < samples.size / rate < 5.0
    assert time.perf_counter() - started < 10
    audio = resample(samples, rate, MIC_RATE)
    session = stt.open(root / RECOGNIZER_FOLDERS[size])
    lines = []
    for i in range(0, audio.size, 800):
        lines += session.feed(audio[i : i + 800])
    lines += session.finish()
    session.close()
    text = " ".join(line.text for line in lines if line.complete).lower()
    assert "timer" in text
    assert "ten" in text or "10" in text
    stt.unload()
    tts.unload()


def test_missing_folder_is_not_installed(tmp_path: Path) -> None:
    from ev_core.voice.moonshine import MoonshineStt

    with pytest.raises(VoiceError) as caught:
        MoonshineStt().open(tmp_path / "moonshine-small-streaming-en")
    assert caught.value.user_message == NOT_INSTALLED


@needs_models
def test_audio_after_finish_is_ignored() -> None:
    """Push-to-talk release can overtake the last queued chunks (found in the e2e test)."""
    import numpy as np

    from ev_core.voice.moonshine import MoonshineStt

    stt = MoonshineStt()
    session = stt.open(Path(str(FOLDER)).expanduser() / RECOGNIZER_FOLDERS["tiny"])
    session.feed(np.zeros(800, dtype=np.float32))
    session.finish()
    assert session.feed(np.zeros(800, dtype=np.float32)) == []
    assert session.finish() == []
    session.close()
    stt.unload()
