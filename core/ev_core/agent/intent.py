"""Does a request need the PC tools? (CLAUDE.md §5.4 step 3, decisions.md)

General questions get a short prompt (system prompt + date math): the full
tool list nearly doubles the prompt and made the 4B doubt common facts in the
golden tests. Requests that look like PC actions, or follow up on one, get every
tool. Rules only, no model: a miss costs one clarifying reply, never an action.
"""

import re
from typing import Final

PC_WORDS: Final = re.compile(
    r"\b("
    # apps and windows
    r"open|launch|start|close|quit|exit|switch|app|apps|window|windows|snap|maximi[sz]e|"
    r"minimi[sz]e|restore|tile|left half|right half|"
    # sound, screen, radios
    r"volume|louder|quieter|mute|unmute|sound|brightness|brighter|dimmer|dim|"
    r"play|pause|resume|skip|next song|previous song|track|music|"
    r"wi-?fi|wireless|bluetooth|airplane|"
    # screenshots, clipboard, files
    r"screenshot|screen ?shot|capture|clipboard|copied|copy|paste|"
    r"file|files|folder|folders|document|documents|downloads|desktop|pdf|move|delete|"
    r"rename|find|search my|"
    # timers and focus
    r"timer|remind|reminder|alarm|wake me|in \d+ (?:minutes?|hours?|seconds?)|"
    r"focus mode|do not disturb|"
    # driving other apps
    r"click|type|press|button|tab|scroll|notepad|chrome|edge|explorer|spotify|calculator|"
    r"settings|word|excel|powerpoint|vs ?code|undo"
    r")\b",
    re.IGNORECASE,
)


def needs_pc_tools(text: str, previous_used_tools: bool = False) -> bool:
    """True when the request looks like a PC action, or the last turn used a tool
    (follow-ups such as "now close it" or "the second one")."""
    return previous_used_tools or bool(PC_WORDS.search(text))
