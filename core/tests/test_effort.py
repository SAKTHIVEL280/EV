import pytest

from ev_core.agent.effort import POLICIES, parse_prefix
from ev_core.config import EffortLevel
from ev_core.interfaces.llm import ModelRole


@pytest.mark.parametrize(
    ("text", "level", "rest"),
    [
        ("max effort, plan my week", EffortLevel.MAX, "plan my week"),
        ("Deep effort: compare these", EffortLevel.DEEP, "compare these"),
        ("  normal effort ,  hi ", EffortLevel.NORMAL, "hi"),
        ("instant effort, time", EffortLevel.INSTANT, "time"),
        ("quick effort, time", EffortLevel.INSTANT, "time"),
        ("MAX EFFORT, line one\nline two", EffortLevel.MAX, "line one\nline two"),
        ("max effort,", EffortLevel.MAX, ""),
    ],
)
def test_prefix_parsed(text: str, level: EffortLevel, rest: str) -> None:
    assert parse_prefix(text) == (level, rest)


@pytest.mark.parametrize(
    "text",
    ["plan my week", "max effort plan my week", "extreme effort, hi", "the max effort, ok", ""],
)
def test_no_prefix(text: str) -> None:
    assert parse_prefix(text) == (None, text)


def test_policies_match_contract() -> None:
    # CLAUDE.md §5.5
    assert POLICIES[EffortLevel.INSTANT].max_steps == 1
    assert POLICIES[EffortLevel.NORMAL].max_steps == 5
    assert POLICIES[EffortLevel.DEEP].max_steps == 15
    assert POLICIES[EffortLevel.MAX].max_steps == 40
    assert not POLICIES[EffortLevel.INSTANT].thinking
    assert not POLICIES[EffortLevel.NORMAL].thinking
    assert POLICIES[EffortLevel.DEEP].thinking
    assert POLICIES[EffortLevel.MAX].thinking
    # Provisional (decisions.md, "Hallucination eval"): the small model invents facts.
    assert POLICIES[EffortLevel.INSTANT].role is ModelRole.DEFAULT
    assert POLICIES[EffortLevel.NORMAL].role is ModelRole.DEFAULT
    assert POLICIES[EffortLevel.DEEP].role is ModelRole.LARGE
