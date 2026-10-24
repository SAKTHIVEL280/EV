import numpy as np
import pytest

from ev_core.voice import level_of, worth_sending
from ev_core.voice.audio import resample
from ev_core.voice.barge import FRAME, BargeDetector
from ev_core.voice.earcons import PEAK, RATE, Earcon, render
from ev_core.voice.text import SentenceSplitter, speakable


def split(*deltas: str) -> list[str]:
    splitter = SentenceSplitter(first_clause=False)
    out: list[str] = []
    for delta in deltas:
        out += splitter.add(delta)
    return out + splitter.flush()


def test_sentences_come_out_as_soon_as_they_end() -> None:
    splitter = SentenceSplitter(first_clause=False)
    assert splitter.add("Okay, opening Note") == []
    assert splitter.add("pad. It should") == ["Okay, opening Notepad."]
    assert splitter.add(" be up now! Anything else") == ["It should be up now!"]
    assert splitter.flush() == ["Anything else"]


def test_the_first_clause_is_spoken_before_its_sentence_ends() -> None:
    splitter = SentenceSplitter()
    assert splitter.add("Sure, I can") == ["Sure,"]
    # After the first piece, only whole sentences.
    assert splitter.add(" help, gladly. Next") == ["I can help, gladly."]
    assert splitter.flush() == ["Next"]


@pytest.mark.parametrize(
    ("deltas", "expected"),
    [
        (("Dr. Smith is in. Yes.",), ["Dr. Smith is in.", "Yes."]),
        (("J. R. R. Tolkien wrote it. ",), ["J. R. R. Tolkien wrote it."]),
        (("It costs 3.50 today. Ok",), ["It costs 3.50 today.", "Ok"]),
        (("Line one\nLine two",), ["Line one", "Line two"]),
        (("**Bold** and `code`. Done.",), ["Bold and code.", "Done."]),
        (("1. First\n2. Second",), ["First", "Second"]),
        (("Run this:\n```\nrm -rf x. y\n```\nThat's it.",), ["Run this:", "That's it."]),
        (("See [the docs](https://x.y/z). Bye.",), ["See the docs.", "Bye."]),
        (("Wait... what?! Really.",), ["Wait... what?!", "Really."]),
        (("Hmm... No. Ok",), ["Hmm...", "No.", "Ok"]),
    ],
)
def test_sentence_table(deltas: tuple[str, ...], expected: list[str]) -> None:
    assert split(*deltas) == expected


def test_speakable_drops_urls_and_marks() -> None:
    assert speakable("# Title\nGo to https://example.com now") == "Title Go to the link now"


def test_fillers_alone_are_not_requests() -> None:
    assert not worth_sending("you")
    assert not worth_sending("Um, uh.")
    assert not worth_sending("")
    assert worth_sending("Open Notepad")
    assert worth_sending("yes")


def test_level_maps_decibels_to_unit_range() -> None:
    assert level_of(np.zeros(800, dtype=np.float32)) == 0.0
    assert level_of(np.full(800, 1.0, dtype=np.float32)) == 1.0
    quiet = level_of(np.full(800, 0.001, dtype=np.float32))  # -60 dBFS
    assert quiet == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("earcon", list(Earcon))
def test_earcons_are_short_soft_and_click_free(earcon: Earcon) -> None:
    wave = render(earcon, 1.0)
    assert wave.dtype == np.float32
    assert len(wave) / RATE < 0.3
    assert float(np.max(np.abs(wave))) == pytest.approx(PEAK, rel=1e-3)
    # Starts and ends at silence: no click.
    assert abs(float(wave[0])) < 1e-3
    assert abs(float(wave[-1])) < 1e-3
    assert float(np.max(np.abs(render(earcon, 0.5)))) == pytest.approx(PEAK / 2, rel=1e-3)
    assert not np.any(render(earcon, 0.0))


def test_resample_keeps_duration_and_tone() -> None:
    t = np.arange(48_000, dtype=np.float32) / 48_000
    tone = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    down = resample(tone, 48_000, 16_000)
    assert down.size == 16_000
    assert down.dtype == np.float32
    up = resample(np.zeros(24_000, dtype=np.float32), 24_000, 48_000)
    assert up.size == 48_000
    same = resample(tone, 16_000, 16_000)
    assert same is tone or np.array_equal(same, tone)


def noise(level: float, frames: int = 1, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(FRAME * frames) * level).astype(np.float32)


def test_speech_in_silence_is_detected_after_150_ms() -> None:
    detector = BargeDetector()
    for _ in range(20):
        assert not detector.feed(noise(0.001), 0.0)
    assert not detector.feed(noise(0.1), 0.0)
    assert not detector.feed(noise(0.1), 0.0)
    assert detector.feed(noise(0.1), 0.0)


def test_echo_of_evs_own_voice_is_not_barge_in() -> None:
    detector = BargeDetector()
    # Laptop speakers: the mic hears EV at about half the output level.
    for i in range(60):
        assert not detector.feed(noise(0.05, seed=i), output_level=0.1)
    assert detector.ratio < 0.8
    # The user talks clearly louder than the echo.
    hits = [detector.feed(noise(0.4, seed=100 + i), output_level=0.1) for i in range(3)]
    assert hits[-1]


def test_with_headphones_quiet_speech_still_counts() -> None:
    detector = BargeDetector()
    for i in range(80):
        detector.feed(noise(0.0005, seed=i), output_level=0.2)
    assert detector.ratio < 0.05
    assert [detector.feed(noise(0.05, seed=200 + i), 0.2) for i in range(3)][-1]
