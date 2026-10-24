import pytest

from ev_core.interfaces.pc import PcError
from ev_core.platform.keys import escape_text, pywinauto_keys


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ("ctrl+s", "^s"),
        ("Ctrl + Shift + T", "^+t"),
        ("enter", "{ENTER}"),
        ("alt+f4", "%{F4}"),
        ("ctrl+plus", None),
        ("shift+(", "+{(}"),
        ("win+d", "{VK_LWIN}d"),
    ],
)
def test_key_names(keys: str, expected: str | None) -> None:
    if expected is None:
        with pytest.raises(PcError):
            pywinauto_keys(keys)
    else:
        assert pywinauto_keys(keys) == expected


def test_text_is_typed_literally() -> None:
    assert escape_text("a+b (c) 100%") == "a{+}b {(}c{)} 100{%}"
    with pytest.raises(PcError):
        pywinauto_keys("  ")
