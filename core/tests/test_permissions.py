import pytest

from ev_core.agent.permissions import Decision, decide
from ev_core.config import Permission
from ev_core.interfaces.tools import Risk

A, Q, B = Permission.ALLOW, Permission.ASK, Permission.BLOCK
S, C, D = Risk.SAFE, Risk.CONFIRM, Risk.DANGEROUS
RUN, ASK, BLOCK = Decision.RUN, Decision.ASK, Decision.BLOCK


@pytest.mark.parametrize(
    ("risk", "permission", "untrusted", "approved", "expected"),
    [
        # Block stops everything.
        (S, B, False, False, BLOCK),
        (C, B, False, True, BLOCK),
        (D, B, False, False, BLOCK),
        # Safe runs, even after untrusted content.
        (S, A, False, False, RUN),
        (S, Q, True, False, RUN),
        # Confirm asks unless allowed or already approved in this request...
        (C, Q, False, False, ASK),
        (C, A, False, False, RUN),
        (C, Q, False, True, RUN),
        # ...but always asks after untrusted content was read.
        (C, A, True, False, ASK),
        (C, Q, True, True, ASK),
        # Dangerous always asks.
        (D, A, False, False, ASK),
        (D, Q, False, True, ASK),
    ],
)
def test_policy(
    risk: Risk, permission: Permission, untrusted: bool, approved: bool, expected: Decision
) -> None:
    assert decide(risk, permission, untrusted=untrusted, approved_before=approved) is expected
