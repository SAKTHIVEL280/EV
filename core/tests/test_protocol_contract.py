"""Contract tests: schema, shared fixtures and the Python models agree."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from ev_core import protocol

PROTOCOL_DIR = Path(__file__).resolve().parents[2] / "protocol"
SCHEMA_PATH = PROTOCOL_DIR / "ev-protocol.schema.json"
GENERATED_PATH = Path(__file__).resolve().parents[1] / "ev_core" / "protocol" / "generated.py"
VALID = sorted((PROTOCOL_DIR / "fixtures" / "valid").glob("*.json"))
INVALID = sorted((PROTOCOL_DIR / "fixtures" / "invalid").glob("*.json"))


def _schema() -> dict[str, Any]:
    result: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return result


def _validator() -> jsonschema.Draft202012Validator:
    schema = _schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def test_fixtures_exist() -> None:
    assert VALID
    assert INVALID


def test_protocol_version_matches_schema() -> None:
    assert _schema()["x-ev-protocol-version"] == protocol.PROTOCOL_VERSION


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_fixture_accepted_by_schema_and_models(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    _validator().validate(json.loads(raw))
    message = protocol.decode(raw)
    # Round trip: encoding then decoding yields the same message.
    assert protocol.decode(protocol.encode(message)) == message


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_fixture_rejected_by_schema_and_models(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    assert not _validator().is_valid(json.loads(raw))
    with pytest.raises(protocol.DecodeError):
        protocol.decode(raw)


def test_constructed_messages_satisfy_schema() -> None:
    validator = _validator()
    hello = protocol.hello("0.1.0-beta.1")
    messages = [
        hello,
        protocol.hello_ack(hello.id, "0.1.0b1", []),
        protocol.ping(),
        protocol.pong(hello.id),
        protocol.error("bad_message", "x", "detail", hello.id),
        protocol.shutdown(protocol.Reason.app_exit),
    ]
    for message in messages:
        validator.validate(json.loads(protocol.encode(message)))


def test_decode_error_carries_readable_id() -> None:
    with pytest.raises(protocol.DecodeError) as caught:
        protocol.decode(
            '{"v": 1, "type": "nope", "id": "0b6f1d4e-2c3a-4b5d-9e8f-1a2b3c4d5e6f", "payload": {}}'
        )
    assert caught.value.reply_to == "0b6f1d4e-2c3a-4b5d-9e8f-1a2b3c4d5e6f"
    with pytest.raises(protocol.DecodeError) as caught:
        protocol.decode("not json")
    assert caught.value.reply_to is None


def test_generated_models_are_up_to_date() -> None:
    core_dir = GENERATED_PATH.parents[2]
    # Output must sit inside core/ so ruff-format picks up core/pyproject.toml.
    with tempfile.TemporaryDirectory(dir=core_dir, prefix=".codegen-check-") as tmp:
        out = Path(tmp) / "generated.py"
        subprocess.run(  # noqa: S603 -- fixed argv, no user input
            [sys.executable, "-m", "datamodel_code_generator", "--output", str(out)],
            cwd=core_dir,
            check=True,
            capture_output=True,
        )
        fresh = out.read_text(encoding="utf-8")
    assert fresh == GENERATED_PATH.read_text(encoding="utf-8"), (
        "ev_core/protocol/generated.py is stale; run scripts/codegen-protocol"
    )
