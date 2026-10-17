import pytest

from ev_core.agent.intent import needs_pc_tools


@pytest.mark.parametrize(
    "text",
    [
        "Open Notepad",
        "turn the volume down a bit",
        "Mute",
        "set brightness to 40",
        "remind me at 5 pm to call mom",
        "set a timer for 10 minutes",
        "find my quarterly report",
        "move it to Documents",
        "take a screenshot",
        "fix the text I copied",
        "snap Chrome to the left half",
        "turn off wifi",
        "click the save button",
        "start focus mode for an hour",
        "next song",
    ],
)
def test_pc_requests(text: str) -> None:
    assert needs_pc_tools(text)


@pytest.mark.parametrize(
    "text",
    [
        "What is the capital of Australia?",
        "Who wrote Romeo and Juliet?",
        "Explain what RAM is in one sentence.",
        "Give me one tip to fall asleep faster.",
        "How many days until Christmas?",
        "Tell me about the Tamil film Kathi.",
        "Write a birthday wish for Arun.",
    ],
)
def test_general_questions(text: str) -> None:
    assert not needs_pc_tools(text)


def test_follow_ups_keep_the_tools() -> None:
    assert needs_pc_tools("the second one", previous_used_tools=True)
    assert not needs_pc_tools("the second one")
