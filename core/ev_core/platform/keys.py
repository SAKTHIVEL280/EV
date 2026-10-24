"""Key names for UI automation (F-110): "ctrl+s" -> pywinauto's "^s". Pure, so
it is tested on every platform; used by the Windows PC control."""

from typing import Final

from ev_core.interfaces.pc import PcError

KEY_NAMES: Final = {
    "enter": "{ENTER}", "tab": "{TAB}", "esc": "{ESC}", "escape": "{ESC}", "space": " ",
    "backspace": "{BACKSPACE}", "delete": "{DELETE}", "up": "{UP}", "down": "{DOWN}",
    "left": "{LEFT}", "right": "{RIGHT}", "home": "{HOME}", "end": "{END}",
    "pageup": "{PGUP}", "pagedown": "{PGDN}",
}  # fmt: skip
MODIFIERS: Final = {"ctrl": "^", "control": "^", "alt": "%", "shift": "+", "win": "{VK_LWIN}"}


def pywinauto_keys(keys: str) -> str:
    """ "ctrl+s" -> "^s", "enter" -> "{ENTER}", "ctrl+shift+t" -> "^+t"."""
    parts = [p.strip().lower() for p in keys.split("+") if p.strip()]
    if not parts:
        raise PcError("Which keys?", "empty keys")
    *mods, key = parts
    prefix = "".join(MODIFIERS.get(m, "") for m in mods)
    if key in KEY_NAMES:
        main = KEY_NAMES[key]
    elif len(key) == 1:
        main = "{" + key + "}" if key in "+^%~(){}[]" else key
    elif key.startswith("f") and key[1:].isdigit():
        main = "{" + key.upper() + "}"
    else:
        raise PcError("That key can't be pressed.", key)
    return prefix + main


def escape_text(text: str) -> str:
    """Text for pywinauto's send_keys, typed literally."""
    return "".join("{" + c + "}" if c in "+^%~(){}[]" else c for c in text)
