"""EV wire protocol (docs/ARCHITECTURE.md §3).

Types come from ``generated.py`` (from protocol/ev-protocol.schema.json); this
module adds the discriminated union, encode/decode and message constructors.
"""

import json
import re
import uuid
from typing import Annotated, Final

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from ev_core.errors import EvError
from ev_core.protocol.generated import (
    EmptyPayload,
    ErrorMessage,
    ErrorPayload,
    HelloAckMessage,
    HelloAckPayload,
    HelloMessage,
    HelloPayload,
    ModuleState,
    ModuleStatus,
    PingMessage,
    PongMessage,
    Reason,
    ShutdownMessage,
    ShutdownPayload,
)

PROTOCOL_VERSION: Final = 1
"""Must equal ``x-ev-protocol-version`` in the schema (enforced by a test)."""

type AnyMessage = Annotated[
    HelloMessage | HelloAckMessage | PingMessage | PongMessage | ErrorMessage | ShutdownMessage,
    Field(discriminator="type"),
]

_ADAPTER: Final[TypeAdapter[AnyMessage]] = TypeAdapter(AnyMessage)
_UUID_V4: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class DecodeError(EvError):
    """A frame is not a valid protocol message. ``reply_to`` is its id when readable."""

    def __init__(self, detail: str, reply_to: str | None) -> None:
        super().__init__("EV received a message it doesn't understand.", detail)
        self.reply_to = reply_to


def decode(raw: str | bytes) -> AnyMessage:
    try:
        return _ADAPTER.validate_json(raw, strict=True)
    except ValidationError as exc:
        raise DecodeError(str(exc), _readable_id(raw)) from exc


def encode(message: BaseModel) -> str:
    return message.model_dump_json(exclude_none=True)


def new_id() -> str:
    return str(uuid.uuid4())


def hello(app_version: str) -> HelloMessage:
    return HelloMessage(
        v=PROTOCOL_VERSION,
        type="hello",
        id=new_id(),
        payload=HelloPayload(app_version=app_version, protocol=PROTOCOL_VERSION),
    )


def hello_ack(reply_to: str, core_version: str, modules: list[ModuleStatus]) -> HelloAckMessage:
    return HelloAckMessage(
        v=PROTOCOL_VERSION,
        type="hello.ack",
        id=new_id(),
        reply_to=reply_to,
        payload=HelloAckPayload(
            core_version=core_version, protocol=PROTOCOL_VERSION, modules=modules
        ),
    )


def ping() -> PingMessage:
    return PingMessage(v=PROTOCOL_VERSION, type="ping", id=new_id(), payload=EmptyPayload())


def pong(reply_to: str) -> PongMessage:
    return PongMessage(
        v=PROTOCOL_VERSION, type="pong", id=new_id(), reply_to=reply_to, payload=EmptyPayload()
    )


def error(
    code: str, message: str, detail: str | None = None, reply_to: str | None = None
) -> ErrorMessage:
    return ErrorMessage(
        v=PROTOCOL_VERSION,
        type="error",
        id=new_id(),
        reply_to=reply_to,
        payload=ErrorPayload(code=code, message=message, detail=detail),
    )


def shutdown(reason: Reason) -> ShutdownMessage:
    return ShutdownMessage(
        v=PROTOCOL_VERSION, type="shutdown", id=new_id(), payload=ShutdownPayload(reason=reason)
    )


def _readable_id(raw: str | bytes) -> str | None:
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(obj, dict):
        candidate = obj.get("id")
        if isinstance(candidate, str) and _UUID_V4.match(candidate):
            return candidate
    return None


__all__ = [
    "PROTOCOL_VERSION",
    "AnyMessage",
    "DecodeError",
    "ErrorMessage",
    "HelloAckMessage",
    "HelloMessage",
    "ModuleState",
    "ModuleStatus",
    "PingMessage",
    "PongMessage",
    "Reason",
    "ShutdownMessage",
    "decode",
    "encode",
    "error",
    "hello",
    "hello_ack",
    "new_id",
    "ping",
    "pong",
    "shutdown",
]
