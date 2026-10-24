"""Is Windows asking apps to be quiet? (earcons, F-009)

``SHQueryUserNotificationState``: quiet time (Focus / Do Not Disturb),
presentation mode and full-screen D3D apps all mean "no sounds". Other
platforms: never quiet (development).
"""

import ctypes
import sys
from typing import Final

QUNS_RUNNING_D3D_FULL_SCREEN: Final = 3
QUNS_PRESENTATION_MODE: Final = 4
QUNS_QUIET_TIME: Final = 6
_QUIET_STATES: Final = frozenset(
    {QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE, QUNS_QUIET_TIME}
)


def is_quiet_state(state: int) -> bool:
    return state in _QUIET_STATES


def windows_wants_quiet() -> bool:
    if sys.platform != "win32":
        return False
    state = ctypes.c_int(0)
    result = ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
    return result == 0 and is_quiet_state(state.value)
