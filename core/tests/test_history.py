from ev_core.agent.history import MAX_TURNS, History, budget_chars
from ev_core.interfaces.llm import ChatMessage, ToolCall


def turn(text: str) -> list[ChatMessage]:
    return [ChatMessage("user", text), ChatMessage("assistant", text)]


def test_budget_from_context() -> None:
    assert budget_chars(8192, 1024) == (8192 - 1000 - 600 - 1024) * 3
    assert budget_chars(2048, 4096) == 0


def test_keeps_newest_turns_within_budget() -> None:
    history = History()
    for word in ["aaaa", "bbbb", "cccc"]:
        history.add_turn(turn(word))
    # Each turn is 8 characters.
    window = history.window(16)
    assert [m.content for m in window] == ["bbbb", "bbbb", "cccc", "cccc"]
    assert history.window(0) == []


def test_tool_calls_count_toward_size() -> None:
    history = History()
    call = ToolCall("1", "current_time", "{}" * 20)
    history.add_turn([ChatMessage("assistant", "", tool_calls=(call,))])
    assert history.window(10) == []
    assert len(history.window(100)) == 1


def test_turn_cap_and_clear() -> None:
    history = History()
    for i in range(MAX_TURNS + 5):
        history.add_turn(turn(str(i)))
    window = history.window(10**9)
    assert len(window) == MAX_TURNS * 2
    assert window[0].content == "5"
    history.clear()
    assert history.window(10**9) == []
